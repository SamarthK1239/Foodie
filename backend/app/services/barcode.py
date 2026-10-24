"""Barcode -> product lookup, cached locally so a rescan never re-hits the network.

Brand names are deliberately matched against the existing ingredient vocabulary
rather than added to it: "Tesco British Semi Skimmed Milk" is a package of milk,
not a new ingredient, and creating it as one would silently stop recipes from
matching the stock you just scanned.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Ingredient, ProductLookup
from app.services.ingredients import IngredientResolver
from app.services.units import is_known_unit, normalize_unit

logger = logging.getLogger(__name__)

_BARCODE_RE = re.compile(r"[^0-9]")
_QUANTITY_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*([a-zA-Z]+)")

# The brand prefix is noise when matching against an ingredient vocabulary, but the
# packaging words are worse: they turn "milk" into something no recipe asks for.
_PACKAGING_NOISE = re.compile(
    r"\b(organic|free range|semi[- ]skimmed|skimmed|whole|fresh|pure|natural|"
    r"finest|value|essential|classic|original|extra|premium|unsalted|salted)\b",
    re.IGNORECASE,
)


@dataclass(slots=True)
class ProductInfo:
    """What a scan could work out about a product. `found` false means: ask the user."""

    barcode: str
    found: bool
    source: str
    name: str | None = None
    brand: str | None = None
    quantity: float | None = None
    unit: str | None = None
    ingredient_id: int | None = None
    ingredient_name: str | None = None
    match_method: str = "unmatched"
    match_confidence: float = 0.0


def normalize_barcode(raw: str) -> str:
    return _BARCODE_RE.sub("", raw or "")


def _parse_quantity(product: dict) -> tuple[float | None, str | None]:
    """Prefer OpenFoodFacts' parsed quantity, fall back to the free-text label."""
    raw_qty = product.get("product_quantity")
    raw_unit = product.get("product_quantity_unit")
    if raw_qty not in (None, ""):
        try:
            value = float(raw_qty)
        except (TypeError, ValueError):
            value = None
        if value is not None and value > 0:
            unit = normalize_unit(raw_unit) if raw_unit else "g"
            return value, unit if is_known_unit(unit) else None

    match = _QUANTITY_RE.search(str(product.get("quantity") or ""))
    if match:
        value = float(match.group(1).replace(",", "."))
        unit = normalize_unit(match.group(2))
        if value > 0 and is_known_unit(unit):
            return value, unit
    return None, None


def _searchable_name(name: str, brand: str | None) -> str:
    """Strip the brand and marketing words so the vocabulary match has a chance."""
    cleaned = name
    if brand:
        for part in brand.split(","):
            part = part.strip()
            if part:
                cleaned = re.sub(re.escape(part), " ", cleaned, flags=re.IGNORECASE)
    cleaned = _PACKAGING_NOISE.sub(" ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -,")
    return cleaned or name


def _match_product(session: Session, name: str, brand: str | None):
    """Match a product name against the ingredient vocabulary, head noun last.

    Product names are head-final noun phrases ("Tesco British Semi Skimmed Milk"),
    so when the whole string matches nothing, progressively dropping leading words
    finds the real ingredient. That beats maintaining an endless list of marketing
    adjectives to strip.
    """
    resolver = IngredientResolver(session)
    cleaned = _searchable_name(name, brand)
    result = resolver.match(cleaned)
    if result.ingredient is not None:
        return result

    words = cleaned.split()
    for start in range(1, len(words)):
        candidate = resolver.match(" ".join(words[start:]))
        if candidate.ingredient is not None:
            return candidate
    return result


