from __future__ import annotations

from tests.test_recipes_api import add_item, make_recipe


def review(client, weeks: int = 2) -> dict:
    response = client.get("/api/analytics/period-review", params={"weeks": weeks})
    assert response.status_code == 200, response.text
    return response.json()


def test_review_reports_what_was_cooked_with(client):
    add_item(client, "pasta", 500, "g")
    add_item(client, "tomato", 4, "unit")
    recipe = make_recipe(
        client,
        "Tomato Pasta",
        [("200 g pasta", 200, "g", False), ("3 tomatoes", 3, "unit", False)],
    )
    client.post(f"/api/recipes/{recipe['id']}/cook", json={})

    data = review(client)
    assert data["weeks"] == 2
    assert data["period_days"] == 14
    used = {row["name"]: row for row in data["used"]}
    assert set(used) == {"Pasta", "Tomato"}
    assert used["Pasta"]["quantity"] == 200


def test_review_suggests_restocking_only_what_ran_out(client):
    # Pasta is fully used up; plenty of tomato is left over.
    add_item(client, "pasta", 200, "g")
    add_item(client, "tomato", 20, "unit")
    recipe = make_recipe(
        client,
        "Tomato Pasta",
        [("200 g pasta", 200, "g", False), ("1 tomato", 1, "unit", False)],
    )
    client.post(f"/api/recipes/{recipe['id']}/cook", json={})

    suggested = {row["name"] for row in review(client)["suggested"]}
    assert "Pasta" in suggested
    assert "Tomato" not in suggested


def test_review_does_not_suggest_rebuying_something_binned(client):
    """Re-buying an ingredient you just threw away is how waste repeats."""
    # Two batches: one gets cooked with, the rest goes off and is binned.
    add_item(client, "basil", 1, "unit", days_to_expiry=1)
    add_item(client, "basil", 1, "unit", days_to_expiry=5)
    add_item(client, "pasta", 200, "g")
    recipe = make_recipe(
        client,
        "Pasta with basil",
        [("200 g pasta", 200, "g", False), ("1 basil", 1, "unit", False)],
    )
    client.post(f"/api/recipes/{recipe['id']}/cook", json={})

    leftover_basil = next(
        item
        for item in client.get("/api/inventory/items").json()
        if item["ingredient"]["display_name"] == "Basil"
    )
    assert client.post(f"/api/inventory/items/{leftover_basil['id']}/discard").status_code == 200

    data = review(client)
    assert "Basil" in {row["name"] for row in data["wasted"]}
    assert "Basil" not in {row["name"] for row in data["suggested"]}
    # Pasta was used up without being wasted, so it is still worth restocking.
    assert "Pasta" in {row["name"] for row in data["suggested"]}


def test_applying_the_review_adds_to_the_grocery_list(client):
    add_item(client, "pasta", 200, "g")
    recipe = make_recipe(client, "Plain pasta", [("200 g pasta", 200, "g", False)])
    client.post(f"/api/recipes/{recipe['id']}/cook", json={})

    suggested = review(client)["suggested"]
    assert suggested, "expected pasta to be suggested after being used up"

    response = client.post(
        "/api/analytics/period-review/apply",
        json={"ingredient_ids": [row["ingredient_id"] for row in suggested]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["added"] == len(suggested)

    grocery = client.get("/api/grocery").json()
    pasta = [item for item in grocery if item["label"] == "Pasta"]
    # Merged into the single pending entry rather than duplicated.
    assert len(pasta) == 1
    assert pasta[0]["status"] == "pending"


def test_review_marks_suggestions_already_on_the_list(client):
    add_item(client, "pasta", 200, "g")
    recipe = make_recipe(client, "Plain pasta", [("200 g pasta", 200, "g", False)])
    client.post(f"/api/recipes/{recipe['id']}/cook", json={})

    # Running out auto-adds to the list, so the review must not claim it is new.
    pasta = next(row for row in review(client)["suggested"] if row["name"] == "Pasta")
    assert pasta["already_on_list"] is True
    assert pasta["reason"] == "out_of_stock"


def test_review_uses_period_review_source_for_a_fresh_addition(client):
    """An ingredient still in stock is not auto-listed, so the review owns it."""
    add_item(client, "olive oil", 1000, "ml")
    recipe = make_recipe(client, "Dressing", [("50 ml olive oil", 50, "ml", False)])
    client.post(f"/api/recipes/{recipe['id']}/cook", json={})

    oil = next(
        item
        for item in client.get("/api/inventory/items").json()
        if item["ingredient"]["display_name"] == "Olive Oil"
    )
    response = client.post(
        "/api/analytics/period-review/apply",
        json={"ingredient_ids": [oil["ingredient"]["id"]]},
    )
    assert response.json()["added"] == 1

    grocery = client.get("/api/grocery").json()
    entry = next(item for item in grocery if item["label"] == "Olive Oil")
    assert entry["source"] == "period_review"
    assert entry["note"] == "From your 2-week review"


def test_applying_an_unknown_ingredient_is_ignored(client):
    response = client.post("/api/analytics/period-review/apply", json={"ingredient_ids": [9999]})
    assert response.status_code == 200
    assert response.json()["added"] == 0


def test_freshly_bought_stock_is_not_reported_as_unused(client):
    """Something bought today has not had a chance to go unused yet."""
    add_item(client, "pasta", 500, "g")
    assert review(client)["unused"] == []


def test_review_flags_stock_that_sat_untouched_all_period(client, session_factory):
    from datetime import timedelta

    from app.models import InventoryItem
    from app.models.entities import utcnow

    add_item(client, "quinoa", 500, "g")
    add_item(client, "pasta", 500, "g")

    # Backdate the quinoa so it predates the review window; pasta stays recent.
    db = session_factory()
    try:
        item = next(
            i for i in db.query(InventoryItem).all() if i.ingredient.display_name == "Quinoa"
        )
        item.created_at = utcnow() - timedelta(days=30)
        db.commit()
    finally:
        db.close()

    unused = review(client)["unused"]
    assert [row["name"] for row in unused] == ["Quinoa"]
    assert unused[0]["days_in_stock"] >= 29
