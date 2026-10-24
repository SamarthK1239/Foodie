from __future__ import annotations

from datetime import date, timedelta

from tests.test_recipes_api import add_item, make_recipe


def test_cooking_decrements_stock(client):
    add_item(client, "pasta", 500, "g")
    add_item(client, "tomato", 4, "unit")
    recipe = make_recipe(
        client,
        "Tomato Pasta",
        [("200 g pasta", 200, "g", False), ("3 tomatoes", 3, "unit", False)],
    )

    result = client.post(f"/api/recipes/{recipe['id']}/cook", json={}).json()
    assert result["missing"] == []
    assert {c["ingredient"] for c in result["consumed"]} == {"Pasta", "Tomato"}

    items = {i["ingredient"]["display_name"]: i for i in client.get("/api/inventory/items").json()}
    assert items["Pasta"]["quantity"] == 300
    assert items["Tomato"]["quantity"] == 1


def test_cooking_uses_soonest_expiry_first(client):
    # Two batches of the same ingredient; the one expiring first must be used first.
    add_item(client, "milk", 500, "ml", days_to_expiry=10)
    add_item(client, "milk", 500, "ml", days_to_expiry=1)
    recipe = make_recipe(client, "Milkshake", [("400 ml milk", 400, "ml", False)])

    client.post(f"/api/recipes/{recipe['id']}/cook", json={})

    items = client.get("/api/inventory/items").json()
    by_expiry = {i["expiry_date"]: i["quantity"] for i in items}
    soonest = (date.today() + timedelta(days=1)).isoformat()
    later = (date.today() + timedelta(days=10)).isoformat()
    assert by_expiry[soonest] == 100
    assert by_expiry[later] == 500


def test_cooking_spans_multiple_items_when_needed(client):
    add_item(client, "flour", 300, "g", days_to_expiry=2)
    add_item(client, "flour", 300, "g", days_to_expiry=30)
    recipe = make_recipe(client, "Big Bake", [("500 g flour", 500, "g", False)])

    client.post(f"/api/recipes/{recipe['id']}/cook", json={})

    items = sorted(client.get("/api/inventory/items").json(), key=lambda i: i["expiry_date"] or "")
    # First batch fully drained (and so no longer active), second partially used.
    active = [i for i in items if i["status"] == "active"]
    assert len(active) == 1
    assert active[0]["quantity"] == 100


def test_cooking_converts_units(client):
    add_item(client, "sugar", 1, "kg")
    recipe = make_recipe(client, "Syrup", [("200 g sugar", 200, "g", False)])
    client.post(f"/api/recipes/{recipe['id']}/cook", json={})

    item = client.get("/api/inventory/items").json()[0]
    assert item["unit"] == "kg"
    assert item["quantity"] == 0.8


def test_servings_multiplier_scales_consumption(client):
    add_item(client, "rice", 1000, "g")
    recipe = make_recipe(client, "Rice Bowl", [("200 g rice", 200, "g", False)])
    client.post(f"/api/recipes/{recipe['id']}/cook", json={"servings_multiplier": 2})

    item = client.get("/api/inventory/items").json()[0]
    assert item["quantity"] == 600


def test_missing_ingredients_go_to_grocery_list(client):
    add_item(client, "pasta", 500, "g")
    recipe = make_recipe(
        client,
        "Carbonara",
        [("200 g pasta", 200, "g", False), ("100 g pancetta", 100, "g", False)],
    )
    result = client.post(f"/api/recipes/{recipe['id']}/cook", json={}).json()
    assert result["missing"] == ["Pancetta"]

    grocery = client.get("/api/grocery").json()
    pancetta = next(g for g in grocery if g["label"] == "Pancetta")
    assert pancetta["source"] == "recipe_gap"
    assert "Carbonara" in pancetta["note"]


def test_depleted_ingredient_auto_added_to_grocery(client):
    add_item(client, "onion", 2, "unit")
    recipe = make_recipe(client, "Onion Soup", [("2 onions", 2, "unit", False)])
    client.post(f"/api/recipes/{recipe['id']}/cook", json={})

    grocery = client.get("/api/grocery").json()
    onion = next(g for g in grocery if g["label"] == "Onion")
    assert onion["source"] == "auto_depleted"


def test_restock_threshold_triggers_before_zero(client):
    item = add_item(client, "oats", 1000, "g")
    ingredient_id = item["ingredient"]["id"]
    client.patch(
        f"/api/ingredients/{ingredient_id}",
        json={"restock_threshold": 500, "restock_unit": "g"},
    )

    recipe = make_recipe(client, "Porridge", [("600 g oats", 600, "g", False)])
    client.post(f"/api/recipes/{recipe['id']}/cook", json={})

    grocery = client.get("/api/grocery").json()
    oats = next(g for g in grocery if g["label"] == "Oats")
    assert oats["source"] == "auto_depleted"
    assert "Low stock" in oats["note"]


