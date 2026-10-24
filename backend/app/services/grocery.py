"""Grocery list: auto-populated when stock runs out or a recipe can't be completed."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    GroceryItem,
    GrocerySource,
    GroceryStatus,
    Ingredient,
    InventoryItem,
    ItemStatus,
)
from app.models.entities import utcnow
from app.services.inventory import EPSILON
from app.services.units import try_convert


def _existing_pending(session: Session, ingredient_id: int) -> GroceryItem | None:
    stmt = select(GroceryItem).where(
        GroceryItem.ingredient_id == ingredient_id,
        GroceryItem.status == GroceryStatus.PENDING,
    )
    return session.execute(stmt).scalars().first()


def pending_entry(session: Session, ingredient_id: int) -> GroceryItem | None:
    """Public read-only view of whether an ingredient is already on the list."""
    return _existing_pending(session, ingredient_id)


def remaining_quantity(session: Session, ingredient_id: int, unit: str | None) -> float:
    """Total active stock of an ingredient, expressed in `unit` where possible."""
    stmt = select(InventoryItem).where(
        InventoryItem.ingredient_id == ingredient_id,
        InventoryItem.status == ItemStatus.ACTIVE,
        InventoryItem.quantity > EPSILON,
    )
    items = list(session.execute(stmt).unique().scalars())
    if not items:
        return 0.0
    density = items[0].ingredient.density_g_per_ml
    total = 0.0
    for item in items:
        value = try_convert(item.quantity, item.unit, unit, density)
        total += value if value is not None else item.quantity
    return total


def add_to_list(
    session: Session,
    ingredient: Ingredient,
    *,
    source: GrocerySource,
    quantity: float | None = None,
    unit: str | None = None,
    note: str | None = None,
) -> GroceryItem:
    """Add an ingredient to the pending list, merging with any existing pending entry."""
    existing = _existing_pending(session, ingredient.id)
    if existing is not None:
        if quantity is not None:
            if existing.quantity is None:
                existing.quantity, existing.unit = quantity, unit
            else:
                converted = try_convert(
                    quantity, unit, existing.unit, ingredient.density_g_per_ml
                )
                # Keep the larger requirement rather than double-counting overlapping needs.
                if converted is not None:
                    existing.quantity = max(existing.quantity, converted)
        if note and note not in (existing.note or ""):
            existing.note = f"{existing.note}; {note}" if existing.note else note
        return existing

    item = GroceryItem(
        ingredient_id=ingredient.id,
        label=ingredient.display_name,
        quantity=quantity,
        unit=unit,
        source=source,
        status=GroceryStatus.PENDING,
        note=note,
    )
    session.add(item)
    session.flush()
    return item


def check_depletion(session: Session, ingredient: Ingredient) -> GroceryItem | None:
    """Auto-add an ingredient once stock hits zero or falls under its restock threshold."""
    threshold_unit = ingredient.restock_unit or ingredient.default_unit
    remaining = remaining_quantity(session, ingredient.id, threshold_unit)
    threshold = ingredient.restock_threshold if ingredient.restock_threshold else EPSILON

    if remaining > threshold:
        return None

    note = (
        "Out of stock"
        if remaining <= EPSILON
        else f"Low stock ({remaining:g} {threshold_unit or ''})".strip()
    )
    return add_to_list(
        session,
        ingredient,
        source=GrocerySource.AUTO_DEPLETED,
        quantity=ingredient.restock_threshold,
        unit=threshold_unit,
        note=note,
    )


def add_recipe_gaps(
    session: Session,
    missing: list[tuple[Ingredient, float | None, str | None]],
    recipe_title: str,
) -> list[GroceryItem]:
    added = []
    for ingredient, quantity, unit in missing:
        added.append(
            add_to_list(
                session,
                ingredient,
                source=GrocerySource.RECIPE_GAP,
                quantity=quantity,
                unit=unit,
                note=f"For {recipe_title}",
            )
        )
    return added


def resolve(session: Session, item: GroceryItem, status: GroceryStatus) -> GroceryItem:
    item.status = status
    item.resolved_at = utcnow() if status != GroceryStatus.PENDING else None
    return item
