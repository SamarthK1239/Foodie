"""Resumable recipe ingestion jobs.

A job records its progress in the database after every page, so an interrupted crawl
resumes from where it stopped rather than starting over.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.ingest.discovery import discover
from app.ingest.fetcher import PoliteFetcher
from app.ingest.importer import parse_recipe_html, upsert_recipe
from app.models import IngestJob, IngestMode, IngestStatus, Recipe
from app.models.entities import utcnow
from app.services.ingredients import IngredientResolver

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_active_thread: threading.Thread | None = None


def active_job(session: Session) -> IngestJob | None:
    stmt = (
        select(IngestJob)
        .where(IngestJob.status.in_([IngestStatus.PENDING, IngestStatus.RUNNING]))
        .order_by(IngestJob.id.desc())
    )
    return session.execute(stmt).scalars().first()


def latest_job(session: Session) -> IngestJob | None:
    stmt = select(IngestJob).order_by(IngestJob.id.desc())
    return session.execute(stmt).scalars().first()


def create_job(
    session: Session,
    *,
    mode: IngestMode,
    sites: list[str],
    target: int,
    revalidate_older_than_days: int = 30,
) -> IngestJob:
    job = IngestJob(
        mode=mode,
        status=IngestStatus.PENDING,
        sites=json.dumps(sites),
        target_count=target,
        cursor=json.dumps({"revalidate_days": revalidate_older_than_days}),
    )
    session.add(job)
    session.flush()
    return job


def _existing_urls(session: Session) -> set[str]:
    return {
        url
        for url in session.execute(select(Recipe.source_url).where(Recipe.source_url.is_not(None)))
        .scalars()
        if url
    }


def _revalidation_urls(session: Session, older_than_days: int, limit: int) -> list[str]:
    cutoff = utcnow().replace(tzinfo=None) - timedelta(days=older_than_days)
    stmt = (
        select(Recipe.source_url)
        .where(
            Recipe.source_url.is_not(None),
            Recipe.is_user_edited.is_(False),
            (Recipe.last_scraped_at.is_(None)) | (Recipe.last_scraped_at < cutoff),
        )
        .limit(limit)
    )
    return [u for u in session.execute(stmt).scalars() if u]


def _run_job(job_id: int) -> None:
    session = SessionLocal()
    fetcher: PoliteFetcher | None = None
    try:
        job = session.get(IngestJob, job_id)
        if job is None:
            return
        job.status = IngestStatus.RUNNING
        session.commit()

        sites = json.loads(job.sites or "[]")
        cursor = json.loads(job.cursor or "{}")
        revalidate_days = int(cursor.get("revalidate_days", 30))
        target = job.target_count or settings.scrape_max_recipes

        fetcher = PoliteFetcher()
        resolver = IngredientResolver(session)

        if job.mode == IngestMode.REVALIDATE:
            urls = _revalidation_urls(session, revalidate_days, target)
        else:
            known = _existing_urls(session)
            urls = []
            per_site = max(target // max(len(sites), 1), 1)
            for site in sites:
                for url in discover(fetcher, site, per_site * 2):
                    if url not in known:
                        urls.append(url)
                    if len(urls) >= target:
                        break
                if len(urls) >= target:
                    break

        job.discovered_count = len(urls)
        session.commit()
        logger.info("Ingest job %s processing %d URLs", job_id, len(urls))

        for index, url in enumerate(urls):
            refreshed = session.get(IngestJob, job_id)
            if refreshed is None or refreshed.status == IngestStatus.CANCELLED:
                logger.info("Ingest job %s cancelled", job_id)
                return

            try:
                html = fetcher.get(url, use_cache=job.mode != IngestMode.REVALIDATE)
                if not html:
                    job.skipped_count += 1
                else:
                    scraped = parse_recipe_html(html, url)
                    if scraped is None:
                        job.skipped_count += 1
                    else:
                        _, outcome = upsert_recipe(session, scraped, resolver)
                        if outcome == "skipped":
                            job.skipped_count += 1
                        else:
                            job.imported_count += 1
            except Exception as exc:  # one bad page must not kill the crawl
                logger.warning("Failed to import %s: %s", url, exc)
                session.rollback()
                job = session.get(IngestJob, job_id)
                if job is None:
                    return
                job.failed_count += 1
                job.last_error = f"{url}: {exc}"[:500]

            # Persist progress so a restart resumes rather than repeats.
            job.cursor = json.dumps(
                {"revalidate_days": revalidate_days, "index": index + 1, "last_url": url}
            )
            session.commit()

        job = session.get(IngestJob, job_id)
        if job is not None and job.status != IngestStatus.CANCELLED:
            job.status = IngestStatus.COMPLETED
            job.finished_at = utcnow()
            session.commit()
        logger.info("Ingest job %s finished", job_id)
    except Exception as exc:
        logger.exception("Ingest job %s failed", job_id)
        session.rollback()
        job = session.get(IngestJob, job_id)
        if job is not None:
            job.status = IngestStatus.FAILED
            job.last_error = str(exc)[:500]
            job.finished_at = utcnow()
            session.commit()
    finally:
        if fetcher is not None:
            fetcher.close()
        session.close()


def start_job_async(job_id: int) -> None:
    """Run a job on a background thread. Only one crawl runs at a time."""
    global _active_thread
    with _lock:
        if _active_thread is not None and _active_thread.is_alive():
            logger.info("An ingest job is already running; not starting another")
            return
        thread = threading.Thread(
            target=_run_job, args=(job_id,), daemon=True, name="foodie-ingest"
        )
        _active_thread = thread
        thread.start()


def is_running() -> bool:
    return _active_thread is not None and _active_thread.is_alive()
