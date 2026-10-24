# Foodie

The goal of this project is to help reduce food wastage, and also provide analytics on food consumption patterns, costs, and any other relevant data.

Tech specs:
- Runs on a local server, and exposes a website that will be accessed by client devices over Tailscale
    - Desktop/Mobile support are split between phases 1 and 2
- Local LLM (Qwen 3.8 27B) is hosted on Llama-server on the same machine, and SearXNG is also available if needed.
- Choose a database provider and schema as you see fit. While the database won't be included with this codebase directly (or atleast not at the moment), it would be nice to be able to just drop it in and have the app pick it up when it's restarted
    - The database should also persist between restarts, we don't want to re-run recipe indexing every time the server restarts.
- Having this run in a docker container would also be helpful to ensure that everything is self contained and auditable.

## Features in Phases:
### Phase 1:
- Allow manual entry of items + track expiry dates
- Build a database of recipes with ingredients and procedure text (allow for manual entry, but first run should ideally populate this from an external data source)
    - This is worth a conversation around how to refresh options
    - After the database has been built, the app should reference only the database to make it quick.
- Suggest dishes based on what's available, and what's about to go bad
- Automatically track items and add them to a grocery list as they run out
- Desktop website functionality only for now, mobile will come later

### Phase 2:
- Mobile resolution support for the website
- Barcode Scanning + OCR to allow for automated item pickup and entry
- Keep track of what's been made and offer a way to mark something as being "in the fridge (leftovers)" or "finished (make something new)"
- Keep track of what's dishes have been made so far in the last 4 weeks and try to suggest new things
- Refresh button to renew the options displayed
- Provide guidance on what items were used and what weren't at the end of every 2 week period, and build a grocery list for the next 2 weeks

### Phase 3:
- Build functionality that allows a link to a local model hosted on llama-server with llama.cpp + searxng
    - Allow users to provide a link to a recipe, parse the site, and extract the recipe and procedure and store it in the database


---

# Running Foodie

> [!WARNING]
> **There is no authentication.** Anyone who can reach the port can read and
> change everything. Only expose it on a Tailscale interface or a trusted LAN —
> never publish it to the internet.

## Quick start (Docker)

```bash
docker compose up -d --build
```

Then open `http://<host>:8000`. The first start creates the database and, if
`FOODIE_SEED_ON_FIRST_RUN` is enabled, begins indexing recipes in the
background — the app is usable immediately while that runs. Watch progress on
the **Admin** page.

If port 8000 is already in use (it is a popular default), set `FOODIE_HOST_PORT`
to publish on a different host port — the container still listens on 8000
internally:

```bash
FOODIE_HOST_PORT=8081 docker compose up -d --build
```

To reach it from other devices, run Tailscale on the host and use the
machine's Tailscale address. If you want to be strict, bind the published port
to the Tailscale interface only:

```yaml
ports:
  - "100.x.y.z:8000:8000"
```

## Local development

Two processes: the API and the Vite dev server (which proxies `/api` to it).

```bash
# Terminal 1 — API on :8000
cd backend
uv venv && uv pip install -e '.[dev]'
FOODIE_DATA_DIR=../data .venv/bin/uvicorn app.main:app --reload

# Terminal 2 — UI on :5173
cd frontend
npm install
npm run dev
```

Checks:

```bash
cd backend  && .venv/bin/ruff check . && .venv/bin/pytest   # lint + 88 tests
cd frontend && npm run lint && npm run build                # oxlint + typecheck
```

`npm run build` emits the SPA into `backend/app/static/`, which the API serves
directly — that is how a single container serves both.

## The database

SQLite, a single file at `$FOODIE_DATA_DIR/foodie.db` (`/data/foodie.db` in
Docker).

- **Drop-in:** stop the app, copy a `foodie.db` into the data directory, start
  it again. Any outstanding schema migrations are applied automatically on
  startup.
- **Persistent:** the `foodie-data` volume survives restarts and rebuilds, so
  recipe indexing never repeats.
- **Backup:** stop the container and copy the file, or use
  `sqlite3 foodie.db ".backup backup.db"` while it runs.
- Recipe search uses an FTS5 index kept in sync by database triggers, so it can
  never drift from the recipe table.

## Recipes

Recipes come from three places: the first-run crawl, manual entry in the UI, and
re-runs you trigger from **Admin**.

| Mode | What it does |
| --- | --- |
| `new_only` | Discovers URLs and imports only recipes not already stored. Use this to grow the library. |
| `revalidate` | Re-fetches recipes that already exist to pick up upstream corrections. |

Anything you edit by hand is flagged `is_user_edited` and **will never be
overwritten** by a later crawl.

Crawling is deliberately polite: robots.txt is respected, requests to a host are
spaced by `FOODIE_SCRAPE_DELAY_SECONDS`, responses are cached on disk, and every
recipe keeps its `source_url` for attribution. Set `FOODIE_SCRAPE_SITES` to an
empty list to disable crawling entirely and use manual entry only.

**Choosing sites.** Only add sites whose robots.txt *and* terms of service allow
automated crawling. Many large recipe publishers forbid it and block non-browser
clients outright — `allrecipes.com`, for example, returns `403` to this crawler
and its terms prohibit scraping and data mining, so it is not a default. Do not
try to work around such blocks by disguising the user agent. The default list
ships with `bbcgoodfood.com` only, which permits `/recipes/` crawling.

