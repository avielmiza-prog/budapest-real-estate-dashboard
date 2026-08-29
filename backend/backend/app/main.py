"""
FastAPI entrypoint for the Budapest Apartments backend.

Run locally with:
    uvicorn app.main:app --reload

Interactive API docs will then be at http://127.0.0.1:8000/docs
"""
import asyncio
import logging
import os
import re
from typing import List, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app import access_control, analyzer, crud, dashboard, fx_rate, investment_memo, models, schemas, scraper_jobs, seed, spec_sheet
from app.database import SessionLocal, get_db, init_db
from app.services import stats_service, valuation_agent

# Twice-daily automated scan cycle (10:00 + 18:00 Europe/Budapest) — see
# on_startup() below and POST /api/scan/trigger for a manual/webhook-driven
# run of the same job. Module-level (not env-frozen) so tests can flip it
# off after import, the same way they force access_control.ACCESS_PASSCODE
# off — a pytest run should never accidentally arm a live background
# scraper against real portals.
SCHEDULER_ENABLED = os.getenv("DISABLE_SCHEDULER", "").lower() not in ("1", "true", "yes")
SCHEDULED_SCAN_MAX_LISTINGS = 150
scheduler = AsyncIOScheduler(timezone="Europe/Budapest")


async def _run_scheduled_scan() -> None:
    """
    APScheduler job body: runs the exact same claim-and-run flow as the
    manual trigger endpoints (scraper_jobs.try_start/run_job), so a
    scheduled run and a manual "Scan Market" click can never overlap — one
    is-running flag guards both. Runs the (synchronous, Playwright-capable)
    scraper in a worker thread via asyncio.to_thread so it never blocks the
    event loop the rest of the API is served from.
    """
    status, claimed = scraper_jobs.try_start(
        max_listings=SCHEDULED_SCAN_MAX_LISTINGS, eur_huf_rate=analyzer.DEFAULT_EUR_HUF_RATE
    )
    if not claimed:
        logger.info("[scheduler] skipping scheduled scan cycle — one is already running: %s", status)
        return
    logger.info("[scheduler] starting scheduled scan cycle")
    await asyncio.to_thread(scraper_jobs.run_job, SCHEDULED_SCAN_MAX_LISTINGS, analyzer.DEFAULT_EUR_HUF_RATE)

def _parse_districts(district: Optional[str]) -> Optional[List[str]]:
    """
    'district' query params accept a single value or a comma-separated list
    for multi-select (e.g. 'V,VI,VII'). Returns None when nothing was passed.
    """
    if not district:
        return None
    parsed = [d.strip() for d in district.split(",") if d.strip()]
    return parsed or None


def _parse_portals(portal: Optional[str]) -> Optional[List[str]]:
    """Same comma-separated-list convention as _parse_districts, for the `portal` filter."""
    if not portal:
        return None
    parsed = [p.strip() for p in portal.split(",") if p.strip()]
    return parsed or None


app = FastAPI(
    title="Budapest Apartments API",
    description="Backend for tracking Budapest apartment listings and per-district price benchmarks.",
    version="0.1.0",
)

# Comma-separated list, e.g. "http://localhost:3000,https://my-dashboard.example.com",
# or "*" for any origin. Defaults to "*": this dashboard's actual data
# access control is the optional ACCESS_PASSCODE gate (app/access_control.py),
# not CORS — CORS only restricts browser JS, not curl/server-to-server
# calls, so restricting it here wouldn't hide anything a passcode-less
# deployment doesn't already expose, and "*" means a Vercel redeploy,
# preview URL, or custom domain never needs an env var update to keep
# working. Set FRONTEND_ORIGINS to a real comma-separated list yourself if
# you want it locked down instead.
_DEFAULT_FRONTEND_ORIGINS = "*"
_frontend_origins = os.getenv("FRONTEND_ORIGINS", _DEFAULT_FRONTEND_ORIGINS).split(",")
# Regex for origins that vary per-deploy — Vercel preview URLs get a unique
# subdomain per branch/PR. Irrelevant while FRONTEND_ORIGINS="*" (above)
# already matches everything; only takes effect if you narrow that down.
_frontend_origin_regex = os.getenv("FRONTEND_ORIGIN_REGEX", r"https://.*\.vercel\.app") or None
_frontend_origins_set = {o.strip() for o in _frontend_origins if o.strip()}
_allow_all_origins = "*" in _frontend_origins_set
_frontend_origin_regex_compiled = re.compile(_frontend_origin_regex) if _frontend_origin_regex else None
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _frontend_origins if o.strip()],
    allow_origin_regex=_frontend_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Added after CORS so CORS stays the outer layer — a 401 from the passcode