def test_recently_cooked_recipes_are_deprioritised(client):
    add_item(client, "egg", 12, "unit")
    first = make_recipe(client, "Omelette", [("2 eggs", 2, "unit", False)])
    make_recipe(client, "Scrambled Eggs", [("2 eggs", 2, "unit", False)])

    client.post(f"/api/recipes/{first['id']}/cook", json={})

    suggestions = client.get("/api/suggestions").json()
    titles = [s["recipe"]["title"] for s in suggestions]
    assert titles[0] == "Scrambled Eggs"
    omelette = next(s for s in suggestions if s["recipe"]["title"] == "Omelette")
    assert omelette["recently_cooked"] is True

    # Opting out restores the normal ranking behaviour.
    without = client.get("/api/suggestions", params={"exclude_recent": False}).json()
    assert all(s["recently_cooked"] is False for s in without)


def test_cook_event_history_and_leftovers(client):
    add_item(client, "egg", 6, "unit")
    recipe = make_recipe(client, "Omelette", [("2 eggs", 2, "unit", False)])
    result = client.post(f"/api/recipes/{recipe['id']}/cook", json={}).json()

    events = client.get("/api/cook-events").json()
    assert len(events) == 1
    assert events[0]["recipe_title"] == "Omelette"

    updated = client.patch(
        f"/api/cook-events/{result['cook_event_id']}", json={"leftover_state": "in_fridge"}
    ).json()
    assert updated["leftover_state"] == "in_fridge"


def test_grocery_manual_add_and_status_flow(client):
    created = client.post(
        "/api/grocery", json={"ingredient_name": "Coffee", "quantity": 1, "unit": "package"}
    ).json()
    assert created["status"] == "pending"

    client.patch(f"/api/grocery/{created['id']}", json={"status": "purchased"})
    assert client.get("/api/grocery").json() == []
    purchased = client.get("/api/grocery", params={"status": "purchased"}).json()
    assert len(purchased) == 1

    client.post("/api/grocery/clear-purchased")
    assert client.get("/api/grocery", params={"status": "purchased"}).json() == []


def test_grocery_merges_duplicate_pending_entries(client):
    client.post("/api/grocery", json={"ingredient_name": "Milk", "quantity": 1, "unit": "l"})
    client.post("/api/grocery", json={"ingredient_name": "milk", "quantity": 2, "unit": "l"})
    grocery = client.get("/api/grocery").json()
    assert len(grocery) == 1
    assert grocery[0]["quantity"] == 2


def test_analytics_summary_tracks_spend_and_waste(client):
    add_item(client, "steak", 1, "unit")
    client.post(
        "/api/inventory/items",
        json={"ingredient_name": "wine", "quantity": 1, "unit": "bottle", "cost": 12.5},
    )
    items = client.get("/api/inventory/items").json()
    steak = next(i for i in items if i["ingredient"]["display_name"] == "Steak")
    client.post(f"/api/inventory/items/{steak['id']}/discard")

    summary = client.get("/api/analytics/summary").json()
    assert summary["total_spend"] == 12.5
    assert summary["items_purchased"] == 2
    assert summary["items_discarded"] == 1
    assert summary["waste_rate"] == 1.0

    wasted = client.get("/api/analytics/most-wasted").json()
    assert wasted[0]["name"] == "Steak"


def test_analytics_most_used_reflects_cooking(client):
    add_item(client, "garlic", 10, "clove")
    recipe = make_recipe(client, "Garlic Bread", [("3 cloves garlic", 3, "clove", False)])
    client.post(f"/api/recipes/{recipe['id']}/cook", json={})

    used = client.get("/api/analytics/most-used").json()
    assert used[0]["name"] == "Garlic"


def test_analytics_breakdown_endpoints(client):
    client.post(
        "/api/inventory/items",
        json={"ingredient_name": "chicken", "quantity": 1, "unit": "kg", "cost": 9.0},
    )
    client.post(
        "/api/inventory/items",
        json={"ingredient_name": "carrots", "quantity": 500, "unit": "g", "cost": 2.0},
    )

    by_category = client.get("/api/analytics/spend-by-category").json()
    categories = {row["category"]: row["total"] for row in by_category}
    assert categories["meat"] == 9.0
    assert categories["produce"] == 2.0

    over_time = client.get("/api/analytics/spend-over-time").json()
    assert sum(row["total"] for row in over_time) == 11.0

    assert client.get("/api/analytics/recent-cooks").json() == []
