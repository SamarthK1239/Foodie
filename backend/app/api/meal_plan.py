from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.serializers import recipe_summary
from app.db import get_session
from app.models import MealPlanEntry, Recipe
from app.schemas import (
    MealPlanAdd,
    MealPlanEntryOut,
    MealPlanWeekOut,
    PlannedNeedOut,
)
from app.services import meal_plan

router = APIRouter(prefix="/api/meal-plan", tags=["meal-plan"])


def _entry_out(entry: MealPlanEntry) -> MealPlanEntryOut:
    return MealPlanEntryOut(
        id=entry.id,
        week_start=entry.week_start,
        servings_multiplier=entry.servings_multiplier,
        note=entry.note,
        recipe=recipe_summary(entry.recipe),
    )


@router.get("", response_model=MealPlanWeekOut)
def get_week(
    session: Session = Depends(get_session),
    week_start: date | None = Query(default=None),
) -> MealPlanWeekOut:
    start = meal_plan.week_start_for(week_start) if week_start else meal_plan.current_week_start()
    entries = meal_plan.entries_for_week(session, start)
    shortfalls = [
        PlannedNeedOut(
            ingredient_id=s.requirement.ingredient.id,
            name=s.requirement.ingredient.display_name,
            needed=s.requirement.quantity,
            unit=s.requirement.unit,
            in_stock=round(s.in_stock, 4),
            missing=round(s.missing, 4) if s.missing is not None else None,
            recipes=s.requirement.recipe_titles,
        )
        for s in meal_plan.week_shortfalls(session, start)
    ]
    return MealPlanWeekOut(
        week_start=start,
        week_end=start + timedelta(days=6),
        entries=[_entry_out(e) for e in entries],
        shortfalls=shortfalls,
    )


@router.post("", response_model=MealPlanEntryOut, status_code=201)
def add_entry(payload: MealPlanAdd, session: Session = Depends(get_session)) -> MealPlanEntryOut:
    recipe = session.get(Recipe, payload.recipe_id)
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found")
    start = (
        meal_plan.week_start_for(payload.week_start)
        if payload.week_start
        else meal_plan.current_week_start()
    )
    entry = meal_plan.add_to_week(
        session,
        recipe,
        week_start=start,
        servings_multiplier=payload.servings_multiplier,
        note=payload.note,
    )
    return _entry_out(entry)


@router.delete("/{entry_id}", status_code=204)
def remove_entry(entry_id: int, session: Session = Depends(get_session)) -> None:
    entry = session.get(MealPlanEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Plan entry not found")
    meal_plan.remove_from_week(session, entry)
