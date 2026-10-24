"""barcode product lookup cache

Revision ID: c3a9e1d47b22
Revises: b2f1a7c45d10
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c3a9e1d47b22"
down_revision: str | Sequence[str] | None = "b2f1a7c45d10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "product_lookup",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("barcode", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("brand", sa.String(length=255), nullable=True),
        sa.Column("quantity", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(length=32), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("ingredient_id", sa.Integer(), nullable=True),
        sa.Column("raw", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["ingredient_id"], ["ingredient.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_product_lookup_barcode", "product_lookup", ["barcode"], unique=True)
    op.create_index("ix_product_lookup_ingredient_id", "product_lookup", ["ingredient_id"])


def downgrade() -> None:
    op.drop_index("ix_product_lookup_ingredient_id", table_name="product_lookup")
    op.drop_index("ix_product_lookup_barcode", table_name="product_lookup")
    op.drop_table("product_lookup")
