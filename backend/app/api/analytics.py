from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_session
from app.schemas import SummaryOut
from app.services import analytics

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/summary", response_model=SummaryOut)
def get_summary(
    session: Session = Depends(get_session), days: int = Query(default=30, ge=1, le=365)
) -> SummaryOut:
    result = analytics.summary(session, days)
    return SummaryOut(**result.__dict__)


@router.get("/spend-by-category")
def spend_by_category(
    session: Session = Depends(get_session), days: int = Query(default=30, ge=1, le=365)
) -> list[dict]:
    return analytics.spend_by_category(session, days)


@router.get("/spend-over-time")
def spend_over_time(
    session: Session = Depends(get_session), days: int = Query(default=90, ge=1, le=365)
) -> list[dict]:
    return analytics.spend_over_time(session, days)


@router.get("/most-wasted")
def most_wasted(
    session: Session = Depends(get_session), days: int = Query(default=90, ge=1, le=365)
) -> list[dict]:
    return analytics.most_wasted(session, days)


@router.get("/most-used")
def most_used(
    session: Session = Depends(get_session), days: int = Query(default=90, ge=1, le=365)
) -> list[dict]:
    return analytics.most_used(session, days)


@router.get("/recent-cooks")
def recent_cooks(
    session: Session = Depends(get_session), days: int = Query(default=28, ge=1, le=365)
) -> list[dict]:
    return analytics.recent_cooks(session, days)