# gate still carries CORS headers, instead of the browser reporting it as an
# opaque CORS failure. See app/access_control.py.
app.add_middleware(access_control.PasscodeGateMiddleware)


@app.on_event("startup")
async def on_startup() -> None:
    init_db()
    # District benchmarks only — never listings. See app/seed.py's docstring
    # for why: this is what makes deal_score/analysis come back non-null on
    # a freshly-provisioned database (e.g. a new Render deploy) instead of
    # every deal showing null ROI until someone manually adds all 23.
    db = SessionLocal()
    try:
        seed.seed_district_benchmarks_if_empty(db)
        # Best-effort: refresh benchmarks from whatever live listings already
        # exist (e.g. a redeploy against an existing DB) so they aren't stuck
        # on the static seed snapshot until the next scheduled scan touches
        # them. See app/services/stats_service.py.
        try:
            stats_service.update_district_benchmarks(db)
        except Exception:  # noqa: BLE001 - must never block startup
            logger.exception("update_district_benchmarks failed during startup")
    finally:
        db.close()

    if SCHEDULER_ENABLED and not scheduler.running:
        scheduler.add_job(
            _run_scheduled_scan,
            CronTrigger(hour="10,18", minute=0, timezone="Europe/Budapest"),
            id="twice_daily_scan",
            replace_existing=True,
            misfire_grace_time=3600,  # still run a scan that missed its exact slot by up to an hour (e.g. a redeploy)
        )
        scheduler.start()
        logger.info("[scheduler] twice-daily scan cycle armed for 10:00 and 18:00 Europe/Budapest")


@app.on_event("shutdown")
async def on_shutdown() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)


def _cors_headers_for_origin(origin: Optional[str]) -> dict:
    """
    Mirrors CORSMiddleware's own origin check, for the one response that
    bypasses it: a bare-`Exception` handler (like the one below) is run by
    Starlette's ServerErrorMiddleware, which wraps *outside* CORSMiddleware
    in the stack — so without this, an unhandled exception's response would
    reach the browser with no CORS headers at all and get silently blocked
    cross-origin (Vercel -> Render), surfacing as an opaque network failure
    instead of the actual error this handler is trying to report.
    """
    if not origin:
        return {}
    allowed = (
        _allow_all_origins
        or origin in _frontend_origins_set
        or (_frontend_origin_regex_compiled is not None and _frontend_origin_regex_compiled.fullmatch(origin) is not None)
    )
    if not allowed:
        return {}
    # Always echo the specific origin, never literal "*" — a credentialed
    # response (Allow-Credentials: true) with a literal "*" origin is
    # rejected by browsers per the Fetch spec, same reason CORSMiddleware
    # itself echoes the origin instead of "*" once allow_credentials=True.
    return {"Access-Control-Allow-Origin": origin, "Access-Control-Allow-Credentials": "true", "Vary": "Origin"}


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Last-resort catch-all for anything that isn't already an HTTPException
    (FastAPI keeps its own more-specific handler for those, e.g. 404s stay
    404s — this only fires for genuinely unhandled bugs). Render's dashboard
    only shows stdout/stderr, not a debugger, so logging the full traceback
    here is the only way to actually see what broke in production.
    """
    logger.exception("Unhandled error on %s %s", request.method, request.url)
    headers = _cors_headers_for_origin(request.headers.get("origin"))
    return JSONResponse(status_code=500, content={"detail": f"{type(exc).__name__}: {exc}"}, headers=headers)


@app.get("/", tags=["meta"])
def root():
    return {"status": "ok", "service": "budapest-apartments-api"}


# ---------------------------------------------------------------------------
# Access passcode (see app/access_control.py)
# ---------------------------------------------------------------------------

@app.get("/api/auth/status", tags=["auth"])
def auth_status():
    """Whether ACCESS_PASSCODE is configured — the frontend skips the passcode modal entirely when it isn't."""
    return {"passcode_required": access_control.is_enabled()}


