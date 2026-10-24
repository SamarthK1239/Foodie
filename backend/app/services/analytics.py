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
from app.services.inventory import active_items, expiry_bucket


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
