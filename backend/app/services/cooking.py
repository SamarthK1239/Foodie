"""Cooking a recipe: decrement stock FIFO by expiry and record what happened."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import CookEvent, GroceryItem, Ingredient, Recipe
from app.services import grocery
from app.services.inventory import consume_ingredient, stock_by_ingredient


@dataclass
class ConsumedLine:
    ingredient: str
    quantity: float
    unit: str | None
    item_id: int


@dataclass
class CookResult:
    event: CookEvent
    consumed: list[ConsumedLine]
    missing: list[str]
    grocery_added: list[GroceryItem]


def cook_recipe(
    session: Session,
    recipe: Recipe,
    *,
    servings_multiplier: float = 1.0,
    add_missing_to_grocery: bool = True,
    note: str | None = None,
) -> CookResult:
    stock = stock_by_ingredient(session)

    event = CookEvent(
        recipe_id=recipe.id,
        recipe_title=recipe.title,
        servings=(recipe.servings or 1) * servings_multiplier,
        note=note,
    )
    session.add(event)
    session.flush()

    consumed: list[ConsumedLine] = []
    missing_names: list[str] = []
    missing_for_grocery: list[tuple[Ingredient, float | None, str | None]] = []
    touched: dict[int, Ingredient] = {}

    for line in recipe.ingredients:
        level = stock.get(line.ingredient_id) if line.ingredient_id else None
        if level is None:
            if not line.optional:
                missing_names.append(
                    line.ingredient.display_name if line.ingredient else line.raw_text
                )
                if line.ingredient is not None:
                    needed = (line.quantity * servings_multiplier) if line.quantity else None
                    missing_for_grocery.append((line.ingredient, needed, line.unit))
            continue

        needed = (line.quantity * servings_multiplier) if line.quantity is not None else None
        taken = consume_ingredient(
            session,
            level,
            needed,
            line.unit,
            recipe_id=recipe.id,
            cook_event_id=event.id,
        )
        for item, amount in taken:
            consumed.append(
                ConsumedLine(
                    ingredient=level.ingredient.display_name,
                    quantity=round(amount, 4),
                    unit=line.unit,
                    item_id=item.id,
                )
            )
        touched[level.ingredient.id] = level.ingredient

    session.flush()

    added: list[GroceryItem] = []
    if add_missing_to_grocery and missing_for_grocery:
        added.extend(grocery.add_recipe_gaps(session, missing_for_grocery, recipe.title))

    # Anything we just drained should land on the grocery list automatically.
    for ingredient in touched.values():
        entry = grocery.check_depletion(session, ingredient)
        if entry is not None and entry not in added:
            added.append(entry)

    return CookResult(event=event, consumed=consumed, missing=missing_names, grocery_added=added)
