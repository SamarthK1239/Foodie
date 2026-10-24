from __future__ import annotations

import pytest

from app.config import settings
from app.services import barcode as barcode_service
from tests.test_recipes_api import add_item


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


@pytest.fixture
def off(monkeypatch):
    """Stub OpenFoodFacts and record how often the network was actually touched."""
    calls: list[str] = []
    responses: dict[str, dict] = {}

    def fake_get(url: str, **_kwargs):
        code = url.rsplit("/", 1)[-1].removesuffix(".json")
        calls.append(code)
        return FakeResponse(responses.get(code, {"status": 0}))

    monkeypatch.setattr(barcode_service.httpx, "get", fake_get)
    return type("Off", (), {"calls": calls, "products": responses})()


def scan(client, code: str, **params) -> dict:
    response = client.get(f"/api/scan/barcode/{code}", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def test_unknown_barcode_is_a_clean_miss_not_an_error(client, off):
    data = scan(client, "0000000000000")
    assert data["found"] is False
    assert data["name"] is None
    assert off.calls == ["0000000000000"]


def test_known_product_is_parsed_and_matched_to_an_existing_ingredient(client, off):
    add_item(client, "milk", 1000, "ml")
    off.products["5000112345678"] = {
        "status": 1,
        "product": {
            "product_name": "Tesco British Semi Skimmed Milk",
            "brands": "Tesco",
            "product_quantity": "2272",
            "product_quantity_unit": "ml",
        },
    }

    data = scan(client, "5000112345678")
    assert data["found"] is True
    assert data["name"] == "Tesco British Semi Skimmed Milk"
    assert data["brand"] == "Tesco"
    assert data["quantity"] == 2272
    assert data["unit"] == "ml"
    # The brand and the packaging words must not stop it matching plain milk.
    assert data["ingredient_name"] == "Milk"


def test_quantity_falls_back_to_the_free_text_label(client, off):
    off.products["111"] = {
        "status": 1,
        "product": {"product_name": "Butter", "quantity": "250 g"},
    }
    data = scan(client, "111")
    assert (data["quantity"], data["unit"]) == (250, "g")


def test_second_scan_is_served_from_the_cache(client, off):
    off.products["222"] = {"status": 1, "product": {"product_name": "Butter"}}
    scan(client, "222")
    second = scan(client, "222")
    assert second["source"] == "cache"
    assert off.calls == ["222"]


def test_refresh_bypasses_the_cache(client, off):
    off.products["333"] = {"status": 1, "product": {"product_name": "Butter"}}
    scan(client, "333")
    refreshed = scan(client, "333", refresh=True)
    assert refreshed["source"] == "openfoodfacts"
    assert off.calls == ["333", "333"]


def test_network_failure_degrades_to_manual_entry(client, monkeypatch):
    import httpx

    def boom(*_args, **_kwargs):
        raise httpx.ConnectError("no route")

    monkeypatch.setattr(barcode_service.httpx, "get", boom)
    data = scan(client, "444")
    assert data["found"] is False


def test_lookup_can_be_switched_off_entirely(client, off, monkeypatch):
    monkeypatch.setattr(settings, "barcode_lookup_enabled", False)
    data = scan(client, "555")
    assert (data["found"], data["source"]) == (False, "disabled")
    assert off.calls == []


def test_non_numeric_barcode_is_rejected_without_a_lookup(client, off):
    data = scan(client, "abc")
    assert (data["found"], data["source"]) == (False, "invalid")
    assert off.calls == []


def test_adding_a_scan_to_inventory_remembers_what_the_barcode_was(client, off):
    off.products["666"] = {
        "status": 1,
        "product": {"product_name": "Own Brand Baked Beans", "quantity": "400 g"},
    }
    scan(client, "666")

    response = client.post(
        "/api/scan/to-inventory",
        json={
            "barcode": "666",
            "ingredient_name": "baked beans",
            "quantity": 400,
            "unit": "g",
        },
    )
    assert response.status_code == 201, response.text
    item = response.json()
    assert item["ingredient"]["display_name"] == "Baked Beans"
    assert item["quantity"] == 400

    # The next scan needs no guessing, and no network call.
    off.calls.clear()
    again = scan(client, "666")
    assert again["source"] == "cache"
    assert again["match_method"] == "remembered"
    assert again["ingredient_id"] == item["ingredient"]["id"]
    assert off.calls == []


def test_a_remembered_mapping_survives_a_refresh(client, off):
    """A corrected mapping must outrank whatever a later fuzzy guess would produce."""
    add_item(client, "milk", 1000, "ml")
    off.products["777"] = {"status": 1, "product": {"product_name": "Mystery Carton"}}
    scan(client, "777")
    client.post(
        "/api/scan/to-inventory",
        json={"barcode": "777", "ingredient_name": "milk", "quantity": 1, "unit": "l"},
    )

    refreshed = scan(client, "777", refresh=True)
    assert refreshed["ingredient_name"] == "Milk"
