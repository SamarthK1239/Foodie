import pytest

from app.ingest.parsing import (
    clean_ingredient_name,
    normalize_ingredient_key,
    parse_ingredient_line,
)


@pytest.mark.parametrize(
    ("line", "qty", "unit", "name"),
    [
        ("2 cups all-purpose flour", 2.0, "cup", "all-purpose flour"),
        ("2 1/2 cups all-purpose flour, sifted", 2.5, "cup", "all-purpose flour"),
        ("1/2 tsp salt", 0.5, "tsp", "salt"),
        ("1 1/4 lb chicken breast", 1.25, "lb", "chicken breast"),
        ("3 large eggs", 3.0, None, "eggs"),
        ("500 g minced beef", 500.0, "g", "beef"),
        ("1 tablespoon of olive oil", 1.0, "tbsp", "olive oil"),
        ("4 cloves garlic, minced", 4.0, "clove", "garlic"),
        ("Salt and pepper to taste", None, None, "salt and pepper"),
        ("1 to 2 tbsp honey", 1.0, "tbsp", "honey"),
        ("1-2 tsp chili flakes", 1.0, "tsp", "chili flakes"),
        ("one onion, finely chopped", 1.0, None, "onion"),
    ],
)
def test_parse_ingredient_line(line, qty, unit, name):
    parsed = parse_ingredient_line(line)
    if qty is None:
        assert parsed.quantity is None
    else:
        assert parsed.quantity == pytest.approx(qty)
    assert parsed.unit == unit
    assert parsed.name == name
    assert parsed.raw_text == line.strip()


def test_vulgar_fraction():
    parsed = parse_ingredient_line("1½ cups milk")
    assert parsed.quantity == pytest.approx(1.5)
    assert parsed.unit == "cup"
    assert parsed.name == "milk"


def test_standalone_vulgar_fraction():
    parsed = parse_ingredient_line("½ cup sugar")
    assert parsed.quantity == pytest.approx(0.5)
    assert parsed.unit == "cup"


def test_pack_size_is_multiplied_out():
    parsed = parse_ingredient_line("2 (14 oz) cans diced tomatoes")
    assert parsed.quantity == pytest.approx(28.0)
    assert parsed.unit == "oz"
    assert parsed.name == "diced tomatoes" or parsed.name == "tomatoes"


def test_optional_detection():
    assert parse_ingredient_line("1 tbsp chili oil (optional)").optional is True
    assert parse_ingredient_line("Salt to taste").optional is True
    assert parse_ingredient_line("2 cups flour").optional is False


def test_clean_ingredient_name_strips_prep_words():
    assert clean_ingredient_name("freshly ground black pepper") == "black pepper"
    assert clean_ingredient_name("boneless skinless chicken thighs") == "chicken thighs"


def test_clean_ingredient_name_drops_preparation_clauses():
    # Real phrasings seen when crawling bbcgoodfood.com; each previously leaked the
    # preparation clause into the canonical name and broke pantry matching.
    assert clean_ingredient_name("butter, melted and cooled") == "butter"
    assert clean_ingredient_name("butter, plus extra for cooking") == "butter"
    assert clean_ingredient_name("red peppers, deseeded and cut into chunks") == "red peppers"
    assert clean_ingredient_name("1 small orange, cut into slices") == "orange"


def test_clean_ingredient_name_skips_leading_prep_only_clause():
    assert (
        clean_ingredient_name("boneless, skinless chicken breasts, cut into 2.5cm cubes")
        == "chicken breasts"
    )


def test_clean_ingredient_name_drops_pack_multipliers():
    assert clean_ingredient_name("2 x 400g cans chopped tomatoes") == "tomatoes"


def test_clean_ingredient_name_preserves_accented_words():
    assert clean_ingredient_name("tomato purée") == "tomato puree"
    assert clean_ingredient_name("crème fraîche") == "creme fraiche"


def test_normalize_ingredient_key_singularises():
    assert normalize_ingredient_key("Tomatoes") == "tomato"
    assert normalize_ingredient_key("Eggs") == "egg"
    assert normalize_ingredient_key("Berries") == "berry"
    assert normalize_ingredient_key("Jalapeño") == "jalapeno"
    assert normalize_ingredient_key("glass") == "glass"


def test_normalize_ingredient_key_handles_irregular_plurals():
    # "bay leaves" previously normalised to "bay leave", creating a canonical
    # ingredient distinct from "bay leaf" so pantry matching silently missed.
    assert normalize_ingredient_key("bay leaves") == normalize_ingredient_key("bay leaf")
    assert normalize_ingredient_key("basil leaves") == "basil leaf"
    assert normalize_ingredient_key("halves") == "half"
    # Genuine "-ve" words must keep the regular rule.
    assert normalize_ingredient_key("olives") == "olive"
    assert normalize_ingredient_key("chives") == "chive"


def test_empty_and_noise_lines_do_not_crash():
    assert parse_ingredient_line("   ").name is not None
    assert parse_ingredient_line("For the sauce:").name is not None
