from __future__ import annotations

from datetime import date, timedelta


def add_item(client, name, quantity=1.0, unit="unit", days_to_expiry=None, cost=None):
    payload = {"ingredient_name": name, "quantity": quantity, "unit": unit}
    if days_to_expiry is not None:
        payload["expiry_date"] = (date.today() + timedelta(days=days_to_expiry)).isoformat()
    if cost is not None:
        payload["cost"] = cost
    response = client.post("/api/inventory/items", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_and_list_item(client):
    item = add_item(client, "Tomatoes", 500, "g", days_to_expiry=3)
    assert item["quantity"] == 500
    assert item["unit"] == "g"
    assert item["ingredient"]["display_name"] == "Tomatoes"
    assert item["ingredient"]["name"] == "tomato"
    assert item["expiry_bucket"] == "soon"
    assert item["days_left"] == 3

    listing = client.get("/api/inventory/items").json()
    assert len(listing) == 1


def test_ingredient_is_reused_across_items(client):
    add_item(client, "Tomatoes", 2)
    add_item(client, "tomato", 3)
    ingredients = client.get("/api/ingredients").json()
    names = [i["name"] for i in ingredients]
    assert names.count("tomato") == 1


def test_expiry_buckets(client):
    add_item(client, "Milk", 1, "l", days_to_expiry=-1)
    add_item(client, "Cheese", 1, "unit", days_to_expiry=1)
    add_item(client, "Rice", 1, "kg", days_to_expiry=100)
    summary = client.get("/api/inventory/summary").json()
    assert summary["total"] == 3
    assert summary["buckets"]["expired"] == 1
    assert summary["buckets"]["critical"] == 1
    assert summary["buckets"]["ok"] == 1


def test_expiring_endpoint(client):
    add_item(client, "Spinach", 1, "bunch", days_to_expiry=2)
    add_item(client, "Flour", 1, "kg", days_to_expiry=200)
    expiring = client.get("/api/inventory/expiring", params={"within_days": 5}).json()
    assert len(expiring) == 1
    assert expiring[0]["ingredient"]["display_name"] == "Spinach"


def test_adjust_creates_transaction_and_updates_quantity(client):
    item = add_item(client, "Eggs", 12)
    response = client.post(
        f"/api/inventory/items/{item['id']}/adjust", json={"delta": -4, "reason": "cook"}
    )
    assert response.status_code == 200
    assert response.json()["quantity"] == 8

    transactions = client.get(f"/api/inventory/items/{item['id']}/transactions").json()
    assert len(transactions) == 2  # purchase + cook
    assert {t["reason"] for t in transactions} == {"purchase", "cook"}


def test_adjusting_to_zero_marks_consumed_and_adds_to_grocery(client):
    item = add_item(client, "Butter", 1, "unit")
    client.post(f"/api/inventory/items/{item['id']}/adjust", json={"delta": -1, "reason": "cook"})

    refreshed = client.get(f"/api/inventory/items/{item['id']}").json()
    assert refreshed["status"] == "consumed"

    grocery = client.get("/api/grocery").json()
    assert any(g["label"] == "Butter" for g in grocery)
    assert all(g["source"] == "auto_depleted" for g in grocery if g["label"] == "Butter")


def test_discard_records_waste(client):
    item = add_item(client, "Lettuce", 1)
    response = client.post(f"/api/inventory/items/{item['id']}/discard")
    assert response.status_code == 200
    assert response.json()["status"] == "discarded"

    transactions = client.get(f"/api/inventory/items/{item['id']}/transactions").json()
    assert any(t["reason"] == "waste" for t in transactions)


def test_update_item_quantity_logs_adjustment(client):
    item = add_item(client, "Sugar", 1000, "g")
    response = client.patch(f"/api/inventory/items/{item['id']}", json={"quantity": 750})
    assert response.status_code == 200
    assert response.json()["quantity"] == 750
    transactions = client.get(f"/api/inventory/items/{item['id']}/transactions").json()
    assert any(t["reason"] == "manual_adjust" for t in transactions)


def test_unit_normalisation_on_create(client):
    item = add_item(client, "Olive oil", 2, "Tablespoons")
    assert item["unit"] == "tbsp"


def test_delete_item(client):
    item = add_item(client, "Yogurt", 1)
    assert client.delete(f"/api/inventory/items/{item['id']}").status_code == 204
    assert client.get(f"/api/inventory/items/{item['id']}").status_code == 404
