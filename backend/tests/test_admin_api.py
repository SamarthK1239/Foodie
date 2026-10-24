from __future__ import annotations

from tests.test_recipes_api import add_item, make_recipe


def test_stats_endpoint(client):
    make_recipe(client, "Soup", [("1 onion", 1, "unit", False)])
    stats = client.get("/api/admin/stats").json()
    assert stats["recipes"] == 1
    assert stats["ingredients"] >= 1
    assert "database_path" in stats


def test_ingest_status_reports_no_job(client):
    status = client.get("/api/admin/ingest/status").json()
    assert status["running"] is False
    assert status["job"] is None


def test_cancel_without_active_job(client):
    assert client.post("/api/admin/ingest/cancel").status_code == 404


def test_start_ingest_rejects_empty_site_list(client):
    response = client.post("/api/admin/ingest/start", json={"mode": "new_only", "sites": []})
    assert response.status_code == 400


def test_unmatched_queue_and_resolution(client, session):
    from app.models import RecipeIngredient

    recipe = make_recipe(client, "Odd Dish", [("1 splorf", 1, "unit", False)])

    # Simulate an ingestion that could not resolve a line.
    line = session.query(RecipeIngredient).filter_by(recipe_id=recipe["id"]).one()
    line.ingredient_id = None
    session.commit()

    unmatched = client.get("/api/admin/unmatched-ingredients").json()
    assert len(unmatched) == 1
    assert unmatched[0]["raw_text"] == "1 splorf"
    assert unmatched[0]["recipe_title"] == "Odd Dish"

    add_item(client, "potato", 5, "unit")
    resolved = client.post(
        "/api/admin/unmatched-ingredients/resolve",
        json={
            "recipe_ingredient_id": unmatched[0]["recipe_ingredient_id"],
            "ingredient_name": "potato",
        },
    ).json()
    assert resolved["ingredient"] == "Potato"

    assert client.get("/api/admin/unmatched-ingredients").json() == []

    # Having been linked, the recipe is now suggestible from the matching stock.
    suggestions = client.get("/api/suggestions").json()
    assert any(s["recipe"]["title"] == "Odd Dish" for s in suggestions)


def test_resolution_creates_reusable_alias(client, session):
    from app.models import IngredientAlias, RecipeIngredient

    first = make_recipe(client, "Dish A", [("2 splorfs", 2, "unit", False)])
    second = make_recipe(client, "Dish B", [("2 splorfs", 2, "unit", False)])
    for recipe_id in (first["id"], second["id"]):
        line = session.query(RecipeIngredient).filter_by(recipe_id=recipe_id).one()
        line.ingredient_id = None
    session.commit()

    unmatched = client.get("/api/admin/unmatched-ingredients").json()
    result = client.post(
        "/api/admin/unmatched-ingredients/resolve",
        json={
            "recipe_ingredient_id": unmatched[0]["recipe_ingredient_id"],
            "ingredient_name": "parsnip",
            "add_alias": True,
        },
    ).json()

    # The identical line in the other recipe should be linked at the same time.
    assert result["also_linked"] == 1
    assert client.get("/api/admin/unmatched-ingredients").json() == []
    assert session.query(IngredientAlias).count() == 1
