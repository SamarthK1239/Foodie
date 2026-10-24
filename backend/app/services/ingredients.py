"""Resolve free-text ingredient names onto canonical `Ingredient` rows."""

from __future__ import annotations

from dataclasses import dataclass

from rapidfuzz import fuzz, process
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingest.parsing import clean_ingredient_name, normalize_ingredient_key
from app.models import Ingredient, IngredientAlias

FUZZY_THRESHOLD = 88.0


@dataclass
class MatchResult:
    ingredient: Ingredient | None
    score: float
    method: str  # exact | alias | fuzzy | created | unmatched


class IngredientResolver:
    """Caches the canonical ingredient vocabulary for the duration of a bulk import."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self._by_key: dict[str, Ingredient] = {}
        self._alias_to_key: dict[str, str] = {}
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        for ingredient in self.session.execute(select(Ingredient)).scalars():
            self._by_key[ingredient.name] = ingredient
        for alias in self.session.execute(select(IngredientAlias)).scalars():
            ing = self.session.get(Ingredient, alias.ingredient_id)
            if ing is not None:
                self._alias_to_key[alias.alias] = ing.name
        self._loaded = True

    def invalidate(self) -> None:
        self._by_key.clear()
        self._alias_to_key.clear()
        self._loaded = False

    def match(self, raw_name: str) -> MatchResult:
        """Find an existing canonical ingredient without creating one."""
        self._load()
        cleaned = clean_ingredient_name(raw_name)
        key = normalize_ingredient_key(cleaned)
        if not key:
            return MatchResult(None, 0.0, "unmatched")

        if key in self._by_key:
            return MatchResult(self._by_key[key], 100.0, "exact")

        if key in self._alias_to_key:
            return MatchResult(self._by_key[self._alias_to_key[key]], 100.0, "alias")

        if self._by_key:
            best = process.extractOne(
                key, list(self._by_key.keys()), scorer=fuzz.token_sort_ratio
            )
            if best and best[1] >= FUZZY_THRESHOLD:
                return MatchResult(self._by_key[best[0]], float(best[1]), "fuzzy")

        return MatchResult(None, 0.0, "unmatched")

    def resolve(self, raw_name: str, *, create: bool = True) -> MatchResult:
        """Match an ingredient, optionally creating a canonical row when nothing fits."""
        result = self.match(raw_name)
        if result.ingredient is not None or not create:
            return result

        cleaned = clean_ingredient_name(raw_name)
        key = normalize_ingredient_key(cleaned)
        if not key:
            return MatchResult(None, 0.0, "unmatched")

        ingredient = Ingredient(
            name=key,
            display_name=cleaned.title(),
            category=guess_category(key),
        )
        self.session.add(ingredient)
        self.session.flush()
        self._by_key[key] = ingredient
        return MatchResult(ingredient, 100.0, "created")


_CATEGORY_HINTS: list[tuple[str, tuple[str, ...]]] = [
    ("produce", ("onion", "garlic", "tomato", "pepper", "carrot", "potato", "lettuce",
                 "spinach", "apple", "banana", "lemon", "lime", "celery", "cucumber",
                 "mushroom", "broccoli", "cabbage", "herb", "basil", "parsley", "cilantro",
                 "ginger", "avocado", "berry", "orange", "zucchini", "corn", "pea")),
    ("meat", ("chicken", "beef", "pork", "lamb", "bacon", "sausage", "turkey", "mince",
              "steak", "ham")),
    ("seafood", ("fish", "salmon", "tuna", "shrimp", "prawn", "cod", "crab", "squid")),
    ("dairy", ("milk", "cheese", "butter", "cream", "yogurt", "yoghurt", "egg", "paneer")),
    ("grain", ("flour", "rice", "pasta", "bread", "oat", "noodle", "tortilla", "couscous",
               "quinoa", "cereal")),
    ("pantry", ("salt", "sugar", "oil", "vinegar", "sauce", "stock", "broth", "spice",
                "powder", "seed", "honey", "syrup", "paste", "can", "bean", "lentil",
                "chickpea", "nut", "almond", "peanut", "cumin", "paprika", "cinnamon")),
]


def guess_category(key: str) -> str | None:
    for category, hints in _CATEGORY_HINTS:
        if any(hint in key for hint in hints):
            return category
    return None