@app.post("/api/auth/verify", tags=["auth"])
def auth_verify(payload: schemas.PasscodeVerify):
    if not access_control.is_enabled():
        return {"valid": True}
    if not access_control.check(payload.passcode):
        raise HTTPException(status_code=401, detail="Incorrect passcode.")
    return {"valid": True}


# ---------------------------------------------------------------------------
# Scraper ("Scan Market" button)
# ---------------------------------------------------------------------------

@app.post("/api/scraper/trigger", tags=["scraper"])
def trigger_scraper(
    background_tasks: BackgroundTasks,
    max_listings: int = Query(default=150, ge=1, le=1000),
    eur_huf_rate: float = Query(default=analyzer.DEFAULT_EUR_HUF_RATE, gt=0),
):
    """
    Kicks off the autonomous ingestion agent (every eligible portal, human-
    like behavior, per-portal fault isolation — see scraper/agent) in a
    FastAPI background task and returns immediately. A run already in
    flight is left alone rather than duplicated — poll GET
    /api/scraper/status for progress/completion.
    """
    status, claimed = scraper_jobs.try_start(max_listings=max_listings, eur_huf_rate=eur_huf_rate)
    if claimed:
        background_tasks.add_task(scraper_jobs.run_job, max_listings, eur_huf_rate)
        message = "Scan started successfully"
    else:
        message = "A scan is already running"
    return {"status": "running", "message": message, **status}


@app.get("/api/scraper/status", tags=["scraper"])
def scraper_status():
    return scraper_jobs.get_status()


@app.post("/api/scan/trigger", tags=["scraper"])
def trigger_scan(
    background_tasks: BackgroundTasks,
    max_listings: int = Query(default=SCHEDULED_SCAN_MAX_LISTINGS, ge=1, le=1000),
    eur_huf_rate: float = Query(default=analyzer.DEFAULT_EUR_HUF_RATE, gt=0),
):
    """
    Same claim-and-run flow as POST /api/scraper/trigger (they share one
    is-running flag, so they can't double-run each other) — a distinct,
    stable path meant for external cron/webhook callers and the twice-daily
    APScheduler job (see on_startup()) to hit, independent of whatever the
    frontend's own "Scan Market" button happens to be wired to. Subject to
    the same ACCESS_PASSCODE gate as every other endpoint when that's
    configured (see app/access_control.py) — "open" here means no
    additional auth beyond that, not a deliberate bypass of it.
    """
    status, claimed = scraper_jobs.try_start(max_listings=max_listings, eur_huf_rate=eur_huf_rate)
    if claimed:
        background_tasks.add_task(scraper_jobs.run_job, max_listings, eur_huf_rate)
        message = "Scan started successfully"
    else:
        message = "A scan is already running"
    return {"status": "running", "message": message, **status}


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------

@app.post("/properties", response_model=schemas.PropertyOut, status_code=201, tags=["properties"])
def create_property(payload: schemas.PropertyCreate, db: Session = Depends(get_db)):
    return crud.create_property(db, payload)