If a recipe line cannot be matched to a known ingredient it will not count
towards suggestions. **Admin → Unlinked ingredients** lists these; naming one
creates an alias and back-links every other recipe using the same text.

## How suggestions work

Each recipe is scored as:

```
0.6 × coverage  +  0.3 × peak_urgency  −  0.1 × missing_penalty
```

minus `0.25` if you have cooked it in the last 28 days. `coverage` is the share
of required ingredients you have; `peak_urgency` rises as your stock approaches
its expiry date. The practical effect is that food about to go off is pushed to
the top of the list.

Cooking a recipe consumes stock **oldest-expiry-first**, writes a ledger entry
for analytics, and adds anything missing or newly depleted to your grocery list.
Items with no recorded quantity (e.g. "salt to taste") are never decremented.

## Configuration

All settings are environment variables with a `FOODIE_` prefix. A `.env` file in
the working directory is also read.

| Variable | Default | Purpose |
| --- | --- | --- |
| `FOODIE_DATA_DIR` | `/data` | Directory holding the database and HTTP cache. |
| `FOODIE_DB_FILENAME` | `foodie.db` | Database filename within the data directory. |
| `FOODIE_ECHO_SQL` | `false` | Log every SQL statement. Debugging only. |
| `FOODIE_SEED_ON_FIRST_RUN` | `true` | Crawl recipes on first start, only when no recipes exist yet. |
| `FOODIE_SCRAPE_SITES` | bbcgoodfood | JSON list of sites to crawl. Empty disables crawling. |
| `FOODIE_SCRAPE_MAX_RECIPES` | `500` | Target recipe count for a crawl. |
| `FOODIE_SCRAPE_DELAY_SECONDS` | `1.5` | Minimum delay between requests to one host. |
| `FOODIE_SCRAPE_TIMEOUT_SECONDS` | `20` | Per-request timeout. |
| `FOODIE_SCRAPE_USER_AGENT` | `FoodieBot/0.1 …` | User agent sent when crawling. |
| `FOODIE_SCRAPE_RESPECT_ROBOTS` | `true` | Obey robots.txt. Leave this on. |
| `FOODIE_EXPIRY_CRITICAL_DAYS` | `2` | Days left before an item is "Use now". |
| `FOODIE_EXPIRY_SOON_DAYS` | `5` | Days left before an item is "Use soon". |
| `FOODIE_LLM_BASE_URL` | `http://localhost:8080/v1` | Phase 3 placeholder — llama-server endpoint. |
| `FOODIE_LLM_MODEL` | `qwen3` | Phase 3 placeholder — model name. |
| `FOODIE_SEARXNG_URL` | `http://localhost:8888` | Phase 3 placeholder — SearXNG endpoint. |

## Project layout

```
backend/
  app/
    api/        FastAPI routers (inventory, recipes, suggestions, grocery, analytics, admin)
    services/   Business logic: units, inventory ledger, suggestion scoring, cooking, grocery
    ingest/     Polite fetcher, sitemap discovery, recipe import, resumable job runner
    models/     SQLAlchemy entities and enums
    static/     Built SPA (generated — not checked in)
  alembic/      Schema migrations, applied automatically on startup
  tests/        Pytest suite
frontend/
  src/api/      Typed client and TanStack Query hooks
  src/pages/    Dashboard, Suggestions, Recipes, Grocery, Analytics, Admin
  src/components/
Dockerfile         Multi-stage: Node builds the SPA, Python serves everything
docker-compose.yml
```

## API

Interactive docs are served at `/docs` while the app is running.

| Area | Endpoints |
| --- | --- |
| Inventory | `GET/POST /api/inventory/items`, `PATCH/DELETE /api/inventory/items/{id}`, `/adjust`, `/discard`, `/finish`, `/api/inventory/expiring`, `/api/inventory/summary` |
| Recipes | `GET/POST /api/recipes`, `GET/PATCH/DELETE /api/recipes/{id}`, `POST /api/recipes/{id}/cook` |
| Suggestions | `GET /api/suggestions`, `GET/PATCH /api/cook-events` |
| Grocery | `GET/POST /api/grocery`, `PATCH/DELETE /api/grocery/{id}`, `POST /api/grocery/clear-purchased` |
| Analytics | `/api/analytics/summary`, `/spend-by-category`, `/spend-over-time`, `/most-wasted`, `/most-used`, `/recent-cooks` |
| Admin | `/api/admin/stats`, `/api/admin/ingest/{start,cancel,status}`, `/api/admin/unmatched-ingredients[/resolve]` |

## Status

Phase 1 is complete: manual entry with expiry tracking, a recipe database with
automatic ingestion, expiry-aware suggestions, cooking with automatic stock
decrement, an auto-maintained grocery list, and consumption/waste analytics.

Phases 2 and 3 are not built yet, but the groundwork is in place — the
append-only inventory ledger supports historical reporting, `CookEvent` already
carries a leftover state, and the Phase 3 LLM and SearXNG settings are reserved
in configuration.
