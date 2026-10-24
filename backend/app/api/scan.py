from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.inventory import create_item
from app.db import get_session
from app.schemas import InventoryItemOut, ScanProductOut, ScanToInventoryRequest
from app.services.barcode import lookup_barcode, remember_product

router = APIRouter(prefix="/api/scan", tags=["scan"])


@router.get("/barcode/{barcode}", response_model=ScanProductOut)
def scan_barcode(
    barcode: str,
    refresh: bool = Query(default=False, description="Ignore the cached entry and re-fetch"),
    session: Session = Depends(get_session),
) -> ScanProductOut:
    """Look a barcode up. An unknown code is a 200 with found=false, not an error."""
    info = lookup_barcode(session, barcode, refresh=refresh)
    return ScanProductOut(**asdict(info))


@router.post("/to-inventory", response_model=InventoryItemOut, status_code=201)
def scan_to_inventory(
    payload: ScanToInventoryRequest, session: Session = Depends(get_session)
) -> InventoryItemOut:
    """Add a scanned product to the kitchen and remember what that barcode really was."""
    item = create_item(payload, session=session)
    remember_product(
        session,
        payload.barcode,
        ingredient_id=item.ingredient.id,
        name=payload.ingredient_name,
        quantity=payload.quantity,
        unit=item.unit,
    )
    return item
