# Budapest Apartments — Backend

FastAPI + SQLAlchemy (SQLite) backend for tracking Budapest apartment listings
and per-district price benchmarks.

## Setup

```bash
cd backend
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Run

```bash
uvicorn app.main:app --reload
```

Tables are created automatically on startup (SQLite file: `budapest_apartments.db`,
created next to this README). Interactive docs: http://127.0.0.1:8000/docs

By default the API only accepts cross-origin requests from `http://localhost:3000`
(where `../frontend` runs in dev) — set `FRONTEND_ORIGINS` (comma-separated) to
change that, e.g. for a deployed frontend's real origin.

## Deploying (Render)

See `../../render.yaml` for the Blueprint. The one step that's easy to miss
if you set the service up manually instead: the build command must run
`playwright install --with-deps chromium` *after* `pip install`, not just
`pip install -r requirements.txt` alone — pip only installs the `playwright`
Python package, not the actual browser binary it drives. Without this step,
every scan (`POST /api/scraper/trigger`) fails instantly with
`BrowserType.launch: Executable doesn't exist at .../ms-playwright/...`.

## Frontend

`../frontend` is a Next.js + Tailwind + shadcn/ui investment dashboard that
reads from this API's `/dashboard/stats` and `/deals` endpoints — see
`../frontend/README.md` to run it.

## Scraper

`scraper/` is a modular Playwright scraper supporting three portals — `jofogas`,
`otthonterkep`, `ingatlanbazar` — each a `BaseScraper` subclass registered in
`scraper/registry.py`; everything else (stealth, robots.txt checks, retry/backoff,
rate limiting, DB upsert, analyzer hookup) is shared. **Read `scraper/README.md`
before running it** — it covers per-portal robots.txt findings and exactly
what's been verified against the live site vs. what still needs checking.

**`jofogas` is fully verified end-to-end against the live site** — it extracts
complete listing data (price, size, rooms, lat/lng, images, condition) straight
from the search-results page's own embedded JSON (`__NEXT_DATA__`), so it never
even needs to visit individual listing pages (`supports_bulk_extraction = True`).

**`otthonterkep` and `ingatlanbazar` are unverified** — built with a JSON-LD-first
extraction attempt (falls back to best-effort CSS selectors), but the selectors
have never been checked against the live, JS-rendered markup. Verify with
`playwright codegen <url>` before relying on them for a real run.

Resilience: 3-attempt exponential backoff (`scraper/retry.py`) around every
navigation, 45s page timeouts, realistic desktop-Chrome headers. Listings with
no real photos get `images: []` (never fabricated); `source_url` always has
UTM/tracking params stripped; districts are always normalized to roman
numerals. Geocoding (`scraper/geocode.py`, Nominatim/OpenStreetMap) fills in
`latitude`/`longitude` for portals that don't already provide it, falling back
to the property's district centroid if geocoding fails.

```bash
playwright install chromium
python -m scraper.run --portal jofogas --max-listings 20
```

## Schema

**properties**
| column | type | notes |
|---|---|---|
| id | int, PK | autoincrement |
| title | string | required |
| district | string | e.g. "V", "XIII", or "13" |
| address | string | |
| size_sqm | float | interior area |
| rooms | float | allows values like 2.5 for "2+1 half room" |
| balcony_sqm | float | nullable — only set when the source portal reports a real size, never guessed |
| price_huf | float | |
| price_eur | float | |
| price_per_sqm | float | auto-computed from price_huf / size_sqm if not supplied |
| url | string | unique, source listing URL |
| condition | string | e.g. "new" / "renovated" / "raw" |
| images | JSON | list of image URLs |
| portal | string | e.g. "jofogas", "ingatlanbazar" |
| latitude / longitude | float | geocoded (or district-centroid fallback) for the map view |
| is_favorite | bool | user bookmark |
| pipeline_status | string | "new" / "reviewing" / "tour_scheduled" / "offer_sent" / "archived" |
| created_at | datetime | set automatically |

**district_benchmarks**
| column | type | notes |
|---|---|---|
| district_number | int, PK | 1–23 (Budapest districts I–XXIII) |
| avg_price_sqm_raw | float | avg HUF/sqm for unrenovated listings |
| avg_price_sqm_renovated | float | avg HUF/sqm for renovated listings |
| avg_rent_huf_sqm | float | avg monthly HUF/sqm rent — powers rental yield |
| centroid_lat / centroid_lng | float | approximate district center — map/geocoding fallback |
| updated_at | datetime | set automatically on insert/update |

