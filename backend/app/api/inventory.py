from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.serializers import item_out
from app.db import get_session
from app.models import (
    ExpiryBucket,
    Ingredient,
    InventoryItem,
    InventoryTransaction,
    ItemStatus,
    TransactionReason,
)
from app.schemas import (
    IngredientOut,
    IngredientUpdate,
    InventoryAdjust,
    InventoryItemCreate,
    InventoryItemOut,
    InventoryItemUpdate,
    TransactionOut,
)
from app.services import grocery
from app.services.ingredients import IngredientResolver
from app.services.inventory import EPSILON, apply_delta, expiry_bucket
from app.services.units import normalize_unit

router = APIRouter(prefix="/api/inventory", tags=["inventory"])


@router.get("/items", response_model=list[InventoryItemOut])
def list_items(
    session: Session = Depends(get_session),
    status: ItemStatus | None = Query(default=ItemStatus.ACTIVE),
    bucket: ExpiryBucket | None = None,
    search: str | None = None,
    location: str | None = None,
) -> list[InventoryItemOut]:
    stmt = select(InventoryItem)
    if status is not None:
        stmt = stmt.where(InventoryItem.status == status)
    if location:
        stmt = stmt.where(InventoryItem.location == location)
    if search:
        stmt = stmt.join(Ingredient).where(Ingredient.display_name.ilike(f"%{search}%"))
    stmt = stmt.order_by(
        InventoryItem.expiry_date.is_(None), InventoryItem.expiry_date, InventoryItem.id
    )
    items = list(session.execute(stmt).unique().scalars())
    out = [item_out(i) for i in items]
    if bucket is not None:
        out = [i for i in out if i.expiry_bucket == bucket]
    return out


@router.get("/expiring", response_model=list[InventoryItemOut])
def expiring_items(
    session: Session = Depends(get_session), within_days: int = Query(default=5, ge=0)
) -> list[InventoryItemOut]:
    cutoff = date.today() + timedelta(days=within_days)
    stmt = (
        select(InventoryItem)
        .where(
            InventoryItem.status == ItemStatus.ACTIVE,
            InventoryItem.quantity > EPSILON,
            InventoryItem.expiry_date.is_not(None),
            InventoryItem.expiry_date <= cutoff,
        )
        .order_by(InventoryItem.expiry_date)
    )
    return [item_out(i) for i in session.execute(stmt).unique().scalars()]


@router.post("/items", response_model=InventoryItemOut, status_code=201)
def create_item(
    payload: InventoryItemCreate, session: Session = Depends(get_session)
) -> InventoryItemOut:
    resolver = IngredientResolver(session)
    match = resolver.resolve(payload.ingredient_name)
    if match.ingredient is None:
        raise HTTPException(status_code=400, detail="Could not interpret that ingredient name")

    ingredient = match.ingredient
    unit = normalize_unit(payload.unit)
    expiry = payload.expiry_date
    if expiry is None and ingredient.typical_shelf_life_days:
        expiry = (payload.purchase_date or date.today()) + timedelta(
            days=ingredient.typical_shelf_life_days
        )

    item = InventoryItem(
        ingredient_id=ingredient.id,
        quantity=0.0,
        unit=unit,
        purchase_date=payload.purchase_date or date.today(),
        expiry_date=expiry,
        location=payload.location,
        cost=payload.cost,
        notes=payload.notes,
        status=ItemStatus.ACTIVE,
    )
    session.add(item)
    session.flush()

    apply_delta(
        session,
        item,
        payload.quantity,
        TransactionReason.PURCHASE,
        unit=unit,
        cost=payload.cost,
    )
    if ingredient.default_unit is None:
        ingredient.default_unit = unit
    session.flush()
    return item_out(item)


