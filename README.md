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
cd backend  && .venv/bin/ruff check . && .venv/bin/pytest   # lint + 128 tests
cd frontend && npm run lint && npm run build                # oxlint + typecheck
cd frontend && npm run test:e2e                             # 18 mobile layout tests
```

`npm run build` emits the SPA into `backend/app/static/`, which the API serves
directly — that is how a single container serves both.

The end-to-end suite boots its own API against a throwaway data directory and
drives a Pixel 7 viewport, asserting that no page scrolls sideways and that every
control meets the 44px touch minimum. Point it at a running instance with
`BASE_URL=http://host:8000 npm run test:e2e`.

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

**Method formatting.** Instructions are stored as plain text but rendered as
numbered steps. Lines are the step boundary; a short line ending in a colon
("For the custard:") becomes a heading and does not consume a step number.
Sources that already number their steps have that numbering stripped so nothing
renders as "1. 1. Heat the oven". Crucially, an unbroken blob is **never** split
on sentence punctuation — "Heat oven to 220C/200C fan/gas 7." would be torn in
half — so a blob is only re-split when it contains markers that genuinely run
1, 2, 3.

**Favourites.** Star a recipe from the card grid or its detail page to keep it
to hand; the list can then be sorted favourites-first or filtered to favourites
only. Starring is a dedicated endpoint rather than a `PATCH`, because an edit
sets `is_user_edited` and would quietly opt the recipe out of future re-imports.

## Planning a week

**Add to this week** on a recipe page puts it on the current week's plan
(weeks run Monday to Sunday) and immediately updates your grocery list.

Requirements are summed **across the whole week**, not maxed: three dishes each
needing 200 g of pasta need 600 g, and one bag will not do. Current stock is
subtracted, so the list asks for the shortfall rather than the full amount. If
any line for an ingredient has no quantity, or a unit that cannot be converted
("2 cloves" against "30 g"), the whole requirement falls back to a presence
check — a partial sum would read as the week's total while silently omitting
lines.

The derived list is recomputed from the plan whenever it changes, and only ever
touches rows it added itself (`meal_plan`). It will not raise a quantity you set
by hand, and an ingredient already pending from another source does not get a
duplicate row. Removing a recipe from the plan withdraws exactly what it added.

Only the current week feeds the grocery list — you shop for the week you are in.
Planning further ahead is allowed and shows up when you view that week.

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

Straight after cooking you are asked whether there are leftovers. It is asked
there rather than later because that is the only moment you actually know; the
answer can still be corrected from **Analytics**.

## On a phone

The UI is responsive: a hamburger menu carries every destination and a bottom
tab bar keeps Kitchen, Cook, Scan and Grocery within one-handed reach. Scanning
takes the fourth tab rather than Analytics, because scanning is what you do
standing up with shopping bags and charts are read sitting down.

## Scanning

**Barcodes.** `Scan` decodes a barcode from a photo, a live camera, or a typed
number, looks the product up against a local cache and then OpenFoodFacts, and
prefills the add-item form.

- An unknown barcode is normal, not an error — most products are not in any
  database, so manual entry is the expected path and what you type is bound to
  that barcode for next time.
- Products are matched against your existing ingredients and never added to
  them. "Tesco British Semi Skimmed Milk" is a package of milk; storing it as a
  new ingredient would silently stop recipes matching the stock you just added.
- Set `FOODIE_BARCODE_LOOKUP_ENABLED=false` to keep lookups entirely local.
- Photos are downscaled before decoding and the search is time-budgeted. A
  modern phone camera produces 12–48 megapixel stills, and decoding one at full
  resolution both takes tens of seconds and exceeds iOS Safari's canvas limit,
  which returns a blank image. Scanning a barcode needs far less detail than
  that.

**Expiry dates.** Photograph the printed date and Foodie reads it. A single
confident reading is applied straight away; where the print is genuinely
ambiguous (`03/04/25` is April 3rd or March 4th depending on where you shop)
every plausible reading is offered rather than one being guessed silently.
"Best before" and "use by" wording wins over a packed-on date printed beside it.

> [!NOTE]
> The **live camera needs HTTPS.** Browsers block camera access on plain HTTP
> for everything except localhost, so over Tailscale the button only appears if
> you serve Foodie over TLS (`tailscale serve`). Photo capture works everywhere
> and is the default path.

Expiry reading needs Tesseract, which the Docker image installs. Running the
backend outside Docker without it simply hides the feature rather than failing.

## The two-week review