New columns are added to the existing SQLite file automatically at startup via
a lightweight idempotent migration (`app/database.py::run_startup_migrations`)
— no Alembic, no manual step needed.

## Endpoints

- `POST /properties`, `GET /properties` (filters: `district`, `portal`, `favorites_only`, `min_price_huf`, `max_price_huf`, `min_size_sqm`, `max_size_sqm`, `skip`, `limit`), `GET /properties/{id}`, `PATCH /properties/{id}` (also how favorite/pipeline-status get updated), `DELETE /properties/{id}`
- `GET /properties/{id}/analysis?...&custom_renovation_cost_eur_sqm=` — flip/renovation financial analysis, optionally with a 4th custom-cost tier (see below)
- `GET /properties/{id}/spec-sheet` — downloadable Contractor Spec Sheet PDF (see below)
- `GET /properties/{id}/investment-memo` — downloadable one-page Investment Memo PDF (see below)
- `GET /fx-rate` — live EUR→HUF rate (frankfurter.app/ECB, cached ~1h)
- `GET /dashboard/stats` — KPIs for the frontend: total listings, average €/sqm, top undervalued deals (see "Dashboard aggregation" below)
- `GET /deals` — properties enriched with their full renovation analysis and Deal Score, filterable by `district`, `portal`, `favorites_only`, `min_roi`, `min_size_sqm`, `max_size_sqm`, `min/max_price_huf` — what the frontend's table/card/split-map views and detail modal read from
- `POST /district-benchmarks`, `GET /district-benchmarks`, `GET /district-benchmarks/{district_number}`, `PATCH /district-benchmarks/{district_number}` (creates or updates), `DELETE /district-benchmarks/{district_number}`

## Dashboard aggregation (`app/dashboard.py`)

`GET /dashboard/stats` computes total listing count, the average price/sqm across
all properties (in HUF and EUR), and up to `top_n` "top undervalued" deals: listings
scraped **today** (UTC), ranked by how far their price/sqm sits below their
district's benchmark — `avg_price_sqm_renovated` if the listing's `condition`
text suggests it's already renovated, `avg_price_sqm_raw` otherwise. If nothing
was scraped today, it falls back to ranking every listing instead of returning
an empty list — `is_today_only: false` in the response says when that's happened,
so the frontend can label it rather than imply today's listings are the ones shown.

`GET /deals` reuses `app/analyzer.py` per property to attach the full
Light/Medium/Full breakdown plus the best-ROI tier to every listing in one
response, so the frontend's detail modal doesn't need a second round-trip.
`min_roi` filters on that best tier; a listing with no benchmark yet is still
returned (with `analysis: null`) unless `min_roi` is set, since there'd be
nothing to compare it against.

## Contractor Spec Sheet (`app/spec_sheet.py`)

`GET /properties/{id}/spec-sheet?eur_huf_rate=` returns a downloadable PDF (`Content-Disposition:
attachment`) built with reportlab: the listing's floor space, room count, condition and price;
its current photos (fetched and embedded — a photo URL that fails to download is skipped rather
than breaking the sheet); an "investment context" line from the district benchmark/analyzer when
available; and an 11-category on-site quoting checklist (structural, electrical, plumbing, heating,
windows/doors, flooring, kitchen, bathroom(s), walls/ceilings, building access/logistics, utilities
& permits) with a blank column per item for the contractor's notes and cost estimate. The frontend's
"Download Contractor Spec Sheet" button (in the detail modal, plus a quick icon button on each
table row / card) just links straight to this endpoint — the browser handles the download.

