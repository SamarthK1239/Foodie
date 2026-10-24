"""Polite HTTP fetching: robots.txt aware, rate limited, and cached on disk."""

from __future__ import annotations

import hashlib
import logging
import time
import urllib.robotparser
from pathlib import Path
from urllib.parse import urlparse

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class PoliteFetcher:
    """Single-threaded fetcher that never hits the same host faster than the configured delay."""

    def __init__(
        self,
        *,
        delay: float | None = None,
        timeout: float | None = None,
        user_agent: str | None = None,
        cache_dir: Path | None = None,
        respect_robots: bool | None = None,
    ) -> None:
        self.delay = settings.scrape_delay_seconds if delay is None else delay
        self.timeout = settings.scrape_timeout_seconds if timeout is None else timeout
        self.user_agent = user_agent or settings.scrape_user_agent
        self.respect_robots = (
            settings.scrape_respect_robots if respect_robots is None else respect_robots
        )
        self.cache_dir = cache_dir or settings.http_cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._last_request: dict[str, float] = {}
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self._client = httpx.Client(
            timeout=self.timeout,
            headers={"User-Agent": self.user_agent},
            follow_redirects=True,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> PoliteFetcher:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _cache_path(self, url: str) -> Path:
        digest = hashlib.sha256(url.encode()).hexdigest()
        return self.cache_dir / f"{digest}.html"

    def _throttle(self, host: str) -> None:
        last = self._last_request.get(host)
        if last is not None:
            elapsed = time.monotonic() - last
            if elapsed < self.delay:
                time.sleep(self.delay - elapsed)
        self._last_request[host] = time.monotonic()

    def allowed(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in self._robots:
            parser = urllib.robotparser.RobotFileParser()
            try:
                self._throttle(parsed.netloc)
                response = self._client.get(f"{origin}/robots.txt")
                if response.status_code == 200:
                    parser.parse(response.text.splitlines())
                else:
                    parser = None  # No usable robots.txt: treat as unrestricted.
            except httpx.HTTPError:
                parser = None
            self._robots[origin] = parser
        parser = self._robots[origin]
        if parser is None:
            return True
        return parser.can_fetch(self.user_agent, url)

    def get(self, url: str, *, use_cache: bool = True) -> str | None:
        cache_file = self._cache_path(url)
        if use_cache and cache_file.exists():
            return cache_file.read_text(encoding="utf-8", errors="replace")

        if not self.allowed(url):
            logger.info("robots.txt disallows %s, skipping", url)
            return None

        parsed = urlparse(url)
        self._throttle(parsed.netloc)
        try:
            response = self._client.get(url)
        except httpx.HTTPError as exc:
            logger.warning("Fetch failed for %s: %s", url, exc)
            return None
        if response.status_code != 200:
            logger.debug("Fetch returned %s for %s", response.status_code, url)
            return None

        text = response.text
        try:
            cache_file.write_text(text, encoding="utf-8")
        except OSError:
            pass
        return text