@app.get("/properties", response_model=List[schemas.PropertyOut], tags=["properties"])
def list_properties(
    skip: int = 0,
    limit: Optional[int] = Query(default=None, ge=1, le=5000, description="Omit for every matching row."),
    district: Optional[str] = Query(
        default=None, description="Single district or comma-separated list, e.g. 'V,VI,VII'."
    ),
    min_price_huf: Optional[float] = None,
    max_price_huf: Optional[float] = None,
    min_size_sqm: Optional[float] = None,
    max_size_sqm: Optional[float] = None,
    portal: Optional[str] = Query(
        default=None, description="Single portal or comma-separated list, e.g. 'jofogas,ingatlanbazar'."
    ),
    favorites_only: bool = False,
    db: Session = Depends(get_db),
):
    return crud.list_properties(
        db,
        skip=skip,
        limit=limit,
        districts=_parse_districts(district),
        min_price_huf=min_price_huf,
        max_price_huf=max_price_huf,
        min_size_sqm=min_size_sqm,
        max_size_sqm=max_size_sqm,
        portals=_parse_portals(portal),
        favorites_only=favorites_only,
    )


@app.get("/properties/{property_id}", response_model=schemas.PropertyOut, tags=["properties"])
def get_property(property_id: int, db: Session = Depends(get_db)):
    prop = crud.get_property(db, property_id)
    if prop is None:
        raise HTTPException(status_code=404, detail="Property not found")
    return prop


@app.patch("/properties/{property_id}", response_model=schemas.PropertyOut, tags=["properties"])
def update_property(property_id: int, payload: schemas.PropertyUpdate, db: Session = Depends(get_db)):
    prop = crud.update_property(db, property_id, payload)
    if prop is None:
        raise HTTPException(status_code=404, detail="Property not found")
    return prop


