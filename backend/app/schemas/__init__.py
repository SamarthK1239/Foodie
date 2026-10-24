from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    ExpiryBucket,
    GrocerySource,
    GroceryStatus,
    IngestMode,
    IngestStatus,
    ItemStatus,
    LeftoverState,
    StorageLocation,
    TransactionReason,
)


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Ingredients -----------------------------------------------------------------


class IngredientOut(ORMModel):
    id: int
    name: str
    display_name: str
    category: str | None = None
    default_unit: str | None = None
    density_g_per_ml: float | None = None
    restock_threshold: float | None = None
    restock_unit: str | None = None


class IngredientUpdate(BaseModel):
    display_name: str | None = None
    category: str | None = None
    default_unit: str | None = None
    density_g_per_ml: float | None = None
    restock_threshold: float | None = None
    restock_unit: str | None = None


# --- Inventory -------------------------------------------------------------------


class InventoryItemCreate(BaseModel):
    ingredient_name: str = Field(min_length=1, max_length=200)
    quantity: float = Field(gt=0)
    unit: str = "unit"
    purchase_date: date | None = None
    expiry_date: date | None = None
    location: StorageLocation = StorageLocation.FRIDGE
    cost: float | None = Field(default=None, ge=0)
    notes: str | None = None


class InventoryItemUpdate(BaseModel):
    quantity: float | None = Field(default=None, ge=0)
    unit: str | None = None
    purchase_date: date | None = None
    expiry_date: date | None = None
    opened_at: date | None = None
    location: StorageLocation | None = None
    cost: float | None = Field(default=None, ge=0)
    notes: str | None = None
    status: ItemStatus | None = None


class InventoryAdjust(BaseModel):
    delta: float
    unit: str | None = None
    reason: TransactionReason = TransactionReason.MANUAL_ADJUST
    note: str | None = None


class InventoryItemOut(ORMModel):
    id: int
    ingredient: IngredientOut
    quantity: float
    unit: str
    purchase_date: date | None
    expiry_date: date | None
    opened_at: date | None
    location: StorageLocation
    cost: float | None
    status: ItemStatus
    notes: str | None
    expiry_bucket: ExpiryBucket
    days_left: int | None


class TransactionOut(ORMModel):
    id: int
    inventory_item_id: int
    ingredient_id: int
    delta_qty: float
    unit: str
    reason: TransactionReason
    note: str | None
    created_at: datetime


# --- Recipes ---------------------------------------------------------------------


class RecipeIngredientIn(BaseModel):
    raw_text: str = Field(min_length=1)
    quantity: float | None = None
    unit: str | None = None
    optional: bool = False


class RecipeIngredientOut(ORMModel):
    id: int
    raw_text: str
    quantity: float | None
    unit: str | None
    optional: bool
    ingredient: IngredientOut | None = None


class RecipeCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    instructions: str = ""
    servings: int | None = Field(default=None, ge=1)
    total_minutes: int | None = Field(default=None, ge=0)
    source_url: str | None = None
    image_url: str | None = None
    tags: list[str] = []
    ingredients: list[RecipeIngredientIn] = []


class RecipeUpdate(BaseModel):
    title: str | None = None
    instructions: str | None = None
    servings: int | None = None
    total_minutes: int | None = None
    image_url: str | None = None
    tags: list[str] | None = None
    ingredients: list[RecipeIngredientIn] | None = None


class RecipeSummary(ORMModel):
    id: int
    title: str
    source_site: str | None
    source_url: str | None
    image_url: str | None
    servings: int | None
    total_minutes: int | None
    tags: list[str] = []


class RecipeOut(RecipeSummary):
    instructions: str
    is_user_edited: bool
    ingredients: list[RecipeIngredientOut] = []


class RecipeListOut(BaseModel):
    total: int
    items: list[RecipeSummary]


# --- Suggestions -----------------------------------------------------------------


class MatchOut(BaseModel):
    name: str
    raw_text: str
    have: bool
    optional: bool
    sufficient: bool
    quantity_needed: float | None
    unit: str | None
    quantity_available: float | None
    urgency: float


class SuggestionOut(BaseModel):
    recipe: RecipeSummary
    score: float
    coverage: float
    urgency: float
    recently_cooked: bool
    have: list[MatchOut]
    missing: list[MatchOut]


class CookRequest(BaseModel):
    servings_multiplier: float = Field(default=1.0, gt=0)
    add_missing_to_grocery: bool = True
    note: str | None = None


class CookedLineOut(BaseModel):
    ingredient: str
    quantity: float
    unit: str | None


class CookResultOut(BaseModel):
    cook_event_id: int
    recipe_title: str
    consumed: list[CookedLineOut]
    missing: list[str]
    grocery_added: list[str]


class CookEventOut(ORMModel):
    id: int
    recipe_id: int | None
    recipe_title: str
    servings: float
    leftover_state: LeftoverState | None
    cooked_at: datetime
    note: str | None


class LeftoverUpdate(BaseModel):
    leftover_state: LeftoverState


# --- Grocery ---------------------------------------------------------------------


class GroceryItemCreate(BaseModel):
    label: str | None = None
    ingredient_name: str | None = None
    quantity: float | None = None
    unit: str | None = None
    note: str | None = None


class GroceryItemUpdate(BaseModel):
    quantity: float | None = None
    unit: str | None = None
    status: GroceryStatus | None = None
    note: str | None = None


class GroceryItemOut(ORMModel):
    id: int
    ingredient_id: int | None
    label: str
    quantity: float | None
    unit: str | None
    source: GrocerySource
    status: GroceryStatus
    note: str | None
    created_at: datetime


# --- Ingestion -------------------------------------------------------------------


class IngestStartRequest(BaseModel):
    mode: IngestMode = IngestMode.NEW_ONLY
    sites: list[str] | None = None
    max_recipes: int | None = Field(default=None, ge=1)
    revalidate_older_than_days: int = Field(default=30, ge=1)


class IngestJobOut(ORMModel):
    id: int
    mode: IngestMode
    status: IngestStatus
    sites: str
    target_count: int
    discovered_count: int
    imported_count: int
    skipped_count: int
    failed_count: int
    last_error: str | None
    started_at: datetime
    finished_at: datetime | None


class UnmatchedLineOut(BaseModel):
    recipe_id: int
    recipe_title: str
    recipe_ingredient_id: int
    raw_text: str
    suggestion: str | None = None


class ResolveUnmatchedRequest(BaseModel):
    recipe_ingredient_id: int
    ingredient_name: str
    add_alias: bool = True


# --- Analytics -------------------------------------------------------------------


class SummaryOut(BaseModel):
    period_days: int
    total_spend: float
    items_purchased: int
    items_consumed: int
    items_discarded: int
    waste_rate: float
    active_items: int
    expiring_soon: int
    dishes_cooked: int