def _fetch_openfoodfacts(barcode: str) -> dict | None:
    url = f"{settings.openfoodfacts_url.rstrip('/')}/api/v2/product/{barcode}.json"
    params = {
        "fields": (
            "product_name,product_name_en,brands,quantity,"
            "product_quantity,product_quantity_unit,categories"
        )
    }
    try:
        response = httpx.get(
            url,
            params=params,
            timeout=settings.barcode_timeout_seconds,
            headers={"User-Agent": settings.scrape_user_agent},
            follow_redirects=True,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Barcode lookup failed for %s: %s", barcode, exc)
        return None

    # An unknown barcode is a normal outcome, not an error: status 0 with no product.
    if not payload.get("status") or not payload.get("product"):
        return None
    return payload["product"]


def _to_info(entry: ProductLookup, source: str, session: Session) -> ProductInfo:
    ingredient_name = None
    if entry.ingredient_id is not None:
        ingredient = session.get(Ingredient, entry.ingredient_id)
        if ingredient is not None:
            ingredient_name = ingredient.display_name
    return ProductInfo(
        barcode=entry.barcode,
        found=True,
        source=source,
        name=entry.name,
        brand=entry.brand,
        quantity=entry.quantity,
        unit=entry.unit,
        ingredient_id=entry.ingredient_id,
        ingredient_name=ingredient_name,
        match_method="remembered" if entry.ingredient_id is not None else "unmatched",
        match_confidence=100.0 if entry.ingredient_id is not None else 0.0,
    )


def cached_entry(session: Session, barcode: str) -> ProductLookup | None:
    return session.execute(
        select(ProductLookup).where(ProductLookup.barcode == barcode)
    ).scalar_one_or_none()


def lookup_barcode(session: Session, raw_barcode: str, *, refresh: bool = False) -> ProductInfo:
    """Resolve a barcode from the local cache, then OpenFoodFacts, then give up gracefully."""
    barcode = normalize_barcode(raw_barcode)
    if not barcode:
        return ProductInfo(barcode=raw_barcode, found=False, source="invalid")

    entry = cached_entry(session, barcode)
    if entry is not None and not refresh:
        return _to_info(entry, "cache", session)

    if not settings.barcode_lookup_enabled:
        return ProductInfo(barcode=barcode, found=False, source="disabled")

    product = _fetch_openfoodfacts(barcode)
    if product is None:
        # Nothing known: the caller falls back to manual entry rather than failing.
        return ProductInfo(barcode=barcode, found=False, source="openfoodfacts")

    name = (product.get("product_name_en") or product.get("product_name") or "").strip()
    if not name:
        return ProductInfo(barcode=barcode, found=False, source="openfoodfacts")
    brand = (product.get("brands") or "").strip() or None
    quantity, unit = _parse_quantity(product)

    match = _match_product(session, name, brand)

    if entry is None:
        entry = ProductLookup(barcode=barcode)
        session.add(entry)
    entry.name = name[:255]
    entry.brand = brand[:255] if brand else None
    entry.quantity = quantity
    entry.unit = unit
    entry.source = "openfoodfacts"
    # A previously remembered mapping outranks a fresh fuzzy guess.
    if entry.ingredient_id is None and match.ingredient is not None:
        entry.ingredient_id = match.ingredient.id
    entry.raw = json.dumps(product)[:4000]
    session.flush()

    info = _to_info(entry, "openfoodfacts", session)
    if match.ingredient is not None and info.match_method == "remembered":
        info.match_method = match.method
        info.match_confidence = match.score
    return info


def remember_product(
    session: Session,
    raw_barcode: str,
    *,
    ingredient_id: int,
    name: str | None = None,
    quantity: float | None = None,
    unit: str | None = None,
) -> ProductLookup:
    """Record what a barcode actually was, so the next scan needs no guessing."""
    barcode = normalize_barcode(raw_barcode)
    entry = cached_entry(session, barcode)
    if entry is None:
        entry = ProductLookup(barcode=barcode, name=name or barcode, source="manual")
        session.add(entry)
    elif entry.source == "manual" and name:
        # Keep whatever the product is actually called on the packaging; the typed
        # value is the ingredient it counts as, not a better label for the product.
        entry.name = name[:255]
    if quantity is not None:
        entry.quantity = quantity
    if unit:
        entry.unit = unit
    entry.ingredient_id = ingredient_id
    session.flush()
    return entry
