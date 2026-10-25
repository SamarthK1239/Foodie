"""Derive diet and meal-type labels for a recipe from its ingredients and tags.

Scraped recipes carry almost no structured dietary metadata -- the only thing the
scrapers give us is a free-text category/cuisine list, which covers meal type for
roughly two thirds of the corpus and says nothing at all about meat content. So
both labels are inferred here and stored on the recipe, which keeps filtering in
SQL where it can be paged correctly.

The inference is deliberately conservative: when the evidence is thin the result
is OTHER / UNKNOWN rather than a guess, because a wrong "vegan" badge is much
worse than an absent one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.models.enums import DietClass, MealType
from app.services.tags import dump_tags, load_tags

# --- meat and animal-product vocabulary -------------------------------------
# Matched with word boundaries against both the canonical ingredient name and
# the raw recipe line, so "800g bavette steak" and "braising beef" both land.

MEAT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "beef": (
        "beef", "steak", "bavette", "brisket", "sirloin", "ribeye", "rib-eye",
        "oxtail", "veal", "rump", "chuck", "skirt", "hamburger", "pastrami",
        "corned beef", "short rib",
    ),
    "pork": (
        "pork", "bacon", "ham", "gammon", "sausage", "sausages", "chorizo",
        "pancetta", "prosciutto", "salami", "chipolata", "chipolatas",
        "lardon", "lardons", "spam", "pepperoni", "black pudding", "lard",
        "guanciale", "speck", "bratwurst",
    ),
    "chicken": (
        "chicken", "turkey", "duck", "goose", "poussin", "quail", "poultry",
    ),
    "lamb": ("lamb", "mutton", "goat", "hogget"),
    "fish": (
        "fish", "salmon", "tuna", "cod", "haddock", "mackerel", "sardine",
        "sardines", "anchovy", "anchovies", "prawn", "prawns", "shrimp",
        "crab", "lobster", "mussel", "mussels", "squid", "calamari",
        "scallop", "scallops", "oyster", "oysters", "clam", "clams",
        "tilapia", "trout", "seabass", "sea bass", "pollock", "whitebait",
        "crayfish", "octopus", "nam pla", "surimi", "kipper", "bonito",
        "katsuobushi", "dashi",
    ),
    "game": ("venison", "rabbit", "pheasant", "partridge", "boar", "hare"),
}

# Animal-derived but not meat. Blocks vegan, allows vegetarian.
DAIRY_EGG_KEYWORDS: tuple[str, ...] = (
    "milk", "butter", "cream", "cheese", "yogurt", "yoghurt", "egg", "eggs",
    "parmesan", "cheddar", "mozzarella", "mascarpone", "ricotta", "feta",
    "ghee", "custard", "creme fraiche", "crème fraîche", "buttermilk",
    "halloumi", "paneer", "gruyere", "gruyère", "brie", "stilton",
    "condensed milk", "evaporated milk", "whey", "casein", "curd",
    "meringue", "honey", "clotted cream", "soured cream", "sour cream",
    "double cream", "whipping cream", "quark", "mayonnaise",
)

# Hidden animal products that block vegetarian even with no visible meat.
HIDDEN_ANIMAL_KEYWORDS: tuple[str, ...] = (
    "gelatine", "gelatin", "worcestershire", "suet", "tallow", "rennet",
    "isinglass", "bone broth", "fish sauce", "oyster sauce", "shrimp paste",
    "belacan", "colatura",
)

# "butter" must not fire on nut butters, and "milk"/"cream" must not fire on
# plant versions. These are checked before the dairy keywords.
PLANT_SUBSTITUTE_PATTERNS: tuple[str, ...] = (
    r"peanut butter", r"almond butter", r"cashew butter", r"nut butter",
    r"cocoa butter", r"shea butter", r"seed butter", r"tahini",
    r"(?:soy|soya|almond|oat|rice|coconut|cashew|hemp|hazelnut)\s*milk",
    r"coconut cream", r"vegan\s+\w+", r"plant[- ]based\s+\w+",
    r"dairy[- ]free\s+\w+", r"butter\s*bean", r"butternut",
)

# A stock listed as "chicken or vegetable stock" is a dish that works either
# way, so it must not be counted as meat. Same for "beef or vegetable".
VEG_ALTERNATIVE = re.compile(
    r"\b(?:or|/)\s*(?:a\s+)?(?:light\s+|good\s+)?veg(?:etable|gie)?\b"
    r"|\bveg(?:etable|gie)?\s*(?:or|/)\s*",
    re.IGNORECASE,
)

# A line like "toppings of your choice, such as cooked bacon, blueberries or
# peanut butter" is a list of serving suggestions, not an ingredient. Reading
# the bacon in it literally turns a pancake recipe into a pork dish, so these
# lines are skipped entirely -- the dish as written works without any of them.
SUGGESTION_MARKER = re.compile(
    r"of your choice|such as|or similar|\btoppings?\b|to decorate|for the topping",
    re.IGNORECASE,
)

# Meat that is only present as a broth is weak evidence of a "beef dish", but
# it is still decisive for whether the recipe is vegetarian.
BROTH_MARKER = re.compile(r"\b(?:stock|broth|bouillon|consomm[ée])\b", re.IGNORECASE)


def _boundary(term: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![\w-]){re.escape(term)}(?![\w-])", re.IGNORECASE)


_MEAT_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    cat: tuple(_boundary(t) for t in terms) for cat, terms in MEAT_KEYWORDS.items()
}
_DAIRY_PATTERNS = tuple(_boundary(t) for t in DAIRY_EGG_KEYWORDS)
_HIDDEN_PATTERNS = tuple(_boundary(t) for t in HIDDEN_ANIMAL_KEYWORDS)
_PLANT_SUB_PATTERNS = tuple(re.compile(p, re.IGNORECASE) for p in PLANT_SUBSTITUTE_PATTERNS)


def _strip_plant_substitutes(text: str) -> str:
    """Blank out plant-based look-alikes so "peanut butter" is not read as dairy."""
    for pattern in _PLANT_SUB_PATTERNS:
        text = pattern.sub(" ", text)
    return text


@dataclass(frozen=True)
class DietResult:
    diet: DietClass
    meat_types: list[str]


def classify_diet(lines: list[tuple[str, bool]]) -> DietResult:
    """Classify from (text, optional) pairs.

    Optional ingredients are ignored: "2 tbsp fish sauce (optional)" describes a
    kimchi that is vegan as written for anyone who leaves it out, and treating it
    as fish would hide the recipe from exactly the people the flag is there for.
    """
    meat_types: set[str] = set()
    has_dairy_or_egg = False
    has_hidden_animal = False

    for raw, optional in lines:
        if optional or not raw:
            continue
        text = raw.lower()
        if SUGGESTION_MARKER.search(text):
            continue
        if VEG_ALTERNATIVE.search(text):
            # "chicken or vegetable stock" -- the dish does not require meat.
            continue

        for category, patterns in _MEAT_PATTERNS.items():
            if any(p.search(text) for p in patterns):
                meat_types.add(category)

        for pattern in _HIDDEN_PATTERNS:
            if pattern.search(text):
                has_hidden_animal = True
                break

        cleaned = _strip_plant_substitutes(text)
        if any(p.search(cleaned) for p in _DAIRY_PATTERNS):
            has_dairy_or_egg = True

    if meat_types:
        return DietResult(DietClass.MEAT, sorted(meat_types))
    if has_hidden_animal:
        # Anchovy in the Worcestershire sauce still rules out vegetarian, but
        # there is no meat to name, so it stays an unlabelled meat dish.
        return DietResult(DietClass.MEAT, [])
    if has_dairy_or_egg:
        return DietResult(DietClass.VEGETARIAN, [])
    return DietResult(DietClass.VEGAN, [])


# --- meal type ---------------------------------------------------------------

# Checked in order; the first group with a matching tag wins. Breakfast outranks
# dessert so a Dutch baby tagged "Breakfast, Brunch, Dessert" reads as breakfast,
# and lunch outranks side so "Lunch, Side dish" spam musubi is a lunch.
TAG_PRIORITY: tuple[tuple[MealType, tuple[str, ...]], ...] = (
    (MealType.BREAKFAST, ("breakfast", "brunch")),
    (MealType.DESSERT, ("dessert", "pudding", "treat", "baking", "sweets")),
    (MealType.DRINK, ("drink", "drinks", "cocktail", "beverage", "smoothie")),
    (MealType.LUNCH, ("lunch", "light lunch")),
    (MealType.DINNER, ("dinner", "supper", "main course", "main", "mains")),
    (MealType.SIDE, ("side dish", "side", "sides", "starter", "snack", "appetizer",
                     "appetiser", "accompaniment", "condiment")),
)

DESSERT_TITLE_WORDS = (
    "cake", "pie", "tart", "tarte", "pudding", "pavlova", "cupcake", "brownie",
    "cookie", "biscuit", "mousse", "trifle", "cheesecake", "ice cream",
    "sorbet", "gelato", "custard", "fudge", "truffle", "meringue", "eclair",
    "doughnut", "donut", "parfait", "sundae", "crumble", "cobbler", "scone",
    "shortbread", "flapjack", "tiramisu", "panna cotta", "macaron", "babka",
)
BREAKFAST_TITLE_WORDS = (
    "pancake", "pancakes", "waffle", "waffles", "porridge", "granola",
    "muesli", "omelette", "omelet", "frittata", "croissant", "bagel",
    "french toast", "crumpet", "oatmeal", "shakshuka", "hash brown",
)
DRINK_TITLE_WORDS = (
    "shot", "cocktail", "mocktail", "smoothie", "latte", "juice", "punch",
    "margarita", "martini", "negroni", "lemonade", "milkshake", "spritz",
)

_SAVOURY_MARKERS = tuple(
    _boundary(t)
    for t in ("onion", "onions", "garlic", "stock", "soy sauce", "pepper",
              "cumin", "paprika", "curry", "chilli", "chili", "broth")
)
_SUGAR_MARKERS = tuple(
    _boundary(t)
    for t in ("sugar", "icing sugar", "caster sugar", "honey", "maple syrup",
              "golden syrup", "chocolate", "cocoa")
)
_FLOUR_MARKERS = tuple(
    _boundary(t) for t in ("flour", "self-raising flour", "cornflour", "sponge fingers")
)


def _title_match(title: str, words: tuple[str, ...]) -> bool:
    """Titles use a plain word boundary rather than the hyphen-aware one used
    for ingredients: "Pavlova-misu" and "No-bake cheesecake" must still match,
    whereas an ingredient "sugar-free" genuinely is not sugar."""
    lowered = title.lower()
    return any(re.search(rf"\b{re.escape(w)}\b", lowered) for w in words)


def classify_meal_type(
    title: str, tags: list[str], lines: list[tuple[str, bool]], has_meat: bool
) -> MealType:
    """Tags are trusted first; only tag-less recipes fall through to inference."""
    normalized = {t.strip().lower() for t in tags if t and t.strip()}
    for meal_type, keys in TAG_PRIORITY:
        if normalized & set(keys):
            return meal_type

    if _title_match(title, DESSERT_TITLE_WORDS):
        return MealType.DESSERT
    if _title_match(title, BREAKFAST_TITLE_WORDS):
        return MealType.BREAKFAST
    if _title_match(title, DRINK_TITLE_WORDS):
        return MealType.DRINK

    # A sweet bake with no savoury aromatics is a pudding even when the title is
    # a proper noun the keyword list will never contain ("Karpatka").
    texts = [raw.lower() for raw, optional in lines if raw and not optional]
    if not has_meat and not any(p.search(t) for t in texts for p in _SAVOURY_MARKERS):
        sweet = any(p.search(t) for t in texts for p in _SUGAR_MARKERS)
        floury = any(p.search(t) for t in texts for p in _FLOUR_MARKERS)
        if sweet and floury:
            return MealType.DESSERT

    if has_meat:
        return MealType.DINNER
    return MealType.OTHER


# --- applying the labels to a recipe ----------------------------------------


def classify_recipe(recipe) -> None:
    """Recompute and store a recipe's diet and meal-type labels in place.

    Called from every write path, so a recipe's labels can never drift from its
    ingredients: editing a dish to swap the beef for lentils re-labels it.
    """
    lines = [
        (f"{ri.raw_text} {ri.ingredient.name if ri.ingredient else ''}", bool(ri.optional))
        for ri in recipe.ingredients
    ]
    result = classify_diet(lines)
    recipe.diet = result.diet
    recipe.meat_types = dump_tags(result.meat_types)
    recipe.meal_type = classify_meal_type(
        recipe.title or "",
        load_tags(recipe.tags),
        lines,
        result.diet == DietClass.MEAT,
    )
