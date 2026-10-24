"""Consumption, spend and waste analytics derived from the transaction ledger."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    CookEvent,
    ExpiryBucket,
    Ingredient,
    InventoryItem,
    InventoryTransaction,
    ItemStatus,
    TransactionReason,
)
from app.services.inventory import EPSILON, active_items, expiry_bucket


def _window_start(days: int) -> datetime:
    return datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days)


@dataclass
class Summary:
    period_days: int
    total_spend: float
    items_purchased: int
    items_consumed: int
    items_discarded: int
    waste_rate: float
    active_items: int
    expiring_soon: int
    dishes_cooked: int


def summary(session: Session, days: int = 30) -> Summary:
    start = _window_start(days)

    spend = session.execute(
        select(func.coalesce(func.sum(InventoryItem.cost), 0.0)).where(
            InventoryItem.created_at >= start, InventoryItem.cost.is_not(None)
        )
    ).scalar_one()

    purchased = session.execute(
        select(func.count()).select_from(InventoryItem).where(InventoryItem.created_at >= start)
    ).scalar_one()

    consumed = session.execute(
        select(func.count())
        .select_from(InventoryItem)
        .where(InventoryItem.updated_at >= start, InventoryItem.status == ItemStatus.CONSUMED)
    ).scalar_one()

    discarded = session.execute(
        select(func.count())
        .select_from(InventoryItem)
        .where(InventoryItem.updated_at >= start, InventoryItem.status == ItemStatus.DISCARDED)
    ).scalar_one()

    active = session.execute(
        select(func.count())
        .select_from(InventoryItem)
        .where(InventoryItem.status == ItemStatus.ACTIVE)
    ).scalar_one()

    cooked = session.execute(
        select(func.count()).select_from(CookEvent).where(CookEvent.cooked_at >= start)
    ).scalar_one()

    resolved = consumed + discarded
    waste_rate = (discarded / resolved) if resolved else 0.0

    expiring = sum(
        1
        for item in active_items(session)
        if expiry_bucket(item.expiry_date)
        in (ExpiryBucket.EXPIRED, ExpiryBucket.CRITICAL, ExpiryBucket.SOON)
    )

    return Summary(
        period_days=days,
        total_spend=round(float(spend), 2),
        items_purchased=purchased,
        items_consumed=consumed,
        items_discarded=discarded,
        waste_rate=round(waste_rate, 4),
        active_items=active,
        expiring_soon=expiring,
        dishes_cooked=cooked,
    )


def spend_by_category(session: Session, days: int = 30) -> list[dict]:
    start = _window_start(days)
    stmt = (
        select(
            func.coalesce(Ingredient.category, "uncategorised").label("category"),
            func.coalesce(func.sum(InventoryItem.cost), 0.0).label("total"),
            func.count().label("count"),
        )
        .select_from(InventoryItem)
        .join(Ingredient, Ingredient.id == InventoryItem.ingredient_id)
        .where(InventoryItem.created_at >= start, InventoryItem.cost.is_not(None))
        .group_by("category")
        .order_by(func.sum(InventoryItem.cost).desc())
    )
    return [
        {"category": row.category, "total": round(float(row.total), 2), "count": row.count}
        for row in session.execute(stmt)
    ]


def spend_over_time(session: Session, days: int = 90) -> list[dict]:
    start = _window_start(days)
    bucket = func.strftime("%Y-%W", InventoryItem.created_at).label("week")
    stmt = (
        select(bucket, func.coalesce(func.sum(InventoryItem.cost), 0.0).label("total"))
        .where(InventoryItem.created_at >= start, InventoryItem.cost.is_not(None))
        .group_by(bucket)
        .order_by(bucket)
    )
    return [
        {"period": row.week, "total": round(float(row.total), 2)}
        for row in session.execute(stmt)
    ]


def most_wasted(session: Session, days: int = 90, limit: int = 10) -> list[dict]:
    start = _window_start(days)
    stmt = (
        select(
            Ingredient.display_name.label("name"),
            func.count().label("times"),
            func.coalesce(func.sum(InventoryItem.cost), 0.0).label("cost"),
        )
        .select_from(InventoryItem)
        .join(Ingredient, Ingredient.id == InventoryItem.ingredient_id)
        .where(
            InventoryItem.status == ItemStatus.DISCARDED,
            InventoryItem.updated_at >= start,
        )
        .group_by(Ingredient.id)
        .order_by(func.count().desc())
        .limit(limit)
    )
    return [
        {"name": row.name, "times": row.times, "cost": round(float(row.cost), 2)}
        for row in session.execute(stmt)
    ]


def most_used(session: Session, days: int = 90, limit: int = 10) -> list[dict]:
    start = _window_start(days)
    stmt = (
        select(
            Ingredient.display_name.label("name"),
            func.count().label("times"),
        )
        .select_from(InventoryTransaction)
        .join(Ingredient, Ingredient.id == InventoryTransaction.ingredient_id)
        .where(
            InventoryTransaction.reason == TransactionReason.COOK,
            InventoryTransaction.created_at >= start,
        )
        .group_by(Ingredient.id)
        .order_by(func.count().desc())
        .limit(limit)
    )
    return [{"name": row.name, "times": row.times} for row in session.execute(stmt)]


def recent_cooks(session: Session, days: int = 28, limit: int = 50) -> list[dict]:
    start = _window_start(days)
    stmt = (
        select(CookEvent)
        .where(CookEvent.cooked_at >= start)
        .order_by(CookEvent.cooked_at.desc())
        .limit(limit)
    )
    return [
        {
            "id": e.id,
            "recipe_id": e.recipe_id,
            "title": e.recipe_title,
            "cooked_at": e.cooked_at.isoformat(),
            "leftover_state": e.leftover_state,
        }
        for e in session.execute(stmt).scalars()
    ]


# --- Two-week period review ------------------------------------------------------


@dataclass
class PeriodReview:
    weeks: int
    period_days: int
    start: str
    end: str
    used: list[dict]
    unused: list[dict]
    wasted: list[dict]
    suggested: list[dict]


def _used_in_window(session: Session, start: datetime) -> list[dict]:
    """Ingredients actually cooked with during the window, most-used first."""
    stmt = (
        select(
            Ingredient.id.label("ingredient_id"),
            Ingredient.display_name.label("name"),
            func.count().label("times"),
            func.coalesce(func.sum(-InventoryTransaction.delta_qty), 0.0).label("quantity"),
        )
        .select_from(InventoryTransaction)
        .join(Ingredient, Ingredient.id == InventoryTransaction.ingredient_id)
        .where(
            InventoryTransaction.reason == TransactionReason.COOK,
            InventoryTransaction.created_at >= start,
        )
        .group_by(Ingredient.id)
        .order_by(func.count().desc(), Ingredient.display_name)
    )
    return [
        {
            "ingredient_id": row.ingredient_id,
            "name": row.name,
            "times": row.times,
            "quantity": round(float(row.quantity), 2),
        }
        for row in session.execute(stmt)
    ]


def _wasted_in_window(session: Session, start: datetime) -> list[dict]:
    stmt = (
        select(
            Ingredient.id.label("ingredient_id"),
            Ingredient.display_name.label("name"),
            func.count().label("times"),
            func.coalesce(func.sum(InventoryItem.cost), 0.0).label("cost"),
        )
        .select_from(InventoryItem)
        .join(Ingredient, Ingredient.id == InventoryItem.ingredient_id)
        .where(
            InventoryItem.status == ItemStatus.DISCARDED,
            InventoryItem.updated_at >= start,
        )
        .group_by(Ingredient.id)
        .order_by(func.count().desc(), Ingredient.display_name)
    )
    return [
        {
            "ingredient_id": row.ingredient_id,
            "name": row.name,
            "times": row.times,
            "cost": round(float(row.cost), 2),
        }
        for row in session.execute(stmt)
    ]


def _unused_in_window(session: Session, start: datetime) -> list[dict]:
    """Stock that was already in the kitchen when the period began and never got touched.

    These are the items quietly heading for the bin, so they are the ones worth
    cooking next rather than buying again.
    """
    touched = select(InventoryTransaction.ingredient_id).where(
        InventoryTransaction.created_at >= start,
        InventoryTransaction.reason.in_((TransactionReason.COOK, TransactionReason.WASTE)),
    )
    stmt = (
        select(InventoryItem)
        .where(
            InventoryItem.status == ItemStatus.ACTIVE,
            InventoryItem.created_at < start,
            InventoryItem.ingredient_id.not_in(touched),
        )
        .order_by(InventoryItem.expiry_date.is_(None), InventoryItem.expiry_date)
    )
    now = datetime.now(UTC).replace(tzinfo=None)
    return [
        {
            "ingredient_id": item.ingredient_id,
            "item_id": item.id,
            "name": item.ingredient.display_name,
            "quantity": round(float(item.quantity), 2),
            "unit": item.unit,
            "days_in_stock": max((now - item.created_at).days, 0),
            "expiry_bucket": expiry_bucket(item.expiry_date),
        }
        for item in session.execute(stmt).unique().scalars()
    ]


def _suggested_restock(
    session: Session, used: list[dict], wasted: list[dict]
) -> list[dict]:
    """What to buy again: things cooked with this period that have now run out.

    Anything binned during the same period is deliberately left off. If it went
    in the bin, buying more of it is how the waste repeats.
    """
    from app.services import grocery as grocery_service

    wasted_ids = {row["ingredient_id"] for row in wasted}
    suggestions = []
    for row in used:
        if row["ingredient_id"] in wasted_ids:
            continue
        ingredient = session.get(Ingredient, row["ingredient_id"])
        if ingredient is None:
            continue
        unit = ingredient.restock_unit or ingredient.default_unit
        remaining = grocery_service.remaining_quantity(session, ingredient.id, unit)
        threshold = ingredient.restock_threshold or 0.0
        if remaining > max(threshold, EPSILON):
            continue
        # Running out usually auto-adds the item already; say so rather than
        # implying the review found something new.
        already_listed = grocery_service.pending_entry(session, ingredient.id) is not None
        suggestions.append(
            {
                "ingredient_id": ingredient.id,
                "name": ingredient.display_name,
                "times_used": row["times"],
                "remaining": round(float(remaining), 2),
                "unit": unit,
                "reason": "out_of_stock" if remaining <= EPSILON else "low_stock",
                "already_on_list": already_listed,
            }
        )
    return suggestions


def period_review(session: Session, weeks: int = 2) -> PeriodReview:
    days = weeks * 7
    start = _window_start(days)
    used = _used_in_window(session, start)
    wasted = _wasted_in_window(session, start)
    return PeriodReview(
        weeks=weeks,
        period_days=days,
        start=start.isoformat(),
        end=datetime.now(UTC).replace(tzinfo=None).isoformat(),
        used=used,
        unused=_unused_in_window(session, start),
        wasted=wasted,
        suggested=_suggested_restock(session, used, wasted),
    )


def apply_period_review(session: Session, ingredient_ids: list[int]) -> list[int]:
    """Push the chosen restock suggestions onto the grocery list."""
    from app.models import GrocerySource
    from app.services import grocery as grocery_service

    added = []
    for ingredient_id in ingredient_ids:
        ingredient = session.get(Ingredient, ingredient_id)
        if ingredient is None:
            continue
        item = grocery_service.add_to_list(
            session,
            ingredient,
            source=GrocerySource.PERIOD_REVIEW,
            quantity=ingredient.restock_threshold,
            unit=ingredient.restock_unit or ingredient.default_unit,
            note="From your 2-week review",
        )
        added.append(item.id)
    return added
