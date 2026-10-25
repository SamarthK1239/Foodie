from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, selectinload

from app.api.serializers import recipe_out, recipe_summary
from app.db import get_session
from app.ingest.parsing import parse_ingredient_line
from app.models import Recipe, RecipeIngredient
from app.models.entities import utcnow
from app.models.enums import DietClass, MealType
from app.schemas import (
    FavoriteRequest,
    RecipeCreate,
    RecipeListOut,
    RecipeOut,
    RecipeUpdate,
)
from app.services.classify import classify_recipe
from app.services.ingredients import IngredientResolver
from app.services.tags import dump_tags
from app.services.units import normalize_unit

router = APIRouter(prefix="/api/recipes", tags=["recipes"])


def _fts_query(raw: str) -> str:
    """Build a safe FTS5 prefix query from user input."""
    tokens = [t for t in "".join(c if c.isalnum() else " " for c in raw).split() if t]
    return " AND ".join(f'"{t}"*' for t in tokens)


def _filter_clauses(
    favorites_only: bool,
    diet: DietClass | None,
    meat: str | None,
    meal_type: MealType | None,
) -> tuple[list[str], dict]:
    """Build the filter predicates once, as SQL fragments against `recipe`.

    Both the plain listing and the full-text search have to apply these, and
    they have to apply them *inside* the query rather than to an already-paged
    result -- filtering a page that was cut to `limit` returns short pages and a
    total that only counts the page. Returning fragments rather than ORM
    conditions lets the raw FTS statement reuse exactly the same logic.
    """
    clauses: list[str] = []
    params: dict = {}

    if favorites_only:
        clauses.append("recipe.is_favorite = 1")

    if diet is not None:
        if diet == DietClass.VEGETARIAN:
            # Vegan is a strict subset of vegetarian: someone filtering for
            # vegetarian food wants the vegan recipes too.
            clauses.append("recipe.diet IN ('vegetarian', 'vegan')")
        else:
            clauses.append("recipe.diet = :diet")
            params["diet"] = str(diet)

    if meat:
        # meat_types is a JSON array, so match elements rather than substrings:
        # a LIKE would make "fish" match a future "shellfish".
        clauses.append(
            "EXISTS (SELECT 1 FROM json_each(recipe.meat_types) WHERE value = :meat)"
        )
        params["meat"] = meat

    if meal_type is not None:
        clauses.append("recipe.meal_type = :meal_type")
        params["meal_type"] = str(meal_type)

    return clauses, params


MEAT_TYPE_PATTERN = "^(beef|pork|chicken|lamb|fish|game)$"


def _apply_ingredients(
    session: Session, recipe: Recipe, lines: list, resolver: IngredientResolver
) -> None:
    recipe.ingredients.clear()
    session.flush()
    for position, line in enumerate(lines):
        # Manual entry runs through the same parser as ingestion so that a typed
        # "2 eggs" resolves to the same canonical ingredient as a scraped one.
        parsed = parse_ingredient_line(line.raw_text)
        match = resolver.resolve(parsed.name)
        quantity = line.quantity if line.quantity is not None else parsed.quantity
        unit = line.unit if line.unit else parsed.unit
        recipe.ingredients.append(
            RecipeIngredient(
                raw_text=line.raw_text,
                quantity=quantity,
                unit=normalize_unit(unit) if unit else None,
                optional=line.optional or parsed.optional,
                position=position,
                ingredient_id=match.ingredient.id if match.ingredient else None,
            )
        )


