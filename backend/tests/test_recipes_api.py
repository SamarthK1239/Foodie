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


def set_favorite(client, recipe_id: int, value: bool):
    response = client.post(f"/api/recipes/{recipe_id}/favorite", json={"is_favorite": value})
    assert response.status_code == 200, response.text
    return response.json()


def test_recipes_start_unfavorited_and_toggle(client):
    recipe = make_recipe(client, "Soup", [("1 onion", 1, "unit", False)])
    assert recipe["is_favorite"] is False

    assert set_favorite(client, recipe["id"], True)["is_favorite"] is True
    assert client.get(f"/api/recipes/{recipe['id']}").json()["is_favorite"] is True

    assert set_favorite(client, recipe["id"], False)["is_favorite"] is False


def test_favoriting_does_not_mark_a_recipe_hand_edited(client, session):
    # Starring is not editing. Going through PATCH would set is_user_edited and
    # quietly opt the recipe out of future re-imports.
    from app.models import Recipe

    recipe = make_recipe(client, "Soup", [("1 onion", 1, "unit", False)])
    stored = session.get(Recipe, recipe["id"])
    stored.is_user_edited = False
    session.commit()

    set_favorite(client, recipe["id"], True)

    session.expire_all()
    stored = session.get(Recipe, recipe["id"])
    assert stored.is_favorite is True
    assert stored.is_user_edited is False


def test_sorting_by_favorite_puts_starred_recipes_first(client):
    make_recipe(client, "Apple cake", [("1 apple", 1, "unit", False)])
    zebra = make_recipe(client, "Zebra cake", [("1 egg", 1, "unit", False)])
    set_favorite(client, zebra["id"], True)

    titles = [r["title"] for r in client.get("/api/recipes").json()["items"]]
    assert titles == ["Apple cake", "Zebra cake"]

    sorted_titles = [
        r["title"] for r in client.get("/api/recipes", params={"sort": "favorite"}).json()["items"]
    ]
    assert sorted_titles == ["Zebra cake", "Apple cake"]


def test_favorites_only_filters_and_counts(client):
    make_recipe(client, "Apple cake", [("1 apple", 1, "unit", False)])
    zebra = make_recipe(client, "Zebra cake", [("1 egg", 1, "unit", False)])
    set_favorite(client, zebra["id"], True)

    body = client.get("/api/recipes", params={"favorites_only": True}).json()
    assert [r["title"] for r in body["items"]] == ["Zebra cake"]
    assert body["total"] == 1


def test_favorites_only_applies_to_search_results(client):
    make_recipe(client, "Apple cake", [("1 apple", 1, "unit", False)])
    starred = make_recipe(client, "Apple pie", [("1 apple", 1, "unit", False)])
    set_favorite(client, starred["id"], True)

    body = client.get("/api/recipes", params={"search": "apple", "favorites_only": True}).json()
    assert [r["title"] for r in body["items"]] == ["Apple pie"]
    assert body["total"] == 1


def test_search_sorted_by_favorite_floats_starred_matches(client):
    make_recipe(client, "Apple cake", [("1 apple", 1, "unit", False)])
    pie = make_recipe(client, "Apple pie", [("1 apple", 1, "unit", False)])
    set_favorite(client, pie["id"], True)

    body = client.get("/api/recipes", params={"search": "apple", "sort": "favorite"}).json()
    assert [r["title"] for r in body["items"]][0] == "Apple pie"
    assert body["total"] == 2


def test_favorites_only_search_pages_correctly(client):
    # Favourites must be filtered inside the search, not after paging it:
    # otherwise page one is cut to `limit` first and comes back short.
    for n in range(6):
        recipe = make_recipe(client, f"Apple bake {n}", [("1 apple", 1, "unit", False)])
        if n % 2 == 0:
            set_favorite(client, recipe["id"], True)

    body = client.get(
        "/api/recipes", params={"search": "apple", "favorites_only": True, "limit": 2}
    ).json()
    assert body["total"] == 3
    assert len(body["items"]) == 2
    assert all(r["is_favorite"] for r in body["items"])

    page_two = client.get(
        "/api/recipes",
        params={"search": "apple", "favorites_only": True, "limit": 2, "offset": 2},
    ).json()
    assert page_two["total"] == 3
    assert len(page_two["items"]) == 1

    seen = {r["id"] for r in body["items"]} | {r["id"] for r in page_two["items"]}
    assert len(seen) == 3
