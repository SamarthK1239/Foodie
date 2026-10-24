from __future__ import annotations

from datetime import date, timedelta


def make_recipe(client, title, ingredients, instructions="Mix and cook.", **kwargs):
    payload = {
        "title": title,
        "instructions": instructions,
        "ingredients": [
            {"raw_text": raw, "quantity": qty, "unit": unit, "optional": optional}
            for raw, qty, unit, optional in ingredients
        ],
        **kwargs,
    }
    response = client.post("/api/recipes", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def add_item(client, name, quantity=1.0, unit="unit", days_to_expiry=None):
    payload = {"ingredient_name": name, "quantity": quantity, "unit": unit}
    if days_to_expiry is not None:
        payload["expiry_date"] = (date.today() + timedelta(days=days_to_expiry)).isoformat()
    response = client.post("/api/inventory/items", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_create_and_fetch_recipe(client):
    recipe = make_recipe(
        client,
        "Tomato Pasta",
        [("200 g pasta", 200, "g", False), ("3 tomatoes", 3, "unit", False)],
        tags=["italian", "quick"],
    )
    assert recipe["is_user_edited"] is True
    assert len(recipe["ingredients"]) == 2
    assert sorted(recipe["tags"]) == ["italian", "quick"]
    # Ingredient lines should be linked to canonical ingredients.
    assert all(i["ingredient"] is not None for i in recipe["ingredients"])

    fetched = client.get(f"/api/recipes/{recipe['id']}").json()
    assert fetched["title"] == "Tomato Pasta"


def test_duplicate_source_url_rejected(client):
    make_recipe(client, "A", [("1 egg", 1, "unit", False)], source_url="http://x.test/a")
    response = client.post(
        "/api/recipes",
        json={
            "title": "B",
            "source_url": "http://x.test/a",
            "ingredients": [{"raw_text": "1 egg", "quantity": 1, "unit": "unit"}],
        },
    )
    assert response.status_code == 409


def test_full_text_search(client):
    make_recipe(client, "Chicken Curry", [("500 g chicken", 500, "g", False)])
    make_recipe(client, "Beef Stew", [("500 g beef", 500, "g", False)])

    results = client.get("/api/recipes", params={"search": "chicken"}).json()
    assert results["total"] == 1
    assert results["items"][0]["title"] == "Chicken Curry"

    # Prefix matching should work for partial words.
    assert client.get("/api/recipes", params={"search": "chick"}).json()["total"] == 1
    assert client.get("/api/recipes", params={"search": "zzzz"}).json()["total"] == 0


def test_search_index_updates_on_edit_and_delete(client):
    recipe = make_recipe(client, "Mystery Dish", [("1 egg", 1, "unit", False)])
    client.patch(f"/api/recipes/{recipe['id']}", json={"title": "Pancakes"})

    assert client.get("/api/recipes", params={"search": "pancakes"}).json()["total"] == 1
    assert client.get("/api/recipes", params={"search": "mystery"}).json()["total"] == 0

    client.delete(f"/api/recipes/{recipe['id']}")
    assert client.get("/api/recipes", params={"search": "pancakes"}).json()["total"] == 0


def test_suggestions_rank_by_coverage(client):
    add_item(client, "pasta", 500, "g")
    add_item(client, "tomato", 4, "unit")

    make_recipe(
        client,
        "Tomato Pasta",
        [("200 g pasta", 200, "g", False), ("3 tomatoes", 3, "unit", False)],
    )
    make_recipe(
        client,
        "Complicated Dish",
        [
            ("200 g pasta", 200, "g", False),
            ("1 truffle", 1, "unit", False),
            ("1 saffron", 1, "unit", False),
            ("1 caviar", 1, "unit", False),
        ],
    )

    suggestions = client.get("/api/suggestions").json()
    assert suggestions[0]["recipe"]["title"] == "Tomato Pasta"
    assert suggestions[0]["coverage"] == 1.0
    assert suggestions[0]["missing"] == []

    complicated = next(s for s in suggestions if s["recipe"]["title"] == "Complicated Dish")
    assert complicated["coverage"] < 1.0
    assert {m["name"] for m in complicated["missing"]} == {"Truffle", "Saffron", "Caviar"}


def test_expiring_ingredients_boost_suggestions(client):
    # Two recipes with identical coverage; the one using soon-to-expire stock should win.
    add_item(client, "spinach", 200, "g", days_to_expiry=1)
    add_item(client, "rice", 500, "g", days_to_expiry=300)

    make_recipe(client, "Spinach Saute", [("100 g spinach", 100, "g", False)])
    make_recipe(client, "Plain Rice", [("100 g rice", 100, "g", False)])

    suggestions = client.get("/api/suggestions").json()
    assert suggestions[0]["recipe"]["title"] == "Spinach Saute"
    assert suggestions[0]["urgency"] > suggestions[1]["urgency"]


def test_optional_ingredients_do_not_count_as_missing(client):
    add_item(client, "egg", 6, "unit")
    make_recipe(
        client,
        "Omelette",
        [("2 eggs", 2, "unit", False), ("1 tbsp chives", 1, "tbsp", True)],
    )
    suggestion = client.get("/api/suggestions").json()[0]
    assert suggestion["coverage"] == 1.0
    assert suggestion["missing"] == []


def test_suggestions_empty_without_stock(client):
    make_recipe(client, "Anything", [("1 egg", 1, "unit", False)])
    assert client.get("/api/suggestions").json() == []
