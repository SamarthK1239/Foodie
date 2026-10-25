"""recipe diet and meal-type classification

Revision ID: a5c83f2e6b17
Revises: d7e4b81f9a35

The columns are left nullable on purpose. NULL means "not yet classified", and
the startup backfill fills them in using the live classifier rather than a copy
of the keyword lists frozen into this migration -- so an existing database picks
up the current rules instead of whatever they were when it was first migrated.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a5c83f2e6b17"
down_revision: str | Sequence[str] | None = "d7e4b81f9a35"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("recipe", sa.Column("diet", sa.String(length=16), nullable=True))
    op.add_column("recipe", sa.Column("meat_types", sa.Text(), nullable=True))
    op.add_column("recipe", sa.Column("meal_type", sa.String(length=16), nullable=True))
    op.create_index("ix_recipe_diet", "recipe", ["diet"])
    op.create_index("ix_recipe_meal_type", "recipe", ["meal_type"])


def downgrade() -> None:
    op.drop_index("ix_recipe_meal_type", table_name="recipe")
    op.drop_index("ix_recipe_diet", table_name="recipe")
    op.drop_column("recipe", "meal_type")
    op.drop_column("recipe", "meat_types")
    op.drop_column("recipe", "diet")
