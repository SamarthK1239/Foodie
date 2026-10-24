"""Convert scraped recipe pages into normalised `Recipe` rows."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from urllib.parse import urlparse

from recipe_scrapers import scrape_html
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.serializers import dump_tags
from app.ingest.parsing import parse_ingredient_line
from app.models import Recipe, RecipeIngredient
from app.models.entities import utcnow
from app.services.ingredients import IngredientResolver
from app.services.units import normalize_unit

logger = logging.getLogger(__name__)


@dataclass
class ScrapedRecipe:
    title: str
    instructions: str
    ingredients: list[str] = field(default_factory=list)
    servings: int | None = None
    total_minutes: int | None = None
    image_url: str | None = None
    tags: list[str] = field(default_factory=list)
    source_url: str | None = None
    source_site: str | None = None
    raw: dict | None = None


def _safe(getter, default=None):
    try:
        value = getter()
    except Exception:  # recipe-scrapers raises a wide variety of parse errors
        return default
    return value if value is not None else default


def _parse_servings(value) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    if not digits:
        return None
    try:
        parsed = int(digits[:3])
    except ValueError:
        return None
    return parsed if parsed > 0 else None


def parse_recipe_html(html: str, url: str) -> ScrapedRecipe | None:
    """Run recipe-scrapers over a page, returning None if it isn't a usable recipe."""
    try:
        # supported_only=False lets sites without a dedicated scraper still be parsed
        # from their schema.org metadata.
        scraper = scrape_html(html, org_url=url, supported_only=False)
    except Exception as exc:
        logger.debug("No scraper could handle %s: %s", url, exc)
        return None

    title = _safe(scraper.title)
    ingredients = _safe(scraper.ingredients, []) or []
    instructions = _safe(scraper.instructions, "") or ""

    if not title or not ingredients or not instructions:
        return None

    tags = []
    category = _safe(scraper.category)
    if category:
        tags.extend(str(category).split(","))
    cuisine = _safe(scraper.cuisine)
    if cuisine:
        tags.extend(str(cuisine).split(","))

    return ScrapedRecipe(
        title=str(title).strip(),
        instructions=str(instructions).strip(),
        ingredients=[str(i).strip() for i in ingredients if str(i).strip()],
        servings=_parse_servings(_safe(scraper.yields)),
        total_minutes=_safe(scraper.total_time),
        image_url=_safe(scraper.image),
        tags=[t.strip() for t in tags if t and t.strip()],
        source_url=url,
        source_site=urlparse(url).netloc,
    )


def upsert_recipe(
    session: Session, scraped: ScrapedRecipe, resolver: IngredientResolver
) -> tuple[Recipe | None, str]:
    """Insert or refresh a recipe. Returns (recipe, outcome) where outcome is
    imported / updated / skipped."""
    existing = None
    if scraped.source_url:
        existing = session.execute(
            select(Recipe).where(Recipe.source_url == scraped.source_url)
        ).unique().scalar_one_or_none()

    if existing is not None and existing.is_user_edited:
        # Never overwrite something the user has curated by hand.
        return existing, "skipped"

    recipe = existing or Recipe(source_url=scraped.source_url)
    recipe.title = scraped.title
    recipe.instructions = scraped.instructions
    recipe.servings = scraped.servings
    recipe.total_minutes = scraped.total_minutes
    recipe.image_url = scraped.image_url
    recipe.source_site = scraped.source_site
    recipe.tags = dump_tags(scraped.tags)
    recipe.raw_json = json.dumps({"ingredients": scraped.ingredients})
    recipe.last_scraped_at = utcnow()

    if existing is None:
        session.add(recipe)
    session.flush()

    recipe.ingredients.clear()
    session.flush()
    for position, line in enumerate(scraped.ingredients):
        parsed = parse_ingredient_line(line)
        match = resolver.resolve(parsed.name)
        recipe.ingredients.append(
            RecipeIngredient(
                raw_text=parsed.raw_text,
                quantity=parsed.quantity,
                unit=normalize_unit(parsed.unit) if parsed.unit else None,
                optional=parsed.optional,
                position=position,
                ingredient_id=match.ingredient.id if match.ingredient else None,
            )
        )
    session.flush()
    return recipe, "updated" if existing is not None else "imported"
