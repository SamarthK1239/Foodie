from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import (
    GrocerySource,
    GroceryStatus,
    IngestMode,
    IngestStatus,
    ItemStatus,
    LeftoverState,
    StorageLocation,
    TransactionReason,
)


def utcnow() -> datetime:
    return datetime.now(UTC)


class Ingredient(Base):
    """Canonical ingredient. Recipe lines and inventory items both resolve to these."""

    __tablename__ = "ingredient"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str | None] = mapped_column(String(80), index=True)
    default_unit: Mapped[str | None] = mapped_column(String(32))
    density_g_per_ml: Mapped[float | None] = mapped_column(Float)
    typical_shelf_life_days: Mapped[int | None] = mapped_column(Integer)
    restock_threshold: Mapped[float | None] = mapped_column(Float)
    restock_unit: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    aliases: Mapped[list[IngredientAlias]] = relationship(
        back_populates="ingredient", cascade="all, delete-orphan", lazy="selectin"
    )
    inventory_items: Mapped[list[InventoryItem]] = relationship(back_populates="ingredient")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Ingredient {self.name!r}>"


class IngredientAlias(Base):
    __tablename__ = "ingredient_alias"
    __table_args__ = (UniqueConstraint("alias", name="uq_ingredient_alias_alias"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    ingredient_id: Mapped[int] = mapped_column(
        ForeignKey("ingredient.id", ondelete="CASCADE"), index=True
    )
    alias: Mapped[str] = mapped_column(String(200), index=True)

    ingredient: Mapped[Ingredient] = relationship(back_populates="aliases")


class InventoryItem(Base):
    """A physical thing in the kitchen. Current quantity is derived from its transactions."""

    __tablename__ = "inventory_item"

    id: Mapped[int] = mapped_column(primary_key=True)
    ingredient_id: Mapped[int] = mapped_column(ForeignKey("ingredient.id"), index=True)
    quantity: Mapped[float] = mapped_column(Float, default=0.0)
    unit: Mapped[str] = mapped_column(String(32), default="unit")
    purchase_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date, index=True)
    opened_at: Mapped[date | None] = mapped_column(Date)
    location: Mapped[StorageLocation] = mapped_column(String(16), default=StorageLocation.FRIDGE)
    cost: Mapped[float | None] = mapped_column(Float)
    status: Mapped[ItemStatus] = mapped_column(String(16), default=ItemStatus.ACTIVE, index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    ingredient: Mapped[Ingredient] = relationship(back_populates="inventory_items", lazy="joined")
    transactions: Mapped[list[InventoryTransaction]] = relationship(
        back_populates="item", cascade="all, delete-orphan"
    )


class InventoryTransaction(Base):
    """Append-only ledger of every quantity change. Enables waste/spend analytics and undo."""

    __tablename__ = "inventory_transaction"

    id: Mapped[int] = mapped_column(primary_key=True)
    inventory_item_id: Mapped[int] = mapped_column(
        ForeignKey("inventory_item.id", ondelete="CASCADE"), index=True
    )
    ingredient_id: Mapped[int] = mapped_column(ForeignKey("ingredient.id"), index=True)
    delta_qty: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(32))
    reason: Mapped[TransactionReason] = mapped_column(String(20), index=True)
    cost: Mapped[float | None] = mapped_column(Float)
    recipe_id: Mapped[int | None] = mapped_column(ForeignKey("recipe.id", ondelete="SET NULL"))
    cook_event_id: Mapped[int | None] = mapped_column(
        ForeignKey("cook_event.id", ondelete="SET NULL")
    )
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    item: Mapped[InventoryItem] = relationship(back_populates="transactions")


class Recipe(Base):
    __tablename__ = "recipe"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(300), index=True)
    source_url: Mapped[str | None] = mapped_column(String(800), unique=True)
    source_site: Mapped[str | None] = mapped_column(String(200), index=True)
    instructions: Mapped[str] = mapped_column(Text, default="")
    servings: Mapped[int | None] = mapped_column(Integer)
    total_minutes: Mapped[int | None] = mapped_column(Integer)
    image_url: Mapped[str | None] = mapped_column(String(800))
    tags: Mapped[str | None] = mapped_column(Text)
    raw_json: Mapped[str | None] = mapped_column(Text)
    is_user_edited: Mapped[bool] = mapped_column(Boolean, default=False)
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    last_scraped_at: Mapped[datetime | None] = mapped_column(DateTime)

    ingredients: Mapped[list[RecipeIngredient]] = relationship(
        back_populates="recipe", cascade="all, delete-orphan", lazy="selectin"
    )


