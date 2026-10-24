"""Database bootstrap: detect a dropped-in database, migrate it, and seed only if empty."""

from __future__ import annotations

import logging
from pathlib import Path

from alembic.config import Config
from sqlalchemy import func, select

from alembic import command
from app.config import settings
from app.db import SessionLocal, engine
from app.models import Recipe

logger = logging.getLogger(__name__)

BACKEND_ROOT = Path(__file__).resolve().parent.parent
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"


def _alembic_config() -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    return config


def run_migrations() -> None:
    """Bring whatever database is present at the configured path up to head."""
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    existed = settings.db_path.exists()
    logger.info(
        "Using database %s (%s)",
        settings.db_path,
        "existing file detected" if existed else "creating new file",
    )
    config = _alembic_config()
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    logger.info("Database schema is up to date")


def recipe_count() -> int:
    with SessionLocal() as session:
        return session.execute(select(func.count()).select_from(Recipe)).scalar_one()


def needs_seeding() -> bool:
    """Seed only when the database holds no recipes, so restarts never re-index."""
    if not settings.seed_on_first_run:
        return False
    count = recipe_count()
    if count:
        logger.info("Found %d existing recipes, skipping initial seed", count)
        return False
    return True
