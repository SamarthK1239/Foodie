import type { DietClass, MealType, MeatType } from '../api/types'

export const MEAL_TYPE_LABELS: Record<MealType, string> = {
  breakfast: 'Breakfast',
  lunch: 'Lunch',
  dinner: 'Dinner',
  dessert: 'Dessert',
  side: 'Side',
  drink: 'Drink',
  other: 'Other',
}

export const MEAT_TYPE_LABELS: Record<MeatType, string> = {
  beef: 'Beef',
  pork: 'Pork',
  chicken: 'Chicken & poultry',
  lamb: 'Lamb & goat',
  fish: 'Fish & seafood',
  game: 'Game',
}

export const DIET_LABELS: Record<DietClass, string> = {
  vegan: 'Vegan',
  vegetarian: 'Vegetarian',
  meat: 'Contains meat',
}

/**
 * The diet filter is one control rather than two because that is how the choice
 * is actually made: you want vegetarian food, or you want beef, never both.
 * Values are namespaced so the page knows which query parameter to send.
 */
export type DietFilter = `diet:${DietClass}` | `meat:${MeatType}` | ''

export const DIET_FILTER_OPTIONS: { value: DietFilter; label: string }[] = [
  { value: '', label: 'Any diet' },
  { value: 'diet:vegan', label: 'Vegan' },
  { value: 'diet:vegetarian', label: 'Vegetarian' },
  { value: 'diet:meat', label: 'Contains meat' },
  ...(Object.keys(MEAT_TYPE_LABELS) as MeatType[]).map((m) => ({
    value: `meat:${m}` as DietFilter,
    label: MEAT_TYPE_LABELS[m],
  })),
]

export function dietFilterParams(value: DietFilter): {
  diet?: DietClass
  meat?: MeatType
} {
  if (!value) return {}
  const [kind, rest] = value.split(':')
  return kind === 'diet' ? { diet: rest as DietClass } : { meat: rest as MeatType }
}

/**
 * Tags that produced the meal-type badge, so the card does not render
 * "Dessert Dessert" or "Breakfast Breakfast Brunch". Mirrors the backend's
 * TAG_PRIORITY; it is presentation only, so drift costs at most a redundant
 * chip rather than a wrong label.
 */
const MEAL_TYPE_SOURCE_TAGS: Record<MealType, string[]> = {
  breakfast: ['breakfast', 'brunch'],
  dessert: ['dessert', 'pudding', 'treat', 'baking', 'sweets'],
  drink: ['drink', 'drinks', 'cocktail', 'beverage', 'smoothie'],
  lunch: ['lunch', 'light lunch'],
  dinner: ['dinner', 'supper', 'main course', 'main', 'mains'],
  side: [
    'side dish',
    'side',
    'sides',
    'starter',
    'snack',
    'appetizer',
    'appetiser',
    'accompaniment',
    'condiment',
  ],
  other: [],
}

export function tagsWorthShowing(tags: string[], mealType: MealType | null): string[] {
  const covered = new Set(mealType ? MEAL_TYPE_SOURCE_TAGS[mealType] : [])
  return tags.filter((tag) => !covered.has(tag.trim().toLowerCase()))
}

/** The short badge shown on a recipe card: the named meats, else the diet. */
export function dietBadge(
  diet: DietClass | null,
  meatTypes: MeatType[],
): { label: string; tone: 'green' | 'neutral' } | null {
  if (meatTypes.length > 0) {
    return { label: meatTypes.map((m) => MEAT_TYPE_LABELS[m] ?? m).join(' · '), tone: 'neutral' }
  }
  if (diet === 'vegan') return { label: 'Vegan', tone: 'green' }
  if (diet === 'vegetarian') return { label: 'Vegetarian', tone: 'green' }
  // A meat dish with no nameable meat got there via a hidden animal product
  // such as anchovy in Worcestershire sauce, so say that rather than nothing.
  if (diet === 'meat') return { label: 'Contains animal products', tone: 'neutral' }
  return null
}
