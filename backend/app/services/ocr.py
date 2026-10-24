"""Read an expiry date off a photo of packaging.

The OCR call and the date parsing are deliberately separate: recognising text from
a crumpled label is unreliable and untestable, but turning whatever words came back
into a plausible date is pure logic and is where the actual mistakes happen.
"""

from __future__ import annotations

import calendar
import logging
import re
from dataclasses import dataclass
from datetime import date, timedelta

logger = logging.getLogger(__name__)

_MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}

# Packaging usually says which date it means. When it does, that date is the answer
# and anything else on the label (packed-on, batch codes) is noise.
_HINTS = re.compile(
    r"\b(best\s*before(\s*end)?|use\s*by|exp(iry|ires|\.)?|bb[ed]?|sell\s*by|consume\s*by)\b",
    re.IGNORECASE,
)

_NUMERIC = re.compile(r"\b(\d{1,4})\s*[./\-]\s*(\d{1,2})(?:\s*[./\-]\s*(\d{1,4}))?\b")
# The month must be spelled out explicitly: matching any 3-9 letter word lets
# "BEST BEFORE 20 MAR" consume "BEFORE 20" and read the date as a bare "MAR".
_MONTH_WORDS = "|".join(f"{name}[a-z]*" for name in _MONTHS)
_WORDY = re.compile(
    rf"\b(?:(\d{{1,2}})\s*[-/ ]?\s*)?({_MONTH_WORDS})\s*[-/ ]?\s*(\d{{2,4}})\b",
    re.IGNORECASE,
)

# A real expiry sits in a narrow band around today. Anything outside it is a
# misread, a batch number, or the production date.
_PAST_LIMIT = timedelta(days=365 * 2)
_FUTURE_LIMIT = timedelta(days=365 * 10)


@dataclass(slots=True)
class ExpiryCandidate:
    value: date
    hinted: bool
    source: str
    # 0 for the day-first reading of an ambiguous numeric date, 1 for the fallback.
    reading: int = 0


def _end_of_month(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def _expand_year(year: int) -> int:
    """A two-digit year on food packaging is this century, not 1925."""
    if year < 100:
        return 2000 + year
    return year


def _safe_date(year: int, month: int, day: int | None) -> date | None:
    year = _expand_year(year)
    if not 1 <= month <= 12:
        return None
    try:
        # No day means end of month: "best before end 03/25" is good all March.
        return _end_of_month(year, month) if day is None else date(year, month, day)
    except ValueError:
        return None


def _plausible(value: date, today: date) -> bool:
    return today - _PAST_LIMIT <= value <= today + _FUTURE_LIMIT


def _numeric_dates(a: int, b: int, c: int | None) -> list[date | None]:
    """A bare numeric date is genuinely ambiguous, so offer every reading of it."""
    if c is None:
        # Two parts: month/year either way round.
        return [_safe_date(b, a, None), _safe_date(a, b, None)]
    if a >= 1000:
        return [_safe_date(a, b, c)]  # ISO: yyyy-mm-dd
    readings = [_safe_date(c, b, a)]  # day/month/year, the common case outside the US
    if a != b:
        readings.append(_safe_date(c, a, b))  # month/day/year
    return readings


def parse_expiry_candidates(text: str, *, today: date | None = None) -> list[ExpiryCandidate]:
    """Pull every plausible expiry date out of OCR'd label text, best guess first."""
    today = today or date.today()
    found: dict[date, ExpiryCandidate] = {}

    def record(value: date | None, hinted: bool, source: str, reading: int = 0) -> None:
        if value is None or not _plausible(value, today):
            return
        existing = found.get(value)
        if existing is None:
            found[value] = ExpiryCandidate(value, hinted, source, reading)
            return
        if hinted:
            existing.hinted = True
        existing.reading = min(existing.reading, reading)

    hint_spans = [match.end() for match in _HINTS.finditer(text)]

    def is_hinted(start: int) -> bool:
        # "Best before 15/03/25" — the date follows the words closely.
        return any(0 <= start - end <= 24 for end in hint_spans)

    for match in _NUMERIC.finditer(text):
        a, b = int(match.group(1)), int(match.group(2))
        c = int(match.group(3)) if match.group(3) else None
        for reading, value in enumerate(_numeric_dates(a, b, c)):
            record(value, is_hinted(match.start()), match.group(0).strip(), reading)

    for match in _WORDY.finditer(text):
        month = _MONTHS.get(match.group(2)[:3].lower())
        if month is None:
            continue
        day = int(match.group(1)) if match.group(1) else None
        record(
            _safe_date(int(match.group(3)), month, day),
            is_hinted(match.start()),
            match.group(0).strip(),
        )

    # Hinted dates win. Among the rest, the soonest date that has not already passed
    # is the useful one: that is what you need to cook before.
    def rank(candidate: ExpiryCandidate) -> tuple[int, int, int, date]:
        past = candidate.value < today
        return (
            0 if candidate.hinted else 1,
            1 if past else 0,
            candidate.reading,
            candidate.value,
        )

    return sorted(found.values(), key=rank)


def ocr_available() -> bool:
    try:
        import pytesseract  # noqa: PLC0415

        pytesseract.get_tesseract_version()
    except Exception:
        return False
    return True


def read_text(image_bytes: bytes) -> str:
    """OCR an image. Raises RuntimeError when Tesseract is not installed."""
    try:
        import pytesseract  # noqa: PLC0415
        from PIL import Image, ImageOps  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - depends on the install
        raise RuntimeError("OCR support is not installed") from exc

    import io  # noqa: PLC0415

    try:
        image = Image.open(io.BytesIO(image_bytes))
        image = ImageOps.exif_transpose(image).convert("L")
        # Expiry dates are small, low-contrast dot-matrix print. Tesseract does far
        # better on them enlarged and contrast-stretched than on the raw photo.
        if max(image.size) < 1600:
            scale = 1600 / max(image.size)
            image = image.resize((int(image.width * scale), int(image.height * scale)))
        image = ImageOps.autocontrast(image)
        return pytesseract.image_to_string(image)
    except Exception as exc:
        raise RuntimeError(f"Could not read that image: {exc}") from exc
