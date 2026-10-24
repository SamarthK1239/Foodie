import pytest

from app.services.units import (
    Dimension,
    IncompatibleUnitsError,
    convert,
    dimension_of,
    format_quantity,
    normalize_unit,
    try_convert,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("grams", "g"),
        ("Kilograms", "kg"),
        ("tablespoon", "tbsp"),
        ("TBSP.", "tbsp"),
        ("cups", "cup"),
        ("fluid ounces", "fl oz"),
        ("", "unit"),
        (None, "unit"),
        ("cloves", "clove"),
    ],
)
def test_normalize_unit(raw, expected):
    assert normalize_unit(raw) == expected


def test_dimensions():
    assert dimension_of("kg") is Dimension.MASS
    assert dimension_of("cup") is Dimension.VOLUME
    assert dimension_of("clove") is Dimension.COUNT
    assert dimension_of("bogus") is None


def test_same_dimension_conversion():
    assert convert(1, "kg", "g") == pytest.approx(1000)
    assert convert(2, "lb", "oz") == pytest.approx(32)
    assert convert(1, "l", "ml") == pytest.approx(1000)
    assert convert(3, "tsp", "tbsp") == pytest.approx(1)


def test_cross_dimension_requires_density():
    with pytest.raises(IncompatibleUnitsError):
        convert(1, "cup", "g")
    # Water: 1 g/ml, so one cup is ~236.6 g.
    assert convert(1, "cup", "g", density_g_per_ml=1.0) == pytest.approx(236.588, rel=1e-3)
    assert convert(236.588, "g", "ml", density_g_per_ml=1.0) == pytest.approx(236.588, rel=1e-3)


def test_try_convert_returns_none_instead_of_raising():
    assert try_convert(1, "cup", "g") is None
    assert try_convert(1, "kg", "g") == pytest.approx(1000)


def test_unknown_but_identical_units_pass_through():
    assert convert(5, "blorp", "blorp") == 5


def test_count_units_are_interchangeable_within_dimension():
    assert convert(2, "clove", "unit") == pytest.approx(2)


def test_format_quantity():
    assert format_quantity(2.0, "g") == "2 g"
    assert format_quantity(2.5, "cup") == "2.5 cup"
    assert format_quantity(3.0, None) == "3"