@app.delete("/properties/{property_id}", status_code=204, tags=["properties"])
def delete_property(property_id: int, db: Session = Depends(get_db)):
    deleted = crud.delete_property(db, property_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Property not found")
    return None


@app.get("/properties/{property_id}/analysis", tags=["properties"])
def analyze_property_endpoint(
    property_id: int,
    district_number: Optional[int] = Query(
        default=None,
        description="Override the district benchmark to use (1-23). "
        "Defaults to parsing the property's own `district` field (e.g. 'VII' -> 7).",
    ),
    eur_huf_rate: float = Query(
        default=analyzer.DEFAULT_EUR_HUF_RATE,
        gt=0,
        description="EUR->HUF rate to use for renovation costs. Pass today's actual rate for accuracy.",
    ),
    custom_renovation_cost_eur_sqm: Optional[float] = Query(
        default=None,
        ge=0,
        description="Optional custom renovation cost (EUR/sqm) — adds a 4th 'custom' tier alongside light/medium/full.",
    ),
    db: Session = Depends(get_db),
):
    """
    Renovation cost, acquisition cost, exit price, net profit and ROI for
    this property across the Light/Medium/Full renovation tiers (plus an
    optional custom tier), using the matching
    DistrictBenchmark.avg_price_sqm_renovated as the exit price basis.
    """
    try:
        result = analyzer.analyze_property_by_id(
            db,
            property_id,
            district_number=district_number,
            eur_huf_rate=eur_huf_rate,
            custom_cost_eur_per_sqm=custom_renovation_cost_eur_sqm,
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result.to_dict()


@app.post("/properties/{property_id}/underwrite", tags=["properties"])
def underwrite_property_endpoint(property_id: int, db: Session = Depends(get_db)):
    """
    Manually (re-)run the automated underwriting agent (app/services/
    valuation_agent.py) for one property and persist the result — normally
    this runs automatically at the end of every scrape (see
    scraper/pipeline.py), so this is for backfilling a property that
    predates the feature, or refreshing one after a district-benchmark edit.
    """
    prop = crud.get_property(db, property_id)
    if prop is None:
        raise HTTPException(status_code=404, detail=f"Property {property_id} not found")
    result = valuation_agent.validate_and_underwrite_and_persist(db, property_id)
    return result.to_dict()


@app.get("/properties/{property_id}/spec-sheet", tags=["properties"])
def property_spec_sheet(
    property_id: int,
    eur_huf_rate: float = Query(
        default=analyzer.DEFAULT_EUR_HUF_RATE,
        gt=0,
        description="EUR->HUF rate for the optional investment-context line (renovation ROI needs it).",
    ),
    db: Session = Depends(get_db),
):
    """
    Contractor Spec Sheet: a printable PDF with floor space, room count,
    current photos, and an on-site quoting checklist for this property.
    District benchmark / renovation ROI is included as context when available,
    but the sheet still generates fine without it.
    """
    prop = crud.get_property(db, property_id)
    if prop is None:
        raise HTTPException(status_code=404, detail="Property not found")

    benchmark = None
    try:
        district_number = analyzer.parse_district_number(prop.district)
        benchmark = crud.get_district_benchmark(db, district_number)
    except ValueError:
        pass  # unparseable/unknown district — sheet still generates, just without benchmark context

    analysis = None
    try:
        analysis = analyzer.analyze_property_by_id(db, property_id, eur_huf_rate=eur_huf_rate)
    except (LookupError, ValueError):
        pass

    pdf_bytes = spec_sheet.generate_spec_sheet_pdf(prop, benchmark=benchmark, analysis=analysis)
    filename = f"spec-sheet-property-{property_id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/properties/{property_id}/investment-memo", tags=["properties"])
def property_investment_memo(
    property_id: int,
    eur_huf_rate: float = Query(default=analyzer.DEFAULT_EUR_HUF_RATE, gt=0),
    db: Session = Depends(get_db),
):
    """
    Deal Memo: a single-page, executive-level PDF built from the automated
    underwriting agent's persisted verdict (app/services/valuation_agent.py)
    — asking price, district baseline, discount to market, renovation
    budget, all-in investment, exit value, net profit/ROI, Deal Score, and
    an auto-generated Investment Thesis — for handing to a partner/lender.
    """
    prop = crud.get_property(db, property_id)
    if prop is None:
        raise HTTPException(status_code=404, detail="Property not found")

    benchmark = None
    try:
        district_number = analyzer.parse_district_number(prop.district)
        benchmark = crud.get_district_benchmark(db, district_number)
    except ValueError:
        pass

    _analysis_dict, best_tier, _discount, score = dashboard.compute_live_deal_metrics(db, prop, eur_huf_rate)
    underwriting = dashboard.build_underwriting_dict(prop, best_tier, score)

    pdf_bytes = investment_memo.generate_investment_memo_pdf(
        prop, benchmark=benchmark, eur_huf_rate=eur_huf_rate, underwriting=underwriting
    )
    filename = f"investment-memo-property-{property_id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Live FX rate
# ---------------------------------------------------------------------------

@app.get("/fx-rate", tags=["meta"])
def get_fx_rate(refresh: bool = Query(default=False, description="Force a live refetch, bypassing the cache.")):
    """Live EUR->HUF rate (frankfurter.app / ECB), cached ~1h. The frontend pre-fills its editable override from this."""
    return fx_rate.get_fx_rate(force_refresh=refresh)


# ---------------------------------------------------------------------------
# Dashboard (KPIs + the enriched, filterable deals list the frontend renders)
# ---------------------------------------------------------------------------

@app.get("/dashboard/stats", tags=["dashboard"])
def dashboard_stats(
    eur_huf_rate: float = Query(default=analyzer.DEFAULT_EUR_HUF_RATE, gt=0),
    top_n: int = Query(default=5, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """Total listings tracked, average Budapest EUR/sqm, and the top undervalued deals."""
    return dashboard.compute_stats(db, eur_huf_rate=eur_huf_rate, top_n=top_n)


@app.get("/deals", tags=["dashboard"])
def list_deals(
    district: Optional[str] = Query(
        default=None, description="Single district or comma-separated list, e.g. 'V,VI,VII'."
    ),
    min_roi: Optional[float] = Query(default=None, description="Minimum best-tier ROI %% required to be included."),
    min_flip_roi: Optional[float] = Query(
        default=dashboard.DEFAULT_MIN_FLIP_ROI_PERCENT,
        description=(
            "Strict Net ROI hurdle applied to the persisted underwriting flip ROI "
            "(after renovation, 4%% acquisition tax, 1.5%% legal/closing, 3%% broker "
            "fee). Defaults to the platform's minimum profitability bar. Pass a very "
            "low number (or omit via a negative value) to see the full market including "
            "sub-hurdle deals."
        ),
    ),
    min_size_sqm: Optional[float] = None,
    max_size_sqm: Optional[float] = None,
    min_price_huf: Optional[float] = None,
    max_price_huf: Optional[float] = None,
    min_price_per_sqm: Optional[float] = None,
    max_price_per_sqm: Optional[float] = None,
    portal: Optional[str] = Query(
        default=None, description="Single portal or comma-separated list, e.g. 'jofogas,ingatlanbazar'."
    ),
    favorites_only: bool = False,
    pipeline_status: Optional[str] = Query(
        default=None, description="Filter to a single pipeline status, e.g. 'tour_scheduled'."
    ),
    eur_huf_rate: float = Query(default=analyzer.DEFAULT_EUR_HUF_RATE, gt=0),
    sort: str = Query(
        default=dashboard.DEFAULT_SORT,
        description=f"One of {dashboard.SORT_OPTIONS}. Unrecognized values fall back to 'newest'.",
    ),
    skip: int = 0,
    limit: Optional[int] = Query(default=None, ge=1, le=5000, description="Omit for every matching listing."),
    db: Session = Depends(get_db),
):
    """
    Properties (DB-filtered by district/size/price/portal/favorite/pipeline
    status) enriched with their full renovation analysis and Deal Score,
    further filtered by min_roi (best tier) and min_flip_roi (the strict
    underwriting Net ROI hurdle) when given, sorted by `sort`. This is the
    single endpoint the dashboard's table/card/split-map views and detail
    modal all read from — each item already carries everything the UI
    needs. Omitting `limit` returns every relevant listing.
    """
    if pipeline_status is not None and pipeline_status not in models.PIPELINE_STATUSES:
        raise HTTPException(
            status_code=422, detail=f"pipeline_status must be one of {models.PIPELINE_STATUSES}, got {pipeline_status!r}"
        )
    return dashboard.list_deals(
        db,
        districts=_parse_districts(district),
        min_roi=min_roi,
        min_flip_roi=min_flip_roi,
        min_size_sqm=min_size_sqm,
        max_size_sqm=max_size_sqm,
        min_price_huf=min_price_huf,
        max_price_huf=max_price_huf,
        min_price_per_sqm=min_price_per_sqm,
        max_price_per_sqm=max_price_per_sqm,
        portals=_parse_portals(portal),
        favorites_only=favorites_only,
        pipeline_status=pipeline_status,
        eur_huf_rate=eur_huf_rate,
        sort_by=sort,
        skip=skip,
        limit=limit,
    )


@app.get("/deals/export.csv", tags=["dashboard"])
def export_deals_csv(
    district: Optional[str] = Query(default=None),
    min_roi: Optional[float] = Query(default=None),
    min_flip_roi: Optional[float] = Query(default=dashboard.DEFAULT_MIN_FLIP_ROI_PERCENT),
    min_size_sqm: Optional[float] = None,
    max_size_sqm: Optional[float] = None,
    min_price_huf: Optional[float] = None,
    max_price_huf: Optional[float] = None,
    min_price_per_sqm: Optional[float] = None,
    max_price_per_sqm: Optional[float] = None,
    portal: Optional[str] = Query(default=None),
    favorites_only: bool = False,
    pipeline_status: Optional[str] = Query(default=None),
    eur_huf_rate: float = Query(default=analyzer.DEFAULT_EUR_HUF_RATE, gt=0),
    sort: str = Query(default=dashboard.DEFAULT_SORT),
    db: Session = Depends(get_db),
):
    """
    CSV export of the exact same filtered/sorted set GET /deals would
    return for these params (full underwriting metrics included, no
    pagination — every matching listing is one row) — powers the
    dashboard's "Export CSV" button.
    """
    if pipeline_status is not None and pipeline_status not in models.PIPELINE_STATUSES:
        raise HTTPException(
            status_code=422, detail=f"pipeline_status must be one of {models.PIPELINE_STATUSES}, got {pipeline_status!r}"
        )
    deals = dashboard.list_deals(
        db,
        districts=_parse_districts(district),
        min_roi=min_roi,
        min_flip_roi=min_flip_roi,
        min_size_sqm=min_size_sqm,
        max_size_sqm=max_size_sqm,
        min_price_huf=min_price_huf,
        max_price_huf=max_price_huf,
        min_price_per_sqm=min_price_per_sqm,
        max_price_per_sqm=max_price_per_sqm,
        portals=_parse_portals(portal),
        favorites_only=favorites_only,
        pipeline_status=pipeline_status,
        eur_huf_rate=eur_huf_rate,
        sort_by=sort,
    )
    csv_text = dashboard.deals_to_csv(deals)
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="budapest-deals-export.csv"'},
    )


# ---------------------------------------------------------------------------
# District benchmarks
# ---------------------------------------------------------------------------

@app.post(
    "/district-benchmarks",
    response_model=schemas.DistrictBenchmarkOut,
    status_code=201,
    tags=["district-benchmarks"],
)
def create_district_benchmark(payload: schemas.DistrictBenchmarkCreate, db: Session = Depends(get_db)):
    existing = crud.get_district_benchmark(db, payload.district_number)
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Benchmark for district {payload.district_number} already exists. Use PATCH to update it.",
        )
    return crud.create_district_benchmark(db, payload)


@app.get(
    "/district-benchmarks",
    response_model=List[schemas.DistrictBenchmarkOut],
    tags=["district-benchmarks"],
)
def list_district_benchmarks(db: Session = Depends(get_db)):
    return crud.list_district_benchmarks(db)


@app.get(
    "/district-benchmarks/{district_number}",
    response_model=schemas.DistrictBenchmarkOut,
    tags=["district-benchmarks"],
)
def get_district_benchmark(district_number: int, db: Session = Depends(get_db)):
    benchmark = crud.get_district_benchmark(db, district_number)
    if benchmark is None:
        raise HTTPException(status_code=404, detail="District benchmark not found")
    return benchmark


@app.patch(
    "/district-benchmarks/{district_number}",
    response_model=schemas.DistrictBenchmarkOut,
    tags=["district-benchmarks"],
)
def upsert_district_benchmark(
    district_number: int, payload: schemas.DistrictBenchmarkUpdate, db: Session = Depends(get_db)
):
    return crud.upsert_district_benchmark(db, district_number, payload)


@app.post(
    "/district-benchmarks/recompute",
    tags=["district-benchmarks"],
)
def recompute_district_benchmarks(db: Session = Depends(get_db)):
    """
    On-demand refresh of every district's live median price/sqm from
    currently stored listings — see app/services/stats_service.py. The
    twice-daily scan cycle and app startup already call this automatically;
    this route is for triggering it manually (e.g. right after a bulk
    import) without waiting for either.
    """
    districts_updated = stats_service.update_district_benchmarks(db)
    return {"districts_updated": districts_updated}


@app.delete("/district-benchmarks/{district_number}", status_code=204, tags=["district-benchmarks"])
def delete_district_benchmark(district_number: int, db: Session = Depends(get_db)):
    deleted = crud.delete_district_benchmark(db, district_number)
    if not deleted:
        raise HTTPException(status_code=404, detail="District benchmark not found")
    return None