@router.get("", response_model=RecipeListOut)
def list_recipes(
    session: Session = Depends(get_session),
    search: str | None = None,
    favorites_only: bool = False,
    diet: DietClass | None = None,
    meat: str | None = Query(default=None, pattern=MEAT_TYPE_PATTERN),
    meal_type: MealType | None = None,
    sort: str = Query(default="title", pattern="^(title|favorite)$"),
    limit: int = Query(default=24, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> RecipeListOut:
    clauses, params = _filter_clauses(favorites_only, diet, meat, meal_type)

    if search and search.strip():
        match_expr = _fts_query(search)
        if not match_expr:
            return RecipeListOut(total=0, items=[])
        source = "recipes_fts"
        condition = "recipes_fts MATCH :q"
        if clauses:
            # Any recipe-column filter needs the recipe row joined in.
            source = "recipes_fts JOIN recipe ON recipe.id = recipes_fts.rowid"
            condition = " AND ".join([condition, *clauses])

        ids = list(
            session.execute(
                text(
                    f"SELECT recipes_fts.rowid FROM {source} WHERE {condition} "
                    "ORDER BY rank LIMIT :limit OFFSET :offset"
                ),
                {"q": match_expr, "limit": limit, "offset": offset, **params},
            ).scalars()
        )
        total = session.execute(
            text(f"SELECT count(*) FROM {source} WHERE {condition}"),
            {"q": match_expr, **params},
        ).scalar_one()
        if not ids:
            return RecipeListOut(total=total, items=[])

        recipes = list(session.execute(select(Recipe).where(Recipe.id.in_(ids))).unique().scalars())
        # Relevance is the point of a search, so favourites float to the top of
        # the matches rather than reordering them outright.
        order = {rid: i for i, rid in enumerate(ids)}
        recipes.sort(key=lambda r: order.get(r.id, 1_000_000))
        if sort == "favorite":
            recipes.sort(key=lambda r: not r.is_favorite)
        return RecipeListOut(total=total, items=[recipe_summary(r) for r in recipes])

    count_stmt = select(func.count()).select_from(Recipe)
    stmt = select(Recipe)
    for clause in clauses:
        bound = text(clause).bindparams(
            **{k: v for k, v in params.items() if f":{k}" in clause}
        )
        count_stmt = count_stmt.where(bound)
        stmt = stmt.where(bound)

    total = session.execute(count_stmt).scalar_one()
    if sort == "favorite":
        stmt = stmt.order_by(Recipe.is_favorite.desc(), Recipe.title)
    else:
        stmt = stmt.order_by(Recipe.title)
    recipes = session.execute(stmt.limit(limit).offset(offset)).unique().scalars()
    return RecipeListOut(total=total, items=[recipe_summary(r) for r in recipes])


@router.get("/{recipe_id}", response_model=RecipeOut)
def get_recipe(recipe_id: int, session: Session = Depends(get_session)) -> RecipeOut:
    recipe = session.execute(
        select(Recipe)
        .where(Recipe.id == recipe_id)
        .options(selectinload(Recipe.ingredients).selectinload(RecipeIngredient.ingredient))
    ).unique().scalar_one_or_none()
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return recipe_out(recipe)


@router.post("", response_model=RecipeOut, status_code=201)
def create_recipe(payload: RecipeCreate, session: Session = Depends(get_session)) -> RecipeOut:
    if payload.source_url:
        existing = session.execute(
            select(Recipe).where(Recipe.source_url == payload.source_url)
        ).unique().scalar_one_or_none()
        if existing is not None:
            raise HTTPException(status_code=409, detail="A recipe with that URL already exists")

    recipe = Recipe(
        title=payload.title,
        instructions=payload.instructions,
        servings=payload.servings,
        total_minutes=payload.total_minutes,
        source_url=payload.source_url,
        image_url=payload.image_url,
        tags=dump_tags(payload.tags),
        is_user_edited=True,
    )
    session.add(recipe)
    session.flush()
    _apply_ingredients(session, recipe, payload.ingredients, IngredientResolver(session))
    session.flush()
    classify_recipe(recipe)
    session.flush()
    return recipe_out(recipe)


@router.patch("/{recipe_id}", response_model=RecipeOut)
def update_recipe(
    recipe_id: int, payload: RecipeUpdate, session: Session = Depends(get_session)
) -> RecipeOut:
    recipe = session.get(Recipe, recipe_id)
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found")

    data = payload.model_dump(exclude_unset=True)
    ingredients = data.pop("ingredients", None)
    if "tags" in data:
        data["tags"] = dump_tags(data["tags"])
    for field, value in data.items():
        setattr(recipe, field, value)

    if ingredients is not None:
        _apply_ingredients(
            session, recipe, payload.ingredients or [], IngredientResolver(session)
        )

    # Always reclassify: the labels derive from the ingredients and tags, both
    # of which this endpoint can change. Swapping the beef for lentils must not
    # leave the recipe filed under "beef".
    classify_recipe(recipe)

    # Protect hand-edited recipes from being clobbered by a later re-crawl.
    recipe.is_user_edited = True
    recipe.updated_at = utcnow()
    session.flush()
    return recipe_out(recipe)


@router.post("/{recipe_id}/favorite", response_model=RecipeOut)
def set_favorite(
    recipe_id: int, payload: FavoriteRequest, session: Session = Depends(get_session)
) -> RecipeOut:
    """Deliberately not part of PATCH: starring a recipe is not editing it, and
    going through update_recipe would mark it hand-edited and quietly opt it out
    of future re-imports."""
    recipe = session.get(Recipe, recipe_id)
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found")
    recipe.is_favorite = payload.is_favorite
    session.flush()
    return recipe_out(recipe)


@router.delete("/{recipe_id}", status_code=204)
def delete_recipe(recipe_id: int, session: Session = Depends(get_session)) -> None:
    recipe = session.get(Recipe, recipe_id)
    if recipe is None:
        raise HTTPException(status_code=404, detail="Recipe not found")
    session.delete(recipe)
