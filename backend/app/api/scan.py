from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.orm import Session

from app.api.inventory import create_item
from app.db import get_session
from app.schemas import (
    ExpiryCandidateOut,
    ExpiryScanOut,
    InventoryItemOut,
    ScanProductOut,
    ScanToInventoryRequest,
)
from app.services.barcode import lookup_barcode, remember_product
from app.services.ocr import ocr_available, parse_expiry_candidates, read_text

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


@router.post("/expiry", response_model=ExpiryScanOut)
async def scan_expiry(image: UploadFile = File(...)) -> ExpiryScanOut:
    """Read candidate expiry dates off a photo of a label.

    Returns available=false rather than an error when Tesseract is missing, so the
    UI can quietly fall back to the date picker instead of showing a failure.
    """
    if not ocr_available():
        return ExpiryScanOut(available=False)

    text = read_text(await image.read())
    return ExpiryScanOut(
        available=True,
        text=text.strip()[:2000],
        candidates=[
            ExpiryCandidateOut(date=c.value, hinted=c.hinted, text=c.source)
            for c in parse_expiry_candidates(text)[:5]
        ],
    )