Checkboxes are plain ASCII `[ ]`, not a Unicode box character — reportlab's base font can't render
those glyphs (see the pdf skill's guidance: they come out as solid black boxes).

```bash
python3 tests/test_spec_sheet.py   # generates real PDFs with reportlab and inspects them via pypdf
```

This one could actually be verified end-to-end in the sandbox this was built in, unlike most of the
rest of this project — `reportlab`, `Pillow`, and `pypdf` happened to already be installed there.
The test suite spins up a local HTTP server to serve real JPEGs (no external network needed) and
confirms: successful downloads embed correctly, a 404 or unreachable host is skipped without
crashing the sheet, and the generated PDF's extracted text and embedded-image count match what was
asked for. I also rendered a couple of sample sheets to images and looked at them directly.

## Financial analysis (`app/analyzer.py`)

`GET /properties/{id}/analysis?district_number=&eur_huf_rate=` returns, for each of three renovation
tiers (Light €250/sqm, Medium €450/sqm, Full €700/sqm): renovation cost, total investment, exit
price, net profit, and ROI %. `district_number` defaults to parsing the property's own `district`
field (e.g. "VII" -> 7); `eur_huf_rate` defaults to a placeholder constant in `analyzer.py` — pass
the day's real rate as a query param for accuracy.

The module has no dependency on FastAPI/SQLAlchemy for its core math, so it can be used and tested
standalone:

```bash
python3 -m app.analyzer          # runs a demo calculation and prints JSON
python3 tests/test_analyzer.py   # runs the unit tests (plain assertions, no pytest required)
```

Calculation logic, spelled out:

- **Usable area** = `size_sqm + balcony_sqm × 50%` (falls back to plain `size_sqm` if no balcony size is on file) — used as the basis for renovation cost and exit price, not raw interior size alone
- **Renovation cost** = `usable_area_sqm × tier_EUR_per_sqm × eur_huf_rate` (tiers: Light 250, Medium 450, Full 700 EUR/sqm, or a custom €/sqm passed via `custom_renovation_cost_eur_sqm`)
- **Property transfer tax (illeték)** = `asking_price_huf × 4%`; **legal/notary fee** = `asking_price_huf × 1%`
- **Safety buffer** = `5% × (asking_price_huf + transfer_tax + legal_fee + renovation_cost)`
- **Exit price** = `usable_area_sqm × DistrictBenchmarks.avg_price_sqm_renovated` for the property's district — same benchmark used across all tiers, since only one renovated-price benchmark exists per district (see caveat below)
- **Total investment** = `asking_price_huf + transfer_tax + legal_fee + renovation_cost + safety_buffer`
- **Net profit** = `exit_price − total_investment`; **ROI %** = `net_profit / total_investment × 100`
- **Rental yield** (only when the district has an `avg_rent_huf_sqm` benchmark): gross annual rent = `avg_rent_huf_sqm × usable_area_sqm × 12`; gross yield % = `gross_rent / total_investment × 100`; net yield assumes 20% of gross rent goes to management/maintenance/vacancy

**Deal Score** (`app/deal_score.py`, exposed as `deal_score`/`deal_score_band` on every `/deals` item):
a 0–100 composite of discount-vs-benchmark (45%), best-tier ROI (40%), and layout efficiency —
usable sqm per room (15%) — each clamped to a realistic range and rescaled before weighting, so one
outlier property can't compress everyone else's score toward the middle. `deal_score_band` is
`"high"` (≥70) / `"fair"` (≥40) / `"low"`, matching the frontend's map-pin and badge colors.

Assumptions worth double-checking before using this for real decisions (also documented at the top
of `analyzer.py`):
- The EUR/HUF rate defaults to a placeholder (400) if not supplied — the frontend pre-fills a live
  rate from `GET /fx-rate`, but pass `eur_huf_rate` explicitly for accuracy.
- Because there's only one `avg_price_sqm_renovated` per district, the exit price is the same across
  every tier — a real Light renovation likely wouldn't reach full "renovated" market value. Flag it
  if you'd rather see tier-differentiated exit pricing.
- No resale agent commission or capital gains tax is subtracted from net profit — both are easy to
  add as extra rate constants.
- The 20% rental opex assumption (`RENTAL_OPEX_RATE`) is a flat placeholder, not a verified
  Budapest management-cost figure.

## Investment Memo (`app/investment_memo.py`)

`GET /properties/{id}/investment-memo?eur_huf_rate=&custom_renovation_cost_eur_sqm=` returns a
one-page PDF: acquisition/exit cost breakdown, all renovation tiers (incl. the custom one if
requested) with ROI and rental yield, and the Deal Score — reuses `app/spec_sheet.py`'s photo-loading
helpers rather than duplicating them. Distinct from the Contractor Spec Sheet, which is aimed at a
contractor doing an on-site quote, not an investor evaluating the deal.

## Notes

- `DATABASE_URL` env var can override the default SQLite file (e.g. to point at Postgres later) without code changes.
- The prompt describing `district_benchmarks` was cut off after `avg_price_sqm_renovated`; that column and `avg_price_sqm_raw` are implemented as specified. Let me know if you also want `avg_price_sqm_new`, `sample_size`, or similar and I'll add them.
