"""Diet and meal-type classification.

The cases here are drawn from the real scraped corpus, because the failure mode
that matters is not "the keyword list is short" but "a plausible-looking line
produces a confidently wrong label".
"""

from __future__ import annotations

import pytest

from app.models.enums import DietClass, MealType
from app.services.classify import classify_diet, classify_meal_type


def lines(*raw: str) -> list[tuple[str, bool]]:
    return [(r, False) for r in raw]


# --- diet --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("800g bavette steak", "beef"),
        ("400g braising beef (any cut will do)", "beef"),
        ("12 rashers smoked streaky bacon or pancetta", "pork"),
        ("340g can of Spam", "pork"),
        ("500g Italian-style sausages", "pork"),
        ("8 boneless, skinless chicken breasts", "chicken"),
        ("1kg lean goat/venison/lamb on the bone", "lamb"),
        ("200g cooked and peeled tiger prawns", "fish"),
        ("2 tbsp fish sauce (nam pla)", "fish"),
    ],
)
def test_names_the_meat(raw: str, expected: str) -> None:
    result = classify_diet(lines(raw))
    assert result.diet == DietClass.MEAT
    assert expected in result.meat_types


def test_eggs_and_dairy_are_vegetarian_not_vegan() -> None:
    result = classify_diet(lines("3 large eggs", "150ml milk", "100g plain flour"))
    assert result.diet == DietClass.VEGETARIAN
    assert result.meat_types == []


def test_plant_only_is_vegan() -> None:
    result = classify_diet(lines("25ml peach schnapps", "1 lemon juiced", "handful of ice"))
    assert result.diet == DietClass.VEGAN


def test_nut_butter_and_plant_milk_do_not_make_a_recipe_vegetarian() -> None:
    """`butter` and `milk` are dairy words that plant products borrow."""
    result = classify_diet(lines("2 tbsp peanut butter", "200ml oat milk", "1 butternut squash"))
    assert result.diet == DietClass.VEGAN


def test_optional_ingredients_do_not_decide_the_diet() -> None:
    """Kimchi written as "fish sauce (optional)" is vegan for anyone omitting it."""
    result = classify_diet(
        [("1 Chinese cabbage", False), ("2 tbsp fish sauce (optional)", True)]
    )
    assert result.diet == DietClass.VEGAN
    assert result.meat_types == []


def test_serving_suggestions_do_not_decide_the_diet() -> None:
    """A real corpus line that made a pancake recipe register as pork."""
    result = classify_diet(
        lines(
            "200g self-raising flour",
            "200ml milk",
            "toppings of your choice, such as cooked bacon, blueberries or peanut butter",
        )
    )
    assert result.diet == DietClass.VEGETARIAN
    assert result.meat_types == []


def test_a_meat_or_vegetable_alternative_is_not_meat() -> None:
    """"Chicken or vegetable stock" describes a soup that works either way."""
    result = classify_diet(
        lines("850ml light chicken or vegetable stock", "450g potatoes", "50g butter")
    )
    assert result.diet == DietClass.VEGETARIAN
    assert result.meat_types == []


def test_stock_with_no_alternative_still_counts() -> None:
    result = classify_diet(lines("about 1 litre chicken stock", "2 eggs"))
    assert result.diet == DietClass.MEAT
    assert result.meat_types == ["chicken"]


def test_hidden_animal_products_block_vegetarian_without_naming_a_meat() -> None:
    result = classify_diet(lines("1 tbsp Worcestershire sauce", "2 tomatoes"))
    assert result.diet == DietClass.MEAT
    assert result.meat_types == []


def test_a_recipe_can_name_several_meats() -> None:
    result = classify_diet(lines("12 chipolatas", "350g bavette steak"))
    assert result.meat_types == ["beef", "pork"]


# --- meal type ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("tags", "expected"),
    [
        (["Breakfast", "Brunch", "Dessert", "German"], MealType.BREAKFAST),
        (["Dessert", "Treat"], MealType.DESSERT),
        (["American", "Drink"], MealType.DRINK),
        (["Lunch", "Main course", "Supper", "Thai"], MealType.LUNCH),
        (["British", "Dinner", "Soup"], MealType.DINNER),
        (["Korean", "Side dish"], MealType.SIDE),
    ],
)
def test_tags_decide_the_meal_type(tags: list[str], expected: MealType) -> None:
    assert classify_meal_type("Something", tags, lines("1 onion"), False) == expected


def test_breakfast_outranks_dessert() -> None:
    """A Dutch baby is tagged Breakfast, Brunch *and* Dessert; it is breakfast."""
    assert (
        classify_meal_type("Dutch baby", ["Dessert", "Breakfast"], lines("3 eggs"), False)
        == MealType.BREAKFAST
    )


def test_lunch_outranks_side() -> None:
    """Spam musubi is tagged Lunch and Side dish; it is lunch."""
    assert (
        classify_meal_type("Spam musubi", ["Side dish", "Lunch"], lines("rice"), True)
        == MealType.LUNCH
    )


def test_untagged_recipes_fall_back_to_the_title() -> None:
    assert classify_meal_type("Pavlova-misu", [], lines("3 punnets raspberries"), False) == (
        MealType.DESSERT
    )
    assert classify_meal_type("Green tea shot", [], lines("25ml whiskey"), False) == (
        MealType.DRINK
    )


def test_an_untagged_sweet_bake_is_a_dessert_even_with_an_unknown_name() -> None:
    """"Karpatka" is in no keyword list, but sugar plus flour and no aromatics is."""
    assert (
        classify_meal_type(
            "Karpatka",
            [],
            lines("120g golden caster sugar", "100g self-raising flour", "3 eggs beaten"),
            False,
        )
        == MealType.DESSERT
    )


def test_an_untagged_meat_dish_is_dinner() -> None:
    assert (
        classify_meal_type("Braised beef with carlin peas", [], lines("400g braising beef"), True)
        == MealType.DINNER
    )


def test_a_savoury_untagged_dish_is_not_guessed_at() -> None:
    """Better an honest "other" than a confident wrong label."""
    assert (
        classify_meal_type(
            "How to cook long-stem broccoli", [], lines("400g long-stem broccoli"), False
        )
        == MealType.OTHER
    )
