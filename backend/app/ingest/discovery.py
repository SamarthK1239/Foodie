"""Discover candidate recipe URLs for a site via its sitemap, falling back to link crawling."""

from __future__ import annotations

import logging
import re
from urllib.parse import urljoin, urlparse

from app.ingest.fetcher import PoliteFetcher

logger = logging.getLogger(__name__)

_LOC_RE = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.IGNORECASE)
_SITEMAP_INDEX_HINT = re.compile(r"<sitemapindex", re.IGNORECASE)
_HREF_RE = re.compile(r'href=["\']([^"\'#]+)["\']', re.IGNORECASE)

# Paths that clearly are not individual recipes.
_EXCLUDE_RE = re.compile(
    r"/(category|categories|tag|tags|author|about|contact|privacy|terms|search|login|"
    r"account|shop|subscribe|newsletter|video|gallery|collection|cuisine|course)/",
    re.IGNORECASE,
)
_RECIPE_HINT_RE = re.compile(r"/(recipe|recipes|recept)[s]?[/-]", re.IGNORECASE)


def _looks_like_recipe(url: str) -> bool:
    if _EXCLUDE_RE.search(url):
        return False
    if url.rstrip("/").count("/") < 3:
        return False
    return bool(_RECIPE_HINT_RE.search(url))


def _sitemap_candidates(site: str) -> list[str]:
    base = site.rstrip("/")
    return [
        f"{base}/sitemap.xml",
        f"{base}/sitemap_index.xml",
        f"{base}/sitemap-index.xml",
        f"{base}/robots.txt",
    ]


def _sitemaps_from_robots(text: str) -> list[str]:
    found = []
    for line in text.splitlines():
        if line.lower().startswith("sitemap:"):
            found.append(line.split(":", 1)[1].strip())
    return found


def discover_from_sitemap(
    fetcher: PoliteFetcher, site: str, limit: int, max_sitemaps: int = 12
) -> list[str]:
    """Walk a site's sitemap (including sitemap indexes) collecting recipe-looking URLs."""
    queue: list[str] = []
    for candidate in _sitemap_candidates(site):
        body = fetcher.get(candidate)
        if not body:
            continue
        if candidate.endswith("robots.txt"):
            queue.extend(_sitemaps_from_robots(body))
        else:
            queue.append(candidate)
    seen_sitemaps: set[str] = set()
    found: list[str] = []
    seen_urls: set[str] = set()
    processed = 0

    while queue and len(found) < limit and processed < max_sitemaps:
        sitemap_url = queue.pop(0)
        if sitemap_url in seen_sitemaps:
            continue
        seen_sitemaps.add(sitemap_url)
        body = fetcher.get(sitemap_url)
        if not body:
            continue
        processed += 1
        locations = _LOC_RE.findall(body)
        if _SITEMAP_INDEX_HINT.search(body):
            # Prefer child sitemaps whose name hints at recipes.
            ranked = sorted(locations, key=lambda u: 0 if "recipe" in u.lower() else 1)
            queue.extend(ranked)
            continue
        for loc in locations:
            if loc in seen_urls:
                continue
            seen_urls.add(loc)
            if _looks_like_recipe(loc):
                found.append(loc)
                if len(found) >= limit:
                    break
    return found


def discover_from_links(fetcher: PoliteFetcher, site: str, limit: int) -> list[str]:
    """Fallback: scrape the homepage for recipe-shaped links."""
    body = fetcher.get(site)
    if not body:
        return []
    host = urlparse(site).netloc
    found: list[str] = []
    seen: set[str] = set()
    for href in _HREF_RE.findall(body):
        absolute = urljoin(site, href)
        if urlparse(absolute).netloc != host or absolute in seen:
            continue
        seen.add(absolute)
        if _looks_like_recipe(absolute):
            found.append(absolute)
            if len(found) >= limit:
                break
    return found


def discover(fetcher: PoliteFetcher, site: str, limit: int) -> list[str]:
    urls = discover_from_sitemap(fetcher, site, limit)
    if len(urls) < limit:
        extra = discover_from_links(fetcher, site, limit - len(urls))
        existing = set(urls)
        urls.extend(u for u in extra if u not in existing)
    logger.info("Discovered %d candidate recipe URLs on %s", len(urls), site)
    return urls[:limit]
