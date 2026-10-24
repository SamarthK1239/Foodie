from __future__ import annotations

import json

from app.models import Recipe
from app.schemas import (
    InventoryItemOut,
    RecipeOut,
    RecipeSummary,
)
from app.services.inventory import days_left, expiry_bucket


def load_tags(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except (ValueError, TypeError):
        return [t.strip() for t in raw.split(",") if t.strip()]
    if isinstance(value, list):
        return [str(v) for v in value]
    return []


def dump_tags(tags: list[str] | None) -> str | None:
    if tags is None:
        return None
    return json.dumps(sorted({t.strip() for t in tags if t and t.strip()}))


def item_out(item) -> InventoryItemOut:
    return InventoryItemOut(
        id=item.id,
        ingredient=item.ingredient,
        quantity=item.quantity,
        unit=item.unit,
        purchase_date=item.purchase_date,
        expiry_date=item.expiry_date,
        opened_at=item.opened_at,
        location=item.location,
        cost=item.cost,
        status=item.status,
        notes=item.notes,
        expiry_bucket=expiry_bucket(item.expiry_date),
        days_left=days_left(item.expiry_date),
    )


def recipe_summary(recipe: Recipe) -> RecipeSummary:
    return RecipeSummary(
        id=recipe.id,
        title=recipe.title,
        source_site=recipe.source_site,
        source_url=recipe.source_url,
        image_url=recipe.image_url,
        servings=recipe.servings,
        total_minutes=recipe.total_minutes,
        tags=load_tags(recipe.tags),
    )


def recipe_out(recipe: Recipe) -> RecipeOut:
    base = recipe_summary(recipe)
    return RecipeOut(
        **base.model_dump(),
        instructions=recipe.instructions or "",
        is_user_edited=recipe.is_user_edited,
        ingredients=sorted(recipe.ingredients, key=lambda i: i.position),
    )