**Review** answers what you actually ate, what you wasted, and what to buy next
over a window you choose.

| Section | What it shows |
| --- | --- |
| Buy again | Ingredients you used up and are now out of. Anything you *binned* this period is deliberately excluded — re-buying what you just threw away is how waste repeats. |
| Sitting untouched | Stock that was already in the kitchen when the period began and has not been touched since. This is what is quietly heading for the bin. |
| Used | What was genuinely cooked with, from the ledger. |
| Wasted | What was binned, and what it cost. |

Selected suggestions are pushed onto the grocery list. Running out already adds
items automatically, so anything already listed is marked as such instead of
being claimed as a new find, and applying merges into the existing entry rather
than duplicating it.

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
| `FOODIE_OPENFOODFACTS_URL` | `https://world.openfoodfacts.org` | Barcode lookup service. |
| `FOODIE_BARCODE_LOOKUP_ENABLED` | `true` | Allow outbound barcode lookups. Off means cache and manual entry only. |
| `FOODIE_BARCODE_TIMEOUT_SECONDS` | `8` | Per-lookup timeout. |
| `FOODIE_LLM_BASE_URL` | `http://localhost:8080/v1` | Phase 3 placeholder — llama-server endpoint. |
| `FOODIE_LLM_MODEL` | `qwen3` | Phase 3 placeholder — model name. |
| `FOODIE_SEARXNG_URL` | `http://localhost:8888` | Phase 3 placeholder — SearXNG endpoint. |

## Project layout

```
backend/
  app/
    api/        FastAPI routers (inventory, recipes, suggestions, grocery, meal plan, analytics, scan, admin)
    services/   Business logic: units, inventory ledger, suggestion scoring, cooking, grocery, meal plan, barcode, OCR
    ingest/     Polite fetcher, sitemap discovery, recipe import, resumable job runner
    models/     SQLAlchemy entities and enums
    static/     Built SPA (generated — not checked in)
  alembic/      Schema migrations, applied automatically on startup
  tests/        Pytest suite
frontend/
  src/api/      Typed client and TanStack Query hooks
  src/pages/    Dashboard, Suggestions, Recipes, Grocery, Review, Scan, Analytics, Admin
  src/components/
  tests/        Playwright mobile-layout suite
Dockerfile         Multi-stage: Node builds the SPA, Python serves everything
docker-compose.yml
```

## API

Interactive docs are served at `/docs` while the app is running.

| Area | Endpoints |
| --- | --- |
| Inventory | `GET/POST /api/inventory/items`, `PATCH/DELETE /api/inventory/items/{id}`, `/adjust`, `/discard`, `/finish`, `/api/inventory/expiring`, `/api/inventory/summary` |
| Recipes | `GET/POST /api/recipes`, `GET/PATCH/DELETE /api/recipes/{id}`, `POST /api/recipes/{id}/cook`, `POST /api/recipes/{id}/favorite` |
| Suggestions | `GET /api/suggestions`, `GET/PATCH /api/cook-events` |
| Meal plan | `GET/POST /api/meal-plan`, `DELETE /api/meal-plan/{id}` |
| Grocery | `GET/POST /api/grocery`, `PATCH/DELETE /api/grocery/{id}`, `POST /api/grocery/clear-purchased` |
| Analytics | `/api/analytics/summary`, `/spend-by-category`, `/spend-over-time`, `/most-wasted`, `/most-used`, `/recent-cooks`, `/period-review[/apply]` |
| Scan | `GET /api/scan/barcode/{code}`, `POST /api/scan/to-inventory`, `POST /api/scan/expiry` |
| Admin | `/api/admin/stats`, `/api/admin/ingest/{start,cancel,status}`, `/api/admin/unmatched-ingredients[/resolve]` |

## Status

Phases 1 and 2 are complete.

**Phase 1** — manual entry with expiry tracking, a recipe database with
automatic ingestion, expiry-aware suggestions, cooking with automatic stock
decrement, an auto-maintained grocery list, and consumption/waste analytics.

**Phase 2** — a phone-usable UI covered by a mobile layout test suite, barcode
scanning with a local product cache, expiry dates read from a photo, a leftovers
prompt at cook time, and the two-week review that builds the next shop. The
"suggest new things" and refresh requirements were already met by Phase 1: the
scoring penalises anything cooked in the last 28 days, and the suggestions list
has a refresh control that redraws the options.

**Phase 3** is not built yet, but the LLM and SearXNG settings are reserved in
configuration.
