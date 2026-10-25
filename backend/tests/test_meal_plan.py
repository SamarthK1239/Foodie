from __future__ import annotations

from datetime import date, timedelta

from tests.test_recipes_api import add_item, make_recipe


def plan(client, recipe_id: int, **kwargs):
    body = {"recipe_id": recipe_id, **kwargs}
    response = client.post("/api/meal-plan", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def week(client):
    return client.get("/api/meal-plan").json()


def grocery_by_label(client) -> dict[str, dict]:
    return {g["label"]: g for g in client.get("/api/grocery").json()}


def test_week_runs_monday_to_sunday(client):
    recipe = make_recipe(client, "Soup", [("1 onion", 1, "unit", False)])
    plan(client, recipe["id"])

    body = week(client)
    start = date.fromisoformat(body["week_start"])
    assert start.weekday() == 0
    assert date.fromisoformat(body["week_end"]) == start + timedelta(days=6)
    assert [e["recipe"]["title"] for e in body["entries"]] == ["Soup"]


def test_planning_puts_missing_ingredients_on_the_grocery_list(client):
    recipe = make_recipe(
        client,
        "Tomato Pasta",
        [("200 g pasta", 200, "g", False), ("3 tomatoes", 3, "unit", False)],
    )
    plan(client, recipe["id"])

    groceries = grocery_by_label(client)
    assert groceries["Pasta"]["source"] == "meal_plan"
    assert groceries["Pasta"]["quantity"] == 200
    assert "Tomato Pasta" in groceries["Pasta"]["note"]
    # Resolved from the line itself, so it keeps the plural the recipe used.
    assert "Tomatoes" in groceries


def test_planning_only_asks_for_the_shortfall(client):
    add_item(client, "pasta", 150, "g")
    recipe = make_recipe(client, "Pasta", [("200 g pasta", 200, "g", False)])
    plan(client, recipe["id"])

    # 150g on hand against 200g needed: buy the difference, not the whole amount.
    assert grocery_by_label(client)["Pasta"]["quantity"] == 50


def test_planning_skips_ingredients_already_in_stock(client):
    add_item(client, "pasta", 500, "g")
    recipe = make_recipe(client, "Pasta", [("200 g pasta", 200, "g", False)])
    plan(client, recipe["id"])

    assert "Pasta" not in grocery_by_label(client)


def test_two_recipes_sharing_an_ingredient_sum_their_needs(client):
    # The reason a week is planned as a whole: one 200g bag does not cover both.
    first = make_recipe(client, "Pasta Bake", [("200 g pasta", 200, "g", False)])
    second = make_recipe(client, "Pasta Salad", [("300 g pasta", 300, "g", False)])
    plan(client, first["id"])
    plan(client, second["id"])

    entry = grocery_by_label(client)["Pasta"]
    assert entry["quantity"] == 500
    assert "Pasta Bake" in entry["note"] and "Pasta Salad" in entry["note"]


def test_requirements_convert_units_before_summing(client):
    first = make_recipe(client, "Cake", [("500 g sugar", 500, "g", False)])
    second = make_recipe(client, "Syrup", [("1 kg sugar", 1, "kg", False)])
    plan(client, first["id"])
    plan(client, second["id"])

    assert grocery_by_label(client)["Sugar"]["quantity"] == 1500


def test_batch_multiplier_scales_the_requirement(client):
    recipe = make_recipe(client, "Pasta", [("200 g pasta", 200, "g", False)])
    plan(client, recipe["id"], servings_multiplier=2.5)

    assert grocery_by_label(client)["Pasta"]["quantity"] == 500


def test_replanning_the_same_recipe_adjusts_rather_than_duplicates(client):
    recipe = make_recipe(client, "Pasta", [("200 g pasta", 200, "g", False)])
    plan(client, recipe["id"])
    plan(client, recipe["id"], servings_multiplier=3)

    body = week(client)
    assert len(body["entries"]) == 1
    assert grocery_by_label(client)["Pasta"]["quantity"] == 600


def test_removing_a_planned_recipe_withdraws_its_groceries(client):
    recipe = make_recipe(client, "Pasta", [("200 g pasta", 200, "g", False)])
    entry = plan(client, recipe["id"])
    assert "Pasta" in grocery_by_label(client)

    assert client.delete(f"/api/meal-plan/{entry['id']}").status_code == 204

    assert "Pasta" not in grocery_by_label(client)
    assert week(client)["entries"] == []


def test_planning_never_touches_groceries_from_other_sources(client):
    manual = client.post(
        "/api/grocery",
        json={"label": "Pasta", "ingredient_name": "pasta", "quantity": 1, "unit": "unit"},
    ).json()

    recipe = make_recipe(client, "Pasta", [("200 g pasta", 200, "g", False)])
    entry = plan(client, recipe["id"])

    # The need is already represented, so no second row appears and the manual
    # entry keeps its own quantity rather than being rewritten by the plan.
    rows = [g for g in client.get("/api/grocery").json() if g["label"] == "Pasta"]
    assert len(rows) == 1
    assert rows[0]["id"] == manual["id"]
    assert rows[0]["source"] == "manual"
    assert rows[0]["quantity"] == 1

    client.delete(f"/api/meal-plan/{entry['id']}")
    survivors = [g for g in client.get("/api/grocery").json() if g["label"] == "Pasta"]
    assert len(survivors) == 1


def test_optional_ingredients_are_not_shopped_for(client):
    recipe = make_recipe(
        client,
        "Pasta",
        [("200 g pasta", 200, "g", False), ("basil", None, None, True)],
    )
    plan(client, recipe["id"])

    assert "Basil" not in grocery_by_label(client)


def test_unquantified_ingredient_is_listed_only_when_absent(client):
    recipe = make_recipe(client, "Pasta", [("salt", None, None, False)])
    plan(client, recipe["id"])

    entry = grocery_by_label(client)["Salt"]
    assert entry["quantity"] is None

    add_item(client, "salt", 100, "g")
    plan(client, recipe["id"])
    assert "Salt" not in grocery_by_label(client)


def test_a_future_week_does_not_fill_this_weeks_basket(client):
    recipe = make_recipe(client, "Pasta", [("200 g pasta", 200, "g", False)])
    next_week = (date.today() + timedelta(days=7)).isoformat()
    plan(client, recipe["id"], week_start=next_week)

    assert "Pasta" not in grocery_by_label(client)
    assert week(client)["entries"] == []

    later = client.get("/api/meal-plan", params={"week_start": next_week}).json()
    assert [e["recipe"]["title"] for e in later["entries"]] == ["Pasta"]


def test_shortfalls_are_reported_with_stock_context(client):
    add_item(client, "pasta", 50, "g")
    recipe = make_recipe(client, "Pasta", [("200 g pasta", 200, "g", False)])
    plan(client, recipe["id"])

    shortfall = {s["name"]: s for s in week(client)["shortfalls"]}["Pasta"]
    assert shortfall["needed"] == 200
    assert shortfall["in_stock"] == 50
    assert shortfall["missing"] == 150
    assert shortfall["unit"] == "g"


def test_planning_an_unknown_recipe_is_a_404(client):
    assert client.post("/api/meal-plan", json={"recipe_id": 9999}).status_code == 404
