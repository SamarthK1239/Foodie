from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import admin, analytics, grocery, inventory, recipes, suggestions
from app.config import settings
from app.db import SessionLocal
from app.ingest import runner
from app.models import IngestMode
from app.startup import needs_seeding, run_migrations

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    run_migrations()
    if needs_seeding() and settings.scrape_sites:
        logger.info("Empty recipe database detected, starting initial seed crawl")
        with SessionLocal() as session:
            job = runner.create_job(
                session,
                mode=IngestMode.SEED,
                sites=settings.scrape_sites,
                target=settings.scrape_max_recipes,
            )
            session.commit()
            job_id = job.id
        runner.start_job_async(job_id)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Foodie",
        description="Self-hosted food inventory, recipe suggestions and waste analytics",
        version="0.1.0",
        lifespan=lifespan,
    )

    # The app is only ever reachable over Tailscale, so CORS is permissive to keep
    # `vite dev` on a separate port working without extra configuration.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(inventory.router)
    app.include_router(inventory.ingredients_router)
    app.include_router(recipes.router)
    app.include_router(suggestions.router)
    app.include_router(grocery.router)
    app.include_router(analytics.router)
    app.include_router(admin.router)

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "database": str(settings.db_path)}

    if STATIC_DIR.is_dir():
        app.mount(
            "/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets"
        )

        @app.exception_handler(StarletteHTTPException)
        async def spa_fallback(request, exc: StarletteHTTPException):
            """Serve the SPA shell for unknown non-API routes so client routing works."""
            if exc.status_code == 404 and not request.url.path.startswith("/api"):
                index = STATIC_DIR / "index.html"
                if index.is_file():
                    return FileResponse(index)
            from fastapi.responses import JSONResponse

            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

        @app.get("/", include_in_schema=False)
        def index() -> FileResponse:
            return FileResponse(STATIC_DIR / "index.html")

    return app


app = create_app()
