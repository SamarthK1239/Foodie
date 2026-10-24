"""recipe full-text search index

Revision ID: b2f1a7c45d10
Revises: 1090c2fba5f1
"""

from collections.abc import Sequence

from alembic import op

revision: str = "b2f1a7c45d10"
down_revision: str | Sequence[str] | None = "1090c2fba5f1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # External-content FTS table: the index stores no copy of the rows, it points at
    # `recipe` by rowid, so the two can never drift apart in content.
    op.execute(
        """
        CREATE VIRTUAL TABLE recipes_fts USING fts5(
            title,
            tags,
            instructions,
            content='recipe',
            content_rowid='id',
            tokenize='unicode61'
        )
        """
    )
    op.execute(
        """
        CREATE TRIGGER recipe_ai AFTER INSERT ON recipe BEGIN
            INSERT INTO recipes_fts(rowid, title, tags, instructions)
            VALUES (new.id, new.title, new.tags, new.instructions);
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER recipe_ad AFTER DELETE ON recipe BEGIN
            INSERT INTO recipes_fts(recipes_fts, rowid, title, tags, instructions)
            VALUES ('delete', old.id, old.title, old.tags, old.instructions);
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER recipe_au AFTER UPDATE ON recipe BEGIN
            INSERT INTO recipes_fts(recipes_fts, rowid, title, tags, instructions)
            VALUES ('delete', old.id, old.title, old.tags, old.instructions);
            INSERT INTO recipes_fts(rowid, title, tags, instructions)
            VALUES (new.id, new.title, new.tags, new.instructions);
        END
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS recipe_au")
    op.execute("DROP TRIGGER IF EXISTS recipe_ad")
    op.execute("DROP TRIGGER IF EXISTS recipe_ai")
    op.execute("DROP TABLE IF EXISTS recipes_fts")
