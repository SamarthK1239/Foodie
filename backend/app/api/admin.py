from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_session
from app.ingest import runner
from app.ingest.parsing import clean_ingredient_name, normalize_ingredient_key
from app.models import (
    IngestJob,
    IngestMode,
    IngestStatus,
    Ingredient,
    IngredientAlias,
    Recipe,
    RecipeIngredient,
)
from app.schemas import (
    IngestJobOut,
    IngestStartRequest,
    ResolveUnmatchedRequest,
    UnmatchedLineOut,
)
from app.services.ingredients import IngredientResolver

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/ingest/jobs", response_model=list[IngestJobOut])
def list_jobs(
    session: Session = Depends(get_session), limit: int = Query(default=10, ge=1, le=50)
) -> list[IngestJobOut]:
    stmt = select(IngestJob).order_by(IngestJob.id.desc()).limit(limit)
    return list(session.execute(stmt).scalars())


@router.get("/ingest/status")
def ingest_status(session: Session = Depends(get_session)) -> dict:
    job = runner.latest_job(session)
    return {
        "running": runner.is_running(),
        "job": IngestJobOut.model_validate(job).model_dump() if job else None,
        "configured_sites": settings.scrape_sites,
    }


@router.post("/ingest/start", response_model=IngestJobOut, status_code=202)
def start_ingest(
    payload: IngestStartRequest, session: Session = Depends(get_session)
) -> IngestJobOut:
    if runner.is_running():
        raise HTTPException(status_code=409, detail="An ingest job is already running")

    sites = payload.sites if payload.sites is not None else settings.scrape_sites
    if payload.mode != IngestMode.REVALIDATE and not sites:
        raise HTTPException(status_code=400, detail="No sites configured to crawl")

    job = runner.create_job(
        session,
        mode=payload.mode,
        sites=sites,
        target=payload.max_recipes or settings.scrape_max_recipes,
        revalidate_older_than_days=payload.revalidate_older_than_days,
    )
    session.commit()
    runner.start_job_async(job.id)
    return job


@router.post("/ingest/cancel", response_model=IngestJobOut)
def cancel_ingest(session: Session = Depends(get_session)) -> IngestJobOut:
    job = runner.active_job(session)
    if job is None:
        raise HTTPException(status_code=404, detail="No active ingest job")
    job.status = IngestStatus.CANCELLED
    session.flush()
    return job


@router.get("/unmatched-ingredients", response_model=list[UnmatchedLineOut])
def unmatched_ingredients(
    session: Session = Depends(get_session), limit: int = Query(default=50, ge=1, le=500)
) -> list[UnmatchedLineOut]:
    """Recipe lines we could not map onto a canonical ingredient.

    These silently degrade suggestion quality, so they get an explicit review queue.
    """
    stmt = (
        select(RecipeIngredient, Recipe.title)
        .join(Recipe, Recipe.id == RecipeIngredient.recipe_id)
        .where(RecipeIngredient.ingredient_id.is_(None))
        .limit(limit)
    )
    resolver = IngredientResolver(session)
    results = []
    for line, title in session.execute(stmt):
        match = resolver.match(line.raw_text)
        results.append(
            UnmatchedLineOut(
                recipe_id=line.recipe_id,
                recipe_title=title,
                recipe_ingredient_id=line.id,
                raw_text=line.raw_text,
                suggestion=match.ingredient.display_name if match.ingredient else None,
            )
        )
    return results


@router.post("/unmatched-ingredients/resolve")
def resolve_unmatched(
    payload: ResolveUnmatchedRequest, session: Session = Depends(get_session)
) -> dict:
    line = session.get(RecipeIngredient, payload.recipe_ingredient_id)
    if line is None:
        raise HTTPException(status_code=404, detail="Recipe ingredient not found")

    resolver = IngredientResolver(session)
    match = resolver.resolve(payload.ingredient_name)
    if match.ingredient is None:
        raise HTTPException(status_code=400, detail="Could not interpret that ingredient name")

    line.ingredient_id = match.ingredient.id

    linked = 0
    if payload.add_alias:
        alias_key = normalize_ingredient_key(clean_ingredient_name(line.raw_text))
        if alias_key and alias_key != match.ingredient.name:
            exists = session.execute(
                select(IngredientAlias).where(IngredientAlias.alias == alias_key)
            ).scalars().first()
            if exists is None:
                session.add(
                    IngredientAlias(ingredient_id=match.ingredient.id, alias=alias_key)
                )
                session.flush()
                # Apply the new alias to every other line with the same text.
                others = session.execute(
                    select(RecipeIngredient).where(
                        RecipeIngredient.ingredient_id.is_(None),
                        RecipeIngredient.raw_text == line.raw_text,
                    )
                ).scalars()
                for other in others:
                    other.ingredient_id = match.ingredient.id
                    linked += 1

    session.flush()
    return {
        "ingredient_id": match.ingredient.id,
        "ingredient": match.ingredient.display_name,
        "also_linked": linked,
    }


@router.get("/stats")
def admin_stats(session: Session = Depends(get_session)) -> dict:
    recipes = session.execute(select(func.count()).select_from(Recipe)).scalar_one()
    ingredients = session.execute(select(func.count()).select_from(Ingredient)).scalar_one()
    unmatched = session.execute(
        select(func.count())
        .select_from(RecipeIngredient)
        .where(RecipeIngredient.ingredient_id.is_(None))
    ).scalar_one()
    return {
        "recipes": recipes,
        "ingredients": ingredients,
        "unmatched_recipe_lines": unmatched,
        "database_path": str(settings.db_path),
    }
