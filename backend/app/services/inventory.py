"""Inventory levels, expiry classification, and the transaction ledger.

`InventoryItem.quantity` is a materialised current level; `InventoryTransaction` is the
append-only audit/analytics ledger. Every mutation goes through `apply_delta` so the two
can never drift apart.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    ExpiryBucket,
    Ingredient,
    InventoryItem,
    InventoryTransaction,
    ItemStatus,
    TransactionReason,
)
from app.services.units import try_convert

EPSILON = 1e-6


def expiry_bucket(expiry: date | None, today: date | None = None) -> ExpiryBucket:
    if expiry is None:
        return ExpiryBucket.NONE
    today = today or date.today()
    days_left = (expiry - today).days
    if days_left < 0:
        return ExpiryBucket.EXPIRED
    if days_left <= settings.expiry_critical_days:
        return ExpiryBucket.CRITICAL
    if days_left <= settings.expiry_soon_days:
        return ExpiryBucket.SOON
    return ExpiryBucket.OK


def days_left(expiry: date | None, today: date | None = None) -> int | None:
    if expiry is None:
        return None
    return (expiry - (today or date.today())).days


def urgency_score(expiry: date | None, today: date | None = None) -> float:
    """0 = not urgent, 1 = expired/expiring today. Drives recipe suggestion ranking."""
    remaining = days_left(expiry, today)
    if remaining is None:
        return 0.0
    if remaining <= 0:
        return 1.0
    horizon = max(settings.expiry_soon_days, 1)
    if remaining >= horizon * 2:
        return 0.0
    return max(0.0, 1.0 - (remaining / (horizon * 2)))


def apply_delta(
    session: Session,
    item: InventoryItem,
    delta_qty: float,
    reason: TransactionReason,
    *,
    unit: str | None = None,
    cost: float | None = None,
    recipe_id: int | None = None,
    cook_event_id: int | None = None,
    note: str | None = None,
) -> InventoryTransaction:
    """Change an item's quantity and record the matching ledger entry."""
    unit = unit or item.unit
    # Ledger entries are stored in the item's own unit so sums stay meaningful.
    if unit != item.unit:
        converted = try_convert(delta_qty, unit, item.unit, item.ingredient.density_g_per_ml)
        if converted is not None:
            delta_qty = converted
            unit = item.unit

    item.quantity = max(0.0, round(item.quantity + delta_qty, 6))
    if item.quantity <= EPSILON and item.status == ItemStatus.ACTIVE:
        item.status = (
            ItemStatus.DISCARDED if reason == TransactionReason.WASTE else ItemStatus.CONSUMED
        )
    elif item.quantity > EPSILON and item.status != ItemStatus.ACTIVE:
        item.status = ItemStatus.ACTIVE

    transaction = InventoryTransaction(
        inventory_item_id=item.id,
        ingredient_id=item.ingredient_id,
        delta_qty=delta_qty,
        unit=unit,
        reason=reason,
        cost=cost,
        recipe_id=recipe_id,
        cook_event_id=cook_event_id,
        note=note,
    )
    session.add(transaction)
    return transaction


def active_items(session: Session) -> list[InventoryItem]:
    stmt = (
        select(InventoryItem)
        .where(InventoryItem.status == ItemStatus.ACTIVE, InventoryItem.quantity > EPSILON)
        .order_by(InventoryItem.expiry_date.is_(None), InventoryItem.expiry_date)
    )
    return list(session.execute(stmt).unique().scalars())


@dataclass
class StockLevel:
    ingredient: Ingredient
    items: list[InventoryItem]

    @property
    def soonest_expiry(self) -> date | None:
        dates = [i.expiry_date for i in self.items if i.expiry_date is not None]
        return min(dates) if dates else None

    @property
    def urgency(self) -> float:
        return urgency_score(self.soonest_expiry)

    def quantity_in(self, unit: str | None) -> float | None:
        """Total stock expressed in `unit`, or None if nothing could be converted."""
        total = 0.0
        converted_any = False
        for item in self.items:
            value = try_convert(
                item.quantity, item.unit, unit, self.ingredient.density_g_per_ml
            )
            if value is not None:
                total += value
                converted_any = True
        return total if converted_any else None


def stock_by_ingredient(session: Session) -> dict[int, StockLevel]:
    grouped: dict[int, list[InventoryItem]] = defaultdict(list)
    for item in active_items(session):
        grouped[item.ingredient_id].append(item)
    levels: dict[int, StockLevel] = {}
    for ingredient_id, items in grouped.items():
        levels[ingredient_id] = StockLevel(ingredient=items[0].ingredient, items=items)
    return levels


def consume_ingredient(
    session: Session,
    level: StockLevel,
    quantity: float | None,
    unit: str | None,
    *,
    recipe_id: int | None = None,
    cook_event_id: int | None = None,
) -> list[tuple[InventoryItem, float]]:
    """Deduct a required amount FIFO by soonest expiry. Returns (item, amount) pairs."""
    # Expiring stock is used first, which is the whole point of the app.
    ordered = sorted(
        level.items,
        key=lambda i: (i.expiry_date is None, i.expiry_date or date.max, i.id),
    )
    consumed: list[tuple[InventoryItem, float]] = []

    if quantity is None:
        # Unquantified recipe line (e.g. "salt to taste"): don't guess, don't decrement.
        return consumed

    remaining = quantity
    for item in ordered:
        if remaining <= EPSILON:
            break
        available = try_convert(item.quantity, item.unit, unit, level.ingredient.density_g_per_ml)
        if available is None or available <= EPSILON:
            continue
        take = min(available, remaining)
        apply_delta(
            session,
            item,
            -take,
            TransactionReason.COOK,
            unit=unit,
            recipe_id=recipe_id,
            cook_event_id=cook_event_id,
        )
        consumed.append((item, take))
        remaining -= take
    return consumed
