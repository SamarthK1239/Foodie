"""recipe favourites and weekly meal plan

Revision ID: d7e4b81f9a35
Revises: c3a9e1d47b22
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d7e4b81f9a35"
down_revision: str | Sequence[str] | None = "c3a9e1d47b22"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "recipe",
        sa.Column("is_favorite", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_recipe_is_favorite", "recipe", ["is_favorite"])

    op.create_table(
        "meal_plan_entry",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("recipe_id", sa.Integer(), nullable=False),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("servings_multiplier", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["recipe_id"], ["recipe.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        # The same recipe twice in one week is a double batch, not two entries.
        sa.UniqueConstraint("recipe_id", "week_start", name="uq_meal_plan_recipe_week"),
    )
    op.create_index("ix_meal_plan_entry_week_start", "meal_plan_entry", ["week_start"])
    op.create_index("ix_meal_plan_entry_recipe_id", "meal_plan_entry", ["recipe_id"])


def downgrade() -> None:
    op.drop_index("ix_meal_plan_entry_recipe_id", table_name="meal_plan_entry")
    op.drop_index("ix_meal_plan_entry_week_start", table_name="meal_plan_entry")
    op.drop_table("meal_plan_entry")
    op.drop_index("ix_recipe_is_favorite", table_name="recipe")
    op.drop_column("recipe", "is_favorite")
