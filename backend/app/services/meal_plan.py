"""Weekly meal planning: what you intend to cook, and what you must buy for it.

The grocery rows this produces are *derived state*. They are rebuilt from the
plan on every change rather than edited incrementally, which is what keeps
adding and removing a recipe symmetrical.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    GroceryItem,
    GrocerySource,
    GroceryStatus,
    Ingredient,
    MealPlanEntry,
    Recipe,
)
from app.services.grocery import remaining_quantity
from app.services.inventory import EPSILON
from app.services.units import try_convert


def week_start_for(day: date) -> date:
    """The Monday of the week containing `day`."""
    return day - timedelta(days=day.weekday())


def current_week_start() -> date:
    return week_start_for(date.today())


@dataclass
class Requirement:
    """How much of one ingredient the whole week's plan calls for."""

    ingredient: Ingredient
    quantity: float | None
    unit: str | None
    recipe_titles: list[str]


@dataclass
class Shortfall:
    requirement: Requirement
    in_stock: float
    missing: float | None


def entries_for_week(session: Session, week_start: date) -> list[MealPlanEntry]:
    stmt = (
        select(MealPlanEntry)
        .where(MealPlanEntry.week_start == week_start)
        .order_by(MealPlanEntry.created_at)
    )
    return list(session.execute(stmt).unique().scalars())


def week_requirements(session: Session, week_start: date) -> list[Requirement]:
    """Total each ingredient across every recipe planned for the week.

    Summing matters here in a way it does not for a single recipe: three dishes
    that each want 200g of pasta need 600g, and a plan that only asks for 200g
    sends you home short.
    """
    quantities: dict[int, float] = defaultdict(float)
    units: dict[int, str | None] = {}
    ingredients: dict[int, Ingredient] = {}
    titles: dict[int, list[str]] = defaultdict(list)
    # Ingredients we know are needed but could not total, because a line had no
    # quantity or used a unit that will not convert ("2 cloves" vs "30 g").
    unquantified: set[int] = set()

    for entry in entries_for_week(session, week_start):
        for line in entry.recipe.ingredients:
            if line.ingredient_id is None or line.optional:
                continue
            key = line.ingredient_id
            ingredients.setdefault(key, line.ingredient)
            if entry.recipe.title not in titles[key]:
                titles[key].append(entry.recipe.title)

            if line.quantity is None:
                unquantified.add(key)
                continue

            needed = line.quantity * entry.servings_multiplier
            if key not in units:
                units[key] = line.unit or line.ingredient.default_unit

            target = units[key]
            converted = (
                needed
                if line.unit == target
                else try_convert(needed, line.unit, target, line.ingredient.density_g_per_ml)
            )
            if converted is None:
                unquantified.add(key)
                continue
            quantities[key] += converted

    requirements: list[Requirement] = []
    for key, ingredient in ingredients.items():
        total = quantities.get(key)
        # A partial total is worse than none: it would read as the full week's
        # need while silently omitting the lines that would not convert.
        quantity = None if key in unquantified or not total else total
        requirements.append(
            Requirement(
                ingredient=ingredient,
                quantity=quantity,
                unit=units.get(key) if quantity is not None else None,
                recipe_titles=titles[key],
            )
        )
    requirements.sort(key=lambda r: r.ingredient.display_name.lower())
    return requirements


def week_shortfalls(session: Session, week_start: date) -> list[Shortfall]:
    """What the week needs that the kitchen cannot currently cover."""
    shortfalls: list[Shortfall] = []
    for requirement in week_requirements(session, week_start):
        in_stock = remaining_quantity(session, requirement.ingredient.id, requirement.unit)
        if requirement.quantity is None:
            # Cannot compare amounts, so fall back to presence: you need it, do
            # you have any at all?
            if in_stock <= EPSILON:
                shortfalls.append(Shortfall(requirement, in_stock, None))
            continue
        missing = requirement.quantity - in_stock
        if missing > EPSILON:
            shortfalls.append(Shortfall(requirement, in_stock, missing))
    return shortfalls


def _pending_for_ingredient(session: Session, ingredient_id: int) -> list[GroceryItem]:
    stmt = select(GroceryItem).where(
        GroceryItem.ingredient_id == ingredient_id,
        GroceryItem.status == GroceryStatus.PENDING,
    )
    return list(session.execute(stmt).scalars())


def sync_plan_groceries(session: Session) -> list[GroceryItem]:
    """Rebuild the meal-plan grocery rows from the current week's plan.

    Derived from the current week only: you shop for the week you are in, so a
    recipe planned three weeks out should not put anything in this week's
    basket. That makes the result a pure function of (plan, today), which is
    what lets this be re-run after any change rather than patched incrementally.

    Only rows this function created are touched. Rows from depletion, a recipe
    gap or manual entry are left exactly as they are: raising someone else's
    quantity here would ratchet it upward on every recompute and never come back
    down, and an ingredient already on the list does not need a second row.
    """
    existing = list(
        session.execute(
            select(GroceryItem).where(
                GroceryItem.source == GrocerySource.MEAL_PLAN,
                GroceryItem.status == GroceryStatus.PENDING,
            )
        ).scalars()
    )
    for row in existing:
        session.delete(row)
    session.flush()

    added: list[GroceryItem] = []
    for shortfall in week_shortfalls(session, current_week_start()):
        ingredient = shortfall.requirement.ingredient
        if _pending_for_ingredient(session, ingredient.id):
            continue
        item = GroceryItem(
            ingredient_id=ingredient.id,
            label=ingredient.display_name,
            quantity=round(shortfall.missing, 4) if shortfall.missing is not None else None,
            unit=shortfall.requirement.unit,
            source=GrocerySource.MEAL_PLAN,
            status=GroceryStatus.PENDING,
            note=f"Planned: {', '.join(shortfall.requirement.recipe_titles)}",
        )
        session.add(item)
        added.append(item)

    session.flush()
    return added


def add_to_week(
    session: Session,
    recipe: Recipe,
    *,
    week_start: date,
    servings_multiplier: float = 1.0,
    note: str | None = None,
) -> MealPlanEntry:
    """Plan a recipe. Re-planning the same recipe adjusts the batch size."""
    existing = session.execute(
        select(MealPlanEntry).where(
            MealPlanEntry.recipe_id == recipe.id,
            MealPlanEntry.week_start == week_start,
        )
    ).scalar_one_or_none()

    if existing is not None:
        existing.servings_multiplier = servings_multiplier
        if note is not None:
            existing.note = note
        entry = existing
    else:
        entry = MealPlanEntry(
            recipe_id=recipe.id,
            week_start=week_start,
            servings_multiplier=servings_multiplier,
            note=note,
        )
        session.add(entry)
    session.flush()

    sync_plan_groceries(session)
    return entry


def remove_from_week(session: Session, entry: MealPlanEntry) -> None:
    session.delete(entry)
    session.flush()
    sync_plan_groceries(session)
