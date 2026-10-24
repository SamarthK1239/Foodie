from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import GroceryItem, GrocerySource, GroceryStatus
from app.schemas import GroceryItemCreate, GroceryItemOut, GroceryItemUpdate
from app.services import grocery
from app.services.ingredients import IngredientResolver
from app.services.units import normalize_unit

router = APIRouter(prefix="/api/grocery", tags=["grocery"])


@router.get("", response_model=list[GroceryItemOut])
def list_grocery(
    session: Session = Depends(get_session),
    status: GroceryStatus | None = Query(default=GroceryStatus.PENDING),
) -> list[GroceryItemOut]:
    stmt = select(GroceryItem)
    if status is not None:
        stmt = stmt.where(GroceryItem.status == status)
    stmt = stmt.order_by(GroceryItem.created_at.desc())
    return list(session.execute(stmt).scalars())


@router.post("", response_model=GroceryItemOut, status_code=201)
def add_grocery(
    payload: GroceryItemCreate, session: Session = Depends(get_session)
) -> GroceryItemOut:
    name = payload.ingredient_name or payload.label
    if not name:
        raise HTTPException(status_code=400, detail="Provide a label or ingredient name")

    unit = normalize_unit(payload.unit) if payload.unit else None
    match = IngredientResolver(session).resolve(name)
    if match.ingredient is None:
        item = GroceryItem(
            label=payload.label or name,
            quantity=payload.quantity,
            unit=unit,
            source=GrocerySource.MANUAL,
            note=payload.note,
        )
        session.add(item)
        session.flush()
        return item

    item = grocery.add_to_list(
        session,
        match.ingredient,
        source=GrocerySource.MANUAL,
        quantity=payload.quantity,
        unit=unit,
        note=payload.note,
    )
    if payload.label:
        item.label = payload.label
    session.flush()
    return item


@router.patch("/{item_id}", response_model=GroceryItemOut)
def update_grocery(
    item_id: int, payload: GroceryItemUpdate, session: Session = Depends(get_session)
) -> GroceryItemOut:
    item = session.get(GroceryItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Grocery item not found")
    data = payload.model_dump(exclude_unset=True)
    status = data.pop("status", None)
    if "unit" in data and data["unit"]:
        data["unit"] = normalize_unit(data["unit"])
    for field, value in data.items():
        setattr(item, field, value)
    if status is not None:
        grocery.resolve(session, item, status)
    session.flush()
    return item


@router.delete("/{item_id}", status_code=204)
def delete_grocery(item_id: int, session: Session = Depends(get_session)) -> None:
    item = session.get(GroceryItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Grocery item not found")
    session.delete(item)


@router.post("/clear-purchased", status_code=204)
def clear_purchased(session: Session = Depends(get_session)) -> None:
    stmt = select(GroceryItem).where(GroceryItem.status == GroceryStatus.PURCHASED)
    for item in session.execute(stmt).scalars():
        session.delete(item)
