from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.serializers import recipe_summary
from app.db import get_session
from app.models import CookEvent, Recipe, RecipeIngredient
from app.schemas import (
    CookedLineOut,
    CookEventOut,
    CookRequest,
    CookResultOut,
    LeftoverUpdate,
    MatchOut,
    SuggestionOut,
)
from app.services.cooking import cook_recipe
from app.services.suggestions import IngredientMatch, ScoredRecipe, suggest

router = APIRouter(prefix="/api", tags=["suggestions"])


def _match_out(match: IngredientMatch) -> MatchOut:
    return MatchOut(
        name=match.name,
        raw_text=match.raw_text,
        have=match.have,
        optional=match.optional,
        sufficient=match.sufficient,
        quantity_needed=match.quantity_needed,
        unit=match.unit,
        quantity_available=(
            round(match.quantity_available, 2) if match.quantity_available is not None else None
        ),
        urgency=round(match.urgency, 3),
    )


def _suggestion_out(scored: ScoredRecipe) -> SuggestionOut:
    return SuggestionOut(
        recipe=recipe_summary(scored.recipe),
        score=scored.score,
        coverage=scored.coverage,
        urgency=scored.urgency,
        recently_cooked=scored.recently_cooked,
        have=[_match_out(m) for m in scored.have],
        missing=[_match_out(m) for m in scored.missing],
    )


@router.get("/suggestions", response_model=list[SuggestionOut])
def get_suggestions(
    session: Session = Depends(get_session),
    limit: int = Query(default=10, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    min_coverage: float = Query(default=0.0, ge=0.0, le=1.0),
    exclude_recent: bool = True,
) -> list[SuggestionOut]:
    results = suggest(
        session,
        limit=limit,
        offset=offset,
        min_coverage=min_coverage,
        exclude_recent=exclude_recent,
    )
    return [_suggestion_out(s) for s in results]


@router.post("/recipes/{recipe_id}/cook", response_model=CookResultOut)
def cook(
    recipe_id: int, payload: CookRequest, session: Session = Depends(get_session)
) -> CookResultOut:
    recipe = session.execute(
        select(Recipe)
        .where(Recipe.id == recipe_id)
        .options(selectinload(Recipe.ingredients).selectinload(RecipeIngredient.ingredient))
    ).unique().scalar_one_or_none()
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found")

    result = cook_recipe(
        session,
        recipe,
        servings_multiplier=payload.servings_multiplier,
        add_missing_to_grocery=payload.add_missing_to_grocery,
        note=payload.note,
    )
    session.flush()
    return CookResultOut(
        cook_event_id=result.event.id,
        recipe_title=recipe.title,
        consumed=[
            CookedLineOut(ingredient=c.ingredient, quantity=c.quantity, unit=c.unit)
            for c in result.consumed
        ],
        missing=result.missing,
        grocery_added=[g.label for g in result.grocery_added],
    )


@router.get("/cook-events", response_model=list[CookEventOut])
def list_cook_events(
    session: Session = Depends(get_session), limit: int = Query(default=50, ge=1, le=200)
) -> list[CookEventOut]:
    stmt = select(CookEvent).order_by(CookEvent.cooked_at.desc()).limit(limit)
    return list(session.execute(stmt).scalars())


@router.patch("/cook-events/{event_id}", response_model=CookEventOut)
def update_cook_event(
    event_id: int, payload: LeftoverUpdate, session: Session = Depends(get_session)
) -> CookEventOut:
    event = session.get(CookEvent, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Cook event not found")
    event.leftover_state = payload.leftover_state
    session.flush()
    return event
