from __future__ import annotations

import enum


class StorageLocation(enum.StrEnum):
    FRIDGE = "fridge"
    FREEZER = "freezer"
    PANTRY = "pantry"
    OTHER = "other"


class ItemStatus(enum.StrEnum):
    ACTIVE = "active"
    CONSUMED = "consumed"
    DISCARDED = "discarded"


class TransactionReason(enum.StrEnum):
    PURCHASE = "purchase"
    COOK = "cook"
    WASTE = "waste"
    MANUAL_ADJUST = "manual_adjust"


class GrocerySource(enum.StrEnum):
    AUTO_DEPLETED = "auto_depleted"
    MANUAL = "manual"
    RECIPE_GAP = "recipe_gap"
    PERIOD_REVIEW = "period_review"
    MEAL_PLAN = "meal_plan"


class GroceryStatus(enum.StrEnum):
    PENDING = "pending"
    PURCHASED = "purchased"
    DISMISSED = "dismissed"


class IngestStatus(enum.StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class IngestMode(enum.StrEnum):
    SEED = "seed"
    NEW_ONLY = "new_only"
    REVALIDATE = "revalidate"


class ExpiryBucket(enum.StrEnum):
    EXPIRED = "expired"
    CRITICAL = "critical"
    SOON = "soon"
    OK = "ok"
    NONE = "none"


class DietClass(enum.StrEnum):
    """Inferred from the ingredient list. VEGAN is a strict subset of
    VEGETARIAN, so a vegetarian filter must match both."""

    VEGAN = "vegan"
    VEGETARIAN = "vegetarian"
    MEAT = "meat"
    UNKNOWN = "unknown"


class MealType(enum.StrEnum):
    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"
    DESSERT = "dessert"
    SIDE = "side"
    DRINK = "drink"
    OTHER = "other"


class LeftoverState(enum.StrEnum):
    """Phase 2 groundwork: what happened to a cooked dish."""

    IN_FRIDGE = "in_fridge"
    FINISHED = "finished"
