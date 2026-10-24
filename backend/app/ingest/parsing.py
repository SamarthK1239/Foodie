"""Parse free-text recipe ingredient lines into quantity / unit / ingredient name."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from app.services.units import is_known_unit, normalize_unit

_VULGAR_FRACTIONS = {
    "¼": 0.25,
    "½": 0.5,
    "¾": 0.75,
    "⅐": 1 / 7,
    "⅑": 1 / 9,
    "⅒": 0.1,
    "⅓": 1 / 3,
    "⅔": 2 / 3,
    "⅕": 0.2,
    "⅖": 0.4,
    "⅗": 0.6,
    "⅘": 0.8,
    "⅙": 1 / 6,
    "⅚": 5 / 6,
    "⅛": 0.125,
    "⅜": 0.375,
    "⅝": 0.625,
    "⅞": 0.875,
}

_NUMBER_WORDS = {
    "one": 1.0,
    "two": 2.0,
    "three": 3.0,
    "four": 4.0,
    "five": 5.0,
    "six": 6.0,
    "seven": 7.0,
    "eight": 8.0,
    "nine": 9.0,
    "ten": 10.0,
    "a": 1.0,
    "an": 1.0,
    "half": 0.5,
}

_OPTIONAL_MARKERS = ("optional", "to taste", "if desired", "as needed", "for garnish", "to serve")

# Preparation words stripped from the tail/head of an ingredient name.
_PREP_WORDS = {
    "chopped", "minced", "diced", "sliced", "grated", "shredded", "crushed", "peeled",
    "finely", "roughly", "coarsely", "thinly", "freshly", "fresh", "frozen", "canned",
    "cooked", "uncooked", "raw", "large", "small", "medium", "ripe", "beaten", "melted",
    "softened", "divided", "packed", "drained", "rinsed", "trimmed", "halved", "quartered",
    "cubed", "ground", "toasted", "warm", "cold", "room", "temperature", "plus", "more",
    "approximately", "about", "roasted", "boneless", "skinless", "washed", "stemmed",
    "seeded", "pitted", "crumbled", "whole", "extra", "optional", "well",
    "cooled", "cooking", "deseeded", "destoned", "deboned", "skinned", "zested",
    "juiced", "squeezed", "mashed", "whisked", "whipped", "sifted", "separated",
    "chunks", "cubes", "pieces", "slices", "strips", "wedges", "rings", "florets",
    "lengthways", "lengthwise", "crossways", "lightly", "generously", "shaved",
}

_CONTAINER_WORDS = {"can", "cans", "package", "packages", "jar", "jars", "bottle", "bottles",
                    "tin", "tins", "packet", "packets", "box", "boxes", "bag", "bags"}

_NOISE_PREFIXES = ("of ", "or ", "and ")

# Clause starters that introduce preparation instructions rather than the ingredient.
# Everything from the marker onwards is discarded.
_PREP_CLAUSE_RE = re.compile(
    r"\b(?:"
    r"cut into|cut in|cut from|broken into|torn into|chopped into|sliced into|"
    r"plus extra|plus more|plus a|mixed with|see tip|"
    r"for (?:cooking|serving|frying|greasing|dusting|drizzling|garnish|the)|"
    r"to (?:serve|taste|garnish|finish|decorate)|"
    r"of your choice|if (?:desired|needed|using)|as needed|at room temperature"
    r")\b",
    re.IGNORECASE,
)

# Dangling connectors left behind once a trailing preparation word is removed.
_CONNECTOR_WORDS = {"and", "or", "with", "for", "plus", "then"}

# A bare pack multiplier such as the "x 400g" in "2 x 400g cans chopped tomatoes".
_PACK_TOKEN_RE = re.compile(r"^(?:x|\d+(?:[.,]\d+)?[a-z]*)$", re.IGNORECASE)

# Plurals the generic "-s"/"-es" rules get wrong. Words like "olives" and "chives"
# are deliberately absent: the generic rule already singularises those correctly.
_IRREGULAR_PLURALS = {
    "leaves": "leaf",
    "halves": "half",
    "loaves": "loaf",
    "knives": "knife",
    "shelves": "shelf",
    "calves": "calf",
}

_QUANTITY_RE = re.compile(
    r"""^\s*
    (?P<qty>
        \d+\s+\d+\s*/\s*\d+     # 2 1/2
      | \d+\s*/\s*\d+           # 1/2
      | \d+(?:[.,]\d+)?         # 2 or 2.5
    )
    \s*""",
    re.VERBOSE,
)

_RANGE_SEP_RE = re.compile(r"^\s*(?:-|–|—|to)\s*(?=\d|\.)", re.IGNORECASE)
_PAREN_RE = re.compile(r"\(([^)]*)\)")


@dataclass
class ParsedIngredient:
    raw_text: str
    quantity: float | None
    unit: str | None
    name: str
    optional: bool


def _strip_accents_fractions(text: str) -> str:
    out: list[str] = []
    for char in text:
        if char in _VULGAR_FRACTIONS:
            value = _VULGAR_FRACTIONS[char]
            # Separate from a preceding digit so "1½" becomes "1 0.5" and sums correctly.
            if out and out[-1].isdigit():
                out.append(" ")
            out.append(f"{value:g}")
        else:
            out.append(char)
    return "".join(out)


def _parse_number(token: str) -> float:
    token = token.strip().replace(",", ".")
    if " " in token:  # mixed number like "2 1/2"
        whole, frac = token.split(None, 1)
        return float(whole) + _parse_number(frac)
    if "/" in token:
        numerator, denominator = token.split("/", 1)
        denom = float(denominator.strip())
        return float(numerator.strip()) / denom if denom else 0.0
    return float(token)


def _leading_quantity(text: str) -> tuple[float | None, str]:
    """Pull a (possibly ranged or compound) quantity off the front of the line."""
    match = _QUANTITY_RE.match(text)
    if not match:
        lowered = text.strip().lower()
        first = lowered.split(" ", 1)[0] if lowered else ""
        if first in _NUMBER_WORDS:
            remainder = text.strip()[len(first) :]
            return _NUMBER_WORDS[first], remainder.strip()
        return None, text

    total = _parse_number(match.group("qty"))
    rest = text[match.end() :]

    # "1 to 2 tbsp" / "1-2 tbsp" -> take the lower bound.
    range_match = _RANGE_SEP_RE.match(rest)
    if range_match:
        after = rest[range_match.end() :]
        second = _QUANTITY_RE.match(after)
        if second:
            rest = after[second.end() :]
            return total, rest.strip()

    # "1 1/2" already handled by the regex; handle "1 0.5" from vulgar fractions.
    extra = _QUANTITY_RE.match(rest)
    if extra:
        candidate = _parse_number(extra.group("qty"))
        remainder = rest[extra.end() :]
        if candidate < 1 and not remainder.strip().startswith("/"):
            total += candidate
            rest = remainder
    return total, rest.strip()


def _leading_unit(text: str) -> tuple[str | None, str]:
    tokens = text.split()
    if not tokens:
        return None, text
    # Try a two-word unit first ("fl oz", "fluid ounces").
    for size in (2, 1):
        if len(tokens) >= size:
            candidate = " ".join(tokens[:size]).strip(".,")
            if is_known_unit(candidate):
                return normalize_unit(candidate), " ".join(tokens[size:])
    return None, text


def _fold_accents(text: str) -> str:
    """Drop diacritics so 'purée' survives the ASCII filter as 'puree'."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _clean_segment(text: str) -> str:
    text = _PREP_CLAUSE_RE.split(text, maxsplit=1)[0]
    text = re.sub(r"[^a-z0-9\s'&-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    for prefix in _NOISE_PREFIXES:
        if text.startswith(prefix):
            text = text[len(prefix) :]

    tokens = [t for t in text.split() if t]
    while tokens and (
        tokens[0] in _PREP_WORDS
        or tokens[0] in _CONTAINER_WORDS
        or _PACK_TOKEN_RE.match(tokens[0])
    ):
        tokens.pop(0)
    while tokens and (tokens[-1] in _PREP_WORDS or tokens[-1] in _CONNECTOR_WORDS):
        tokens.pop()
    if tokens and tokens[0] == "of":
        tokens.pop(0)

    return " ".join(tokens).strip(" -&'")


def clean_ingredient_name(name: str) -> str:
    """Reduce a descriptive ingredient phrase to a canonical-ish ingredient name."""
    text = _fold_accents(name.lower())
    text = _PAREN_RE.sub(" ", text)
    for marker in (" - ", " — ", " – "):
        text = text.split(marker)[0]

    # Try each comma-separated clause in turn: the first is usually the ingredient,
    # but when it holds only preparation words ("boneless, skinless chicken breasts")
    # the real name lives further along.
    segments = [s for s in text.split(",") if s.strip()]
    for segment in segments:
        cleaned = _clean_segment(segment)
        if cleaned:
            return cleaned

    return name.strip().lower()


def normalize_ingredient_key(name: str) -> str:
    """Stable lookup key for canonical ingredients (lowercase, de-accented, singular-ish)."""
    text = unicodedata.normalize("NFKD", name.lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    tokens = [t for t in text.split() if t]
    singular: list[str] = []
    for token in tokens:
        if token in _IRREGULAR_PLURALS:
            singular.append(_IRREGULAR_PLURALS[token])
        elif len(token) > 3 and token.endswith("ies"):
            singular.append(token[:-3] + "y")
        elif len(token) > 3 and token.endswith("es") and token[-3] in "sxzho":
            singular.append(token[:-2])
        elif len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
            singular.append(token[:-1])
        else:
            singular.append(token)
    return " ".join(singular).strip()


def parse_ingredient_line(line: str) -> ParsedIngredient:
    """Parse one recipe ingredient line, e.g. '2 1/2 cups all-purpose flour, sifted'."""
    raw = line.strip()
    working = _strip_accents_fractions(raw)
    lowered = working.lower()
    optional = any(marker in lowered for marker in _OPTIONAL_MARKERS)

    quantity, rest = _leading_quantity(working)

    # "2 (14 oz) cans tomatoes" -> multiply out the parenthetical pack size.
    paren = _PAREN_RE.match(rest.strip())
    if paren and quantity is not None:
        inner = paren.group(1)
        inner_qty, inner_rest = _leading_quantity(inner)
        inner_unit, _ = _leading_unit(inner_rest)
        rest = rest.strip()[paren.end() :].strip()
        if inner_qty is not None and inner_unit is not None:
            quantity = quantity * inner_qty
            name_part = rest
            unit = inner_unit
            tokens = name_part.split()
            if tokens and tokens[0].lower().strip(".,") in _CONTAINER_WORDS:
                name_part = " ".join(tokens[1:])
            return ParsedIngredient(
                raw_text=raw,
                quantity=quantity,
                unit=unit,
                name=clean_ingredient_name(name_part),
                optional=optional,
            )

    unit, rest = _leading_unit(rest)
    if unit and rest.strip().lower().startswith("of "):
        rest = rest.strip()[3:]

    name = clean_ingredient_name(rest)
    if not name:
        name = clean_ingredient_name(raw)
    return ParsedIngredient(
        raw_text=raw,
        quantity=quantity,
        unit=unit,
        name=name,
        optional=optional,
    )
