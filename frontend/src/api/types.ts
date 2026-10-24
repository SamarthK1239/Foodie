export type ExpiryBucket = 'expired' | 'critical' | 'soon' | 'ok' | 'none'
export type ItemStatus = 'active' | 'consumed' | 'discarded'
export type StorageLocation = 'fridge' | 'freezer' | 'pantry' | 'other'
export type GroceryStatus = 'pending' | 'purchased' | 'dismissed'
export type GrocerySource = 'auto_depleted' | 'manual' | 'recipe_gap' | 'period_review'

export interface Ingredient {
  id: number
  name: string
  display_name: string
  category: string | null
  default_unit: string | null
  density_g_per_ml: number | null
  restock_threshold: number | null
  restock_unit: string | null
}

export interface InventoryItem {
  id: number
  ingredient: Ingredient
  quantity: number
  unit: string
  purchase_date: string | null
  expiry_date: string | null
  opened_at: string | null
  location: StorageLocation
  cost: number | null
  status: ItemStatus
  notes: string | null
  expiry_bucket: ExpiryBucket
  days_left: number | null
}

export interface RecipeIngredient {
  id: number
  raw_text: string
  quantity: number | null
  unit: string | null
  optional: boolean
  ingredient: Ingredient | null
}

export interface RecipeSummary {
  id: number
  title: string
  source_site: string | null
  source_url: string | null
  image_url: string | null
  servings: number | null
  total_minutes: number | null
  tags: string[]
}

export interface Recipe extends RecipeSummary {
  instructions: string
  is_user_edited: boolean
  ingredients: RecipeIngredient[]
}

export interface RecipeList {
  total: number
  items: RecipeSummary[]
}

export interface Match {
  name: string
  raw_text: string
  have: boolean
  optional: boolean
  sufficient: boolean
  quantity_needed: number | null
  unit: string | null
  quantity_available: number | null
  urgency: number
}

export interface Suggestion {
  recipe: RecipeSummary
  score: number
  coverage: number
  urgency: number
  recently_cooked: boolean
  have: Match[]
  missing: Match[]
}

export interface CookResult {
  cook_event_id: number
  recipe_title: string
  consumed: { ingredient: string; quantity: number; unit: string | null }[]
  missing: string[]
  grocery_added: string[]
}

export interface GroceryItem {
  id: number
  ingredient_id: number | null
  label: string
  quantity: number | null
  unit: string | null
  source: GrocerySource
  status: GroceryStatus
  note: string | null
  created_at: string
}

export interface AnalyticsSummary {
  period_days: number
  total_spend: number
  items_purchased: number
  items_consumed: number
  items_discarded: number
  waste_rate: number
  active_items: number
  expiring_soon: number
  dishes_cooked: number
}

export interface InventorySummary {
  total: number
  buckets: Record<ExpiryBucket, number>
}

export interface IngestJob {
  id: number
  mode: string
  status: string
  sites: string
  target_count: number
  discovered_count: number
  imported_count: number
  skipped_count: number
  failed_count: number
  last_error: string | null
  started_at: string
  finished_at: string | null
}

export interface IngestStatusResponse {
  running: boolean
  job: IngestJob | null
  configured_sites: string[]
}

export interface AdminStats {
  recipes: number
  ingredients: number
  unmatched_recipe_lines: number
  database_path: string
}

export interface UnmatchedLine {
  recipe_id: number
  recipe_title: string
  recipe_ingredient_id: number
  raw_text: string
  suggestion: string | null
}

export interface CookEvent {
  id: number
  recipe_id: number | null
  recipe_title: string
  servings: number
  leftover_state: 'in_fridge' | 'finished' | null
  cooked_at: string
  note: string | null
}

export interface PeriodReviewUsed {
  ingredient_id: number
  name: string
  times: number
  quantity: number
}

export interface PeriodReviewUnused {
  ingredient_id: number
  item_id: number
  name: string
  quantity: number
  unit: string | null
  days_in_stock: number
  expiry_bucket: ExpiryBucket
}

export interface PeriodReviewWasted {
  ingredient_id: number
  name: string
  times: number
  cost: number
}

export interface PeriodReviewSuggestion {
  ingredient_id: number
  name: string
  times_used: number
  remaining: number
  unit: string | null
  reason: 'out_of_stock' | 'low_stock'
  already_on_list: boolean
}

export interface PeriodReview {
  weeks: number
  period_days: number
  start: string
  end: string
  used: PeriodReviewUsed[]
  unused: PeriodReviewUnused[]
  wasted: PeriodReviewWasted[]
  suggested: PeriodReviewSuggestion[]
}

export interface ScanProduct {
  barcode: string
  found: boolean
  source: string
  name: string | null
  brand: string | null
  quantity: number | null
  unit: string | null
  ingredient_id: number | null
  ingredient_name: string | null
  match_method: string
  match_confidence: number
}