@router.get("/items/{item_id}", response_model=InventoryItemOut)
def get_item(item_id: int, session: Session = Depends(get_session)) -> InventoryItemOut:
    item = session.get(InventoryItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return item_out(item)


@router.patch("/items/{item_id}", response_model=InventoryItemOut)
def update_item(
    item_id: int, payload: InventoryItemUpdate, session: Session = Depends(get_session)
) -> InventoryItemOut:
    item = session.get(InventoryItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")

    data = payload.model_dump(exclude_unset=True)
    new_quantity = data.pop("quantity", None)
    if "unit" in data and data["unit"]:
        data["unit"] = normalize_unit(data["unit"])
    for field, value in data.items():
        setattr(item, field, value)

    if new_quantity is not None:
        delta = new_quantity - item.quantity
        if abs(delta) > EPSILON:
            apply_delta(
                session,
                item,
                delta,
                TransactionReason.MANUAL_ADJUST,
                note="Edited via inventory form",
            )
    session.flush()
    return item_out(item)


@router.post("/items/{item_id}/adjust", response_model=InventoryItemOut)
def adjust_item(
    item_id: int, payload: InventoryAdjust, session: Session = Depends(get_session)
) -> InventoryItemOut:
    item = session.get(InventoryItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    apply_delta(session, item, payload.delta, payload.reason, unit=payload.unit, note=payload.note)
    session.flush()
    if item.quantity <= EPSILON:
        grocery.check_depletion(session, item.ingredient)
    return item_out(item)


@router.post("/items/{item_id}/discard", response_model=InventoryItemOut)
def discard_item(
    item_id: int, session: Session = Depends(get_session), note: str | None = None
) -> InventoryItemOut:
    """Throw an item away. Recorded as waste so it shows up in the analytics."""
    item = session.get(InventoryItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    if item.quantity > EPSILON:
        apply_delta(session, item, -item.quantity, TransactionReason.WASTE, note=note)
    item.status = ItemStatus.DISCARDED
    session.flush()
    grocery.check_depletion(session, item.ingredient)
    return item_out(item)


@router.post("/items/{item_id}/finish", response_model=InventoryItemOut)
def finish_item(item_id: int, session: Session = Depends(get_session)) -> InventoryItemOut:
    """Mark an item as fully used up."""
    item = session.get(InventoryItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    if item.quantity > EPSILON:
        apply_delta(session, item, -item.quantity, TransactionReason.COOK, note="Finished")
    item.status = ItemStatus.CONSUMED
    session.flush()
    grocery.check_depletion(session, item.ingredient)
    return item_out(item)


@router.delete("/items/{item_id}", status_code=204)
def delete_item(item_id: int, session: Session = Depends(get_session)) -> None:
    item = session.get(InventoryItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    session.delete(item)


@router.get("/items/{item_id}/transactions", response_model=list[TransactionOut])
def item_transactions(
    item_id: int, session: Session = Depends(get_session)
) -> list[TransactionOut]:
    stmt = (
        select(InventoryTransaction)
        .where(InventoryTransaction.inventory_item_id == item_id)
        .order_by(InventoryTransaction.created_at.desc())
    )
    return list(session.execute(stmt).scalars())


@router.get("/summary")
def inventory_summary(session: Session = Depends(get_session)) -> dict:
    stmt = select(InventoryItem).where(
        InventoryItem.status == ItemStatus.ACTIVE, InventoryItem.quantity > EPSILON
    )
    items = list(session.execute(stmt).unique().scalars())
    counts = {bucket.value: 0 for bucket in ExpiryBucket}
    for item in items:
        counts[expiry_bucket(item.expiry_date).value] += 1
    return {"total": len(items), "buckets": counts}


# --- Ingredient vocabulary -------------------------------------------------------

ingredients_router = APIRouter(prefix="/api/ingredients", tags=["ingredients"])


@ingredients_router.get("", response_model=list[IngredientOut])
def list_ingredients(
    session: Session = Depends(get_session),
    search: str | None = None,
    limit: int = Query(default=50, le=500),
) -> list[IngredientOut]:
    stmt = select(Ingredient)
    if search:
        stmt = stmt.where(Ingredient.display_name.ilike(f"%{search}%"))
    stmt = stmt.order_by(Ingredient.display_name).limit(limit)
    return list(session.execute(stmt).unique().scalars())


@ingredients_router.patch("/{ingredient_id}", response_model=IngredientOut)
def update_ingredient(
    ingredient_id: int, payload: IngredientUpdate, session: Session = Depends(get_session)
) -> IngredientOut:
    ingredient = session.get(Ingredient, ingredient_id)
    if ingredient is None:
        raise HTTPException(status_code=404, detail="Ingredient not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(ingredient, field, value)
    session.flush()
    return ingredient
