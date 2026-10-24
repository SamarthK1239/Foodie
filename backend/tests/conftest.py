from __future__ import annotations

import atexit
import os
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path

# Must be set before `app.config` is imported so the app never touches a real /data dir.
_TMP_ROOT = Path(tempfile.mkdtemp(prefix="foodie-tests-"))
atexit.register(shutil.rmtree, _TMP_ROOT, ignore_errors=True)
os.environ["FOODIE_DATA_DIR"] = str(_TMP_ROOT)
os.environ["FOODIE_SEED_ON_FIRST_RUN"] = "false"

import pytest  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from alembic import command  # noqa: E402
from app.db import create_db_engine, get_session  # noqa: E402
from app.main import create_app  # noqa: E402

BACKEND_ROOT = Path(__file__).resolve().parent.parent


def _migrate(engine) -> None:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


@pytest.fixture
def engine(db_path: Path):
    eng = create_db_engine(f"sqlite:///{db_path}")
    _migrate(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def session_factory(engine) -> sessionmaker:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


@pytest.fixture
def session(session_factory) -> Iterator[Session]:
    db = session_factory()
    try:
        yield db
        db.commit()
    finally:
        db.close()


@pytest.fixture
def client(session_factory) -> Iterator[TestClient]:
    app = create_app()

    def override() -> Iterator[Session]:
        db = session_factory()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    app.dependency_overrides[get_session] = override
    # The real lifespan would migrate the configured database; the fixtures already
    # provide a migrated one, so it is bypassed here.
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