class RecipeIngredient(Base):
    __tablename__ = "recipe_ingredient"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipe.id", ondelete="CASCADE"), index=True)
    ingredient_id: Mapped[int | None] = mapped_column(
        ForeignKey("ingredient.id", ondelete="SET NULL"), index=True
    )
    raw_text: Mapped[str] = mapped_column(Text)
    quantity: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(String(32))
    optional: Mapped[bool] = mapped_column(Boolean, default=False)
    position: Mapped[int] = mapped_column(Integer, default=0)

    recipe: Mapped[Recipe] = relationship(back_populates="ingredients")
    ingredient: Mapped[Ingredient | None] = relationship(lazy="joined")


class MealPlanEntry(Base):
    """A recipe planned for a given week. Drives the week's grocery requirements."""

    __tablename__ = "meal_plan_entry"
    __table_args__ = (
        # The same recipe twice in one week is a double batch, not two entries.
        UniqueConstraint("recipe_id", "week_start", name="uq_meal_plan_recipe_week"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(
        ForeignKey("recipe.id", ondelete="CASCADE"), index=True
    )
    week_start: Mapped[date] = mapped_column(Date, index=True)
    servings_multiplier: Mapped[float] = mapped_column(Float, default=1.0)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    recipe: Mapped[Recipe] = relationship(lazy="joined")


class CookEvent(Base):
    __tablename__ = "cook_event"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int | None] = mapped_column(ForeignKey("recipe.id", ondelete="SET NULL"))
    recipe_title: Mapped[str] = mapped_column(String(300))
    servings: Mapped[float] = mapped_column(Float, default=1.0)
    leftover_state: Mapped[LeftoverState | None] = mapped_column(String(16))
    cooked_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    note: Mapped[str | None] = mapped_column(Text)


class GroceryItem(Base):
    __tablename__ = "grocery_item"

    id: Mapped[int] = mapped_column(primary_key=True)
    ingredient_id: Mapped[int | None] = mapped_column(
        ForeignKey("ingredient.id", ondelete="CASCADE"), index=True
    )
    label: Mapped[str] = mapped_column(String(200))
    quantity: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(String(32))
    source: Mapped[GrocerySource] = mapped_column(String(20), default=GrocerySource.MANUAL)
    status: Mapped[GroceryStatus] = mapped_column(
        String(16), default=GroceryStatus.PENDING, index=True
    )
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime)


class IngestJob(Base):
    """Resumable state for a recipe crawl so restarts never redo finished work."""

    __tablename__ = "ingest_job"

    id: Mapped[int] = mapped_column(primary_key=True)
    mode: Mapped[IngestMode] = mapped_column(String(20), default=IngestMode.SEED)
    status: Mapped[IngestStatus] = mapped_column(
        String(16), default=IngestStatus.PENDING, index=True
    )
    sites: Mapped[str] = mapped_column(Text, default="")
    target_count: Mapped[int] = mapped_column(Integer, default=0)
    discovered_count: Mapped[int] = mapped_column(Integer, default=0)
    imported_count: Mapped[int] = mapped_column(Integer, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    cursor: Mapped[str | None] = mapped_column(Text)
    last_error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)


class ProductLookup(Base):
    """Cache of barcode lookups so a rescanned product never re-hits the network."""

    __tablename__ = "product_lookup"

    id: Mapped[int] = mapped_column(primary_key=True)
    barcode: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    brand: Mapped[str | None] = mapped_column(String(255))
    quantity: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(String(32))
    source: Mapped[str] = mapped_column(String(32), default="openfoodfacts")
    ingredient_id: Mapped[int | None] = mapped_column(ForeignKey("ingredient.id"), index=True)
    raw: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


Index("ix_inventory_item_status_expiry", InventoryItem.status, InventoryItem.expiry_date)
Index("ix_recipe_ingredient_ing_recipe", RecipeIngredient.ingredient_id, RecipeIngredient.recipe_id)
