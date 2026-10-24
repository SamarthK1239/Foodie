from __future__ import annotations

import json

import pytest

from app.ingest.discovery import _looks_like_recipe
from app.ingest.importer import parse_recipe_html, upsert_recipe
from app.models import Recipe
from app.services.ingredients import IngredientResolver


def recipe_html(
    title="Test Pasta",
    ingredients=("200 g spaghetti", "2 cloves garlic", "1 tbsp olive oil"),
    instructions="Boil pasta. Fry garlic. Combine.",
    servings="4 servings",
    image="http://example.test/img.jpg",
):
    payload = {
        "@context": "https://schema.org",
        "@type": "Recipe",
        "name": title,
        "recipeIngredient": list(ingredients),
        "recipeInstructions": instructions,
        "recipeYield": servings,
        "image": image,
        "totalTime": "PT25M",
        "recipeCategory": "Main",
        "recipeCuisine": "Italian",
    }
    return f"""<!doctype html><html><head><title>{title}</title>
    <script type="application/ld+json">{json.dumps(payload)}</script>
    </head><body><h1>{title}</h1></body></html>"""


def test_parse_recipe_html_extracts_fields():
    scraped = parse_recipe_html(recipe_html(), "http://example.test/recipes/test-pasta")
    assert scraped is not None
    assert scraped.title == "Test Pasta"
    assert len(scraped.ingredients) == 3
    assert scraped.servings == 4
    assert scraped.total_minutes == 25
    assert scraped.source_site == "example.test"
    assert "Main" in scraped.tags


def test_parse_rejects_non_recipe_pages():
    html = "<html><body><p>Just a blog post with no recipe data.</p></body></html>"
    assert parse_recipe_html(html, "http://example.test/blog/post") is None


def test_upsert_creates_recipe_with_linked_ingredients(session):
    scraped = parse_recipe_html(recipe_html(), "http://example.test/recipes/test-pasta")
    resolver = IngredientResolver(session)
    recipe, outcome = upsert_recipe(session, scraped, resolver)

    assert outcome == "imported"
    assert recipe.title == "Test Pasta"
    assert len(recipe.ingredients) == 3

    by_text = {i.raw_text: i for i in recipe.ingredients}
    spaghetti = by_text["200 g spaghetti"]
    assert spaghetti.quantity == 200
    assert spaghetti.unit == "g"
    assert spaghetti.ingredient is not None
    assert spaghetti.ingredient.name == "spaghetti"

    garlic = by_text["2 cloves garlic"]
    assert garlic.quantity == 2
    assert garlic.unit == "clove"


def test_upsert_is_idempotent_on_reimport(session):
    url = "http://example.test/recipes/test-pasta"
    resolver = IngredientResolver(session)

    upsert_recipe(session, parse_recipe_html(recipe_html(), url), resolver)
    recipe, outcome = upsert_recipe(
        session, parse_recipe_html(recipe_html(title="Test Pasta Updated"), url), resolver
    )

    assert outcome == "updated"
    assert recipe.title == "Test Pasta Updated"
    assert session.query(Recipe).count() == 1
    assert len(recipe.ingredients) == 3


def test_user_edited_recipes_are_never_overwritten(session):
    url = "http://example.test/recipes/test-pasta"
    resolver = IngredientResolver(session)
    recipe, _ = upsert_recipe(session, parse_recipe_html(recipe_html(), url), resolver)

    recipe.is_user_edited = True
    recipe.title = "My Perfected Pasta"
    session.flush()

    same, outcome = upsert_recipe(
        session, parse_recipe_html(recipe_html(title="Scraped Again"), url), resolver
    )
    assert outcome == "skipped"
    assert same.title == "My Perfected Pasta"


def test_ingredient_vocabulary_is_shared_across_recipes(session):
    resolver = IngredientResolver(session)
    upsert_recipe(
        session,
        parse_recipe_html(recipe_html(), "http://example.test/recipes/a"),
        resolver,
    )
    upsert_recipe(
        session,
        parse_recipe_html(
            recipe_html(title="Garlic Bread", ingredients=("4 cloves garlic", "1 baguette")),
            "http://example.test/recipes/b",
        ),
        resolver,
    )

    from app.models import Ingredient

    garlic = session.query(Ingredient).filter_by(name="garlic").all()
    assert len(garlic) == 1


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://site.test/recipes/chicken-curry", True),
        ("https://site.test/recipe/beef-stew-123", True),
        ("https://site.test/category/dinner/", False),
        ("https://site.test/tag/quick/", False),
        ("https://site.test/about/", False),
        ("https://site.test/", False),
        ("https://site.test/recipes/collection/best-of/", False),
    ],
)
def test_recipe_url_heuristics(url, expected):
    assert _looks_like_recipe(url) is expected
