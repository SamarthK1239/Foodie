"""Rank recipes by what is in stock and what is about to go bad."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import CookEvent, Recipe, RecipeIngredient
from app.models.entities import utcnow
from app.services.inventory import StockLevel, stock_by_ingredient

# Scoring weights. Coverage dominates, urgency is the tie-breaker that drives the
# waste-reduction goal, and missing items apply a mild penalty.
W_COVERAGE = 0.6
W_URGENCY = 0.3
W_MISSING = 0.1
RECENT_COOK_PENALTY = 0.25
RECENT_COOK_DAYS = 28


@dataclass
class IngredientMatch:
    recipe_ingredient: RecipeIngredient
    name: str
    raw_text: str
    have: bool
    optional: bool
    quantity_needed: float | None
    unit: str | None
    quantity_available: float | None
    sufficient: bool
    urgency: float


@dataclass
class ScoredRecipe:
    recipe: Recipe
    score: float
    coverage: float
    urgency: float
    matches: list[IngredientMatch] = field(default_factory=list)
    recently_cooked: bool = False

    @property
    def have(self) -> list[IngredientMatch]:
        return [m for m in self.matches if m.have]

    @property
    def missing(self) -> list[IngredientMatch]:
        return [m for m in self.matches if not m.have and not m.optional]


def _recently_cooked_recipe_ids(session: Session) -> set[int]:
    """Phase 2 groundwork, already useful: avoid suggesting last week's dinner again."""
    cutoff = utcnow().replace(tzinfo=None)
    cutoff = cutoff.fromordinal(cutoff.toordinal() - RECENT_COOK_DAYS)
    stmt = select(CookEvent.recipe_id).where(
        CookEvent.cooked_at >= cutoff, CookEvent.recipe_id.is_not(None)
    )
    return {row for row in session.execute(stmt).scalars() if row is not None}


def _candidate_recipes(
    session: Session, stock: dict[int, StockLevel], limit: int
) -> list[Recipe]:
    """Only consider recipes that use at least one in-stock ingredient."""
    if not stock:
        return []
    ingredient_ids = list(stock.keys())
    match_count = func.count(func.distinct(RecipeIngredient.ingredient_id)).label("matches")
    stmt = (
        select(RecipeIngredient.recipe_id, match_count)
        .where(RecipeIngredient.ingredient_id.in_(ingredient_ids))
        .group_by(RecipeIngredient.recipe_id)
        .order_by(match_count.desc())
        .limit(max(limit * 20, 200))
    )
    recipe_ids = [row[0] for row in session.execute(stmt)]
    if not recipe_ids:
        return []
    recipes = session.execute(
        select(Recipe)
        .where(Recipe.id.in_(recipe_ids))
        .options(selectinload(Recipe.ingredients).selectinload(RecipeIngredient.ingredient))
    ).scalars()
    return list(recipes)


def score_recipe(
    recipe: Recipe, stock: dict[int, StockLevel], recently_cooked: bool = False
) -> ScoredRecipe:
    matches: list[IngredientMatch] = []
    required_total = 0
    required_have = 0
    urgency_values: list[float] = []

    for line in recipe.ingredients:
        level = stock.get(line.ingredient_id) if line.ingredient_id else None
        available = None
        sufficient = False
        urgency = 0.0

        if level is not None:
            urgency = level.urgency
            if line.quantity is None:
                # No stated amount: having any stock at all counts.
                available = sum(i.quantity for i in level.items)
                sufficient = available > 0
            else:
                available = level.quantity_in(line.unit)
                if available is None:
                    # Units don't reconcile; treat presence as good enough rather
                    # than silently dropping a recipe the user can probably cook.
                    available = sum(i.quantity for i in level.items)
                    sufficient = available > 0
                else:
                    sufficient = available + 1e-6 >= line.quantity

        have = level is not None
        if not line.optional:
            required_total += 1
            if have:
                required_have += 1
                urgency_values.append(urgency)

        matches.append(
            IngredientMatch(
                recipe_ingredient=line,
                name=line.ingredient.display_name if line.ingredient else line.raw_text,
                raw_text=line.raw_text,
                have=have,
                optional=line.optional,
                quantity_needed=line.quantity,
                unit=line.unit,
                quantity_available=available,
                sufficient=sufficient,
                urgency=urgency,
            )
        )

    coverage = (required_have / required_total) if required_total else 0.0
    peak_urgency = max(urgency_values) if urgency_values else 0.0
    missing_count = required_total - required_have
    missing_penalty = min(missing_count / 5.0, 1.0)

    score = (
        W_COVERAGE * coverage
        + W_URGENCY * peak_urgency
        - W_MISSING * missing_penalty
    )
    if recently_cooked:
        score -= RECENT_COOK_PENALTY

    return ScoredRecipe(
        recipe=recipe,
        score=round(max(score, 0.0), 4),
        coverage=round(coverage, 4),
        urgency=round(peak_urgency, 4),
        matches=matches,
        recently_cooked=recently_cooked,
    )


def suggest(
    session: Session,
    limit: int = 10,
    *,
    min_coverage: float = 0.0,
    offset: int = 0,
    exclude_recent: bool = True,
) -> list[ScoredRecipe]:
    stock = stock_by_ingredient(session)
    recipes = _candidate_recipes(session, stock, limit + offset)
    recent = _recently_cooked_recipe_ids(session) if exclude_recent else set()

    scored = [score_recipe(r, stock, r.id in recent) for r in recipes]
    scored = [s for s in scored if s.coverage >= min_coverage and s.coverage > 0]
    scored.sort(key=lambda s: (s.score, s.coverage, s.urgency), reverse=True)
    return scored[offset : offset + limit]
