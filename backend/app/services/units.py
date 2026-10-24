"""Unit normalisation and conversion.

Quantities are converted into one of three canonical dimensions: mass (grams),
volume (millilitres) or count. Cross-dimension conversion is only attempted when a
density is supplied; otherwise the two quantities are treated as incomparable and the
caller is expected to surface that rather than guess.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Dimension(StrEnum):
    MASS = "mass"
    VOLUME = "volume"
    COUNT = "count"


@dataclass(frozen=True)
class UnitDef:
    canonical: str
    dimension: Dimension
    factor: float  # multiply a quantity in this unit by factor to get the base unit


_BASE_UNITS: dict[Dimension, str] = {
    Dimension.MASS: "g",
    Dimension.VOLUME: "ml",
    Dimension.COUNT: "unit",
}

# alias -> (canonical name, dimension, factor to base unit)
_UNIT_TABLE: dict[str, UnitDef] = {}


def _register(canonical: str, dimension: Dimension, factor: float, aliases: list[str]) -> None:
    for alias in [canonical, *aliases]:
        _UNIT_TABLE[alias.lower()] = UnitDef(canonical, dimension, factor)


# Mass
_register("g", Dimension.MASS, 1.0, ["gram", "grams", "gm", "gms", "g."])
_register("kg", Dimension.MASS, 1000.0, ["kilogram", "kilograms", "kilo", "kilos"])
_register("mg", Dimension.MASS, 0.001, ["milligram", "milligrams"])
_register("oz", Dimension.MASS, 28.349523125, ["ounce", "ounces", "oz."])
_register("lb", Dimension.MASS, 453.59237, ["pound", "pounds", "lbs", "lb."])

# Volume
_register("ml", Dimension.VOLUME, 1.0, ["millilitre", "millilitres", "milliliter", "milliliters"])
_register("l", Dimension.VOLUME, 1000.0, ["litre", "litres", "liter", "liters"])
_register("tsp", Dimension.VOLUME, 4.92892159375, ["teaspoon", "teaspoons", "t", "tsps", "tsp."])
_register(
    "tbsp",
    Dimension.VOLUME,
    14.78676478125,
    ["tablespoon", "tablespoons", "tbs", "tbsps", "tbl", "tbsp."],
)
_register("cup", Dimension.VOLUME, 236.5882365, ["cups", "c"])
_register("fl oz", Dimension.VOLUME, 29.5735295625, ["fluid ounce", "fluid ounces", "floz"])
_register("pint", Dimension.VOLUME, 473.176473, ["pints", "pt"])
_register("quart", Dimension.VOLUME, 946.352946, ["quarts", "qt"])
_register("gallon", Dimension.VOLUME, 3785.411784, ["gallons", "gal"])

# Count-like
_register("unit", Dimension.COUNT, 1.0, ["units", "", "whole", "piece", "pieces", "pc", "pcs"])
_register("clove", Dimension.COUNT, 1.0, ["cloves"])
_register("slice", Dimension.COUNT, 1.0, ["slices"])
_register("can", Dimension.COUNT, 1.0, ["cans", "tin", "tins"])
_register("package", Dimension.COUNT, 1.0, ["packages", "pack", "packs", "pkg", "packet"])
_register("bunch", Dimension.COUNT, 1.0, ["bunches"])
_register("pinch", Dimension.COUNT, 1.0, ["pinches"])
_register("dash", Dimension.COUNT, 1.0, ["dashes"])
_register("handful", Dimension.COUNT, 1.0, ["handfuls"])
_register("sprig", Dimension.COUNT, 1.0, ["sprigs"])
_register("stalk", Dimension.COUNT, 1.0, ["stalks"])
_register("head", Dimension.COUNT, 1.0, ["heads"])


class IncompatibleUnitsError(ValueError):
    """Raised when two quantities cannot be meaningfully compared."""


def normalize_unit(unit: str | None) -> str:
    """Map a free-text unit onto its canonical name, defaulting to a countable unit."""
    if unit is None:
        return "unit"
    key = unit.strip().lower().rstrip(".")
    if key in _UNIT_TABLE:
        return _UNIT_TABLE[key].canonical
    key_nodot = key.replace(".", "")
    if key_nodot in _UNIT_TABLE:
        return _UNIT_TABLE[key_nodot].canonical
    return unit.strip().lower() or "unit"


def lookup(unit: str | None) -> UnitDef | None:
    if unit is None:
        return _UNIT_TABLE["unit"]
    key = unit.strip().lower().rstrip(".")
    return _UNIT_TABLE.get(key) or _UNIT_TABLE.get(key.replace(".", ""))


def dimension_of(unit: str | None) -> Dimension | None:
    found = lookup(unit)
    return found.dimension if found else None


def is_known_unit(unit: str | None) -> bool:
    return lookup(unit) is not None


def to_base(
    quantity: float, unit: str | None
) -> tuple[float, Dimension]:
    """Convert a quantity to its canonical base unit (g, ml or unit)."""
    found = lookup(unit)
    if found is None:
        raise IncompatibleUnitsError(f"Unknown unit {unit!r}")
    return quantity * found.factor, found.dimension


def convert(
    quantity: float,
    from_unit: str | None,
    to_unit: str | None,
    density_g_per_ml: float | None = None,
) -> float:
    """Convert between units, bridging mass/volume only when a density is available."""
    source = lookup(from_unit)
    target = lookup(to_unit)
    if source is None or target is None:
        if normalize_unit(from_unit) == normalize_unit(to_unit):
            return quantity
        raise IncompatibleUnitsError(f"Unknown unit in conversion {from_unit!r} -> {to_unit!r}")

    base_qty = quantity * source.factor
    if source.dimension == target.dimension:
        return base_qty / target.factor

    if density_g_per_ml and density_g_per_ml > 0:
        if source.dimension == Dimension.VOLUME and target.dimension == Dimension.MASS:
            return (base_qty * density_g_per_ml) / target.factor
        if source.dimension == Dimension.MASS and target.dimension == Dimension.VOLUME:
            return (base_qty / density_g_per_ml) / target.factor

    raise IncompatibleUnitsError(
        f"Cannot convert {source.dimension.value} to {target.dimension.value} without a density"
    )


def try_convert(
    quantity: float,
    from_unit: str | None,
    to_unit: str | None,
    density_g_per_ml: float | None = None,
) -> float | None:
    """Conversion variant returning None instead of raising."""
    try:
        return convert(quantity, from_unit, to_unit, density_g_per_ml)
    except IncompatibleUnitsError:
        return None


def base_unit_for(unit: str | None) -> str:
    dim = dimension_of(unit)
    return _BASE_UNITS[dim] if dim else normalize_unit(unit)


def format_quantity(quantity: float, unit: str | None) -> str:
    rounded = round(quantity, 2)
    text = f"{int(rounded)}" if rounded == int(rounded) else f"{rounded:g}"
    canonical = normalize_unit(unit)
    if canonical == "unit":
        return text
    return f"{text} {canonical}"
