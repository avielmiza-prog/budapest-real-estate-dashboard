"""
Dynamic per-district price/sqm benchmark computation from live scraped
Property data — refreshes DistrictBenchmark's avg_price_sqm_raw/renovated
with real statistical medians once enough data has been collected, while
keeping the static seed_data.json snapshot (see app/seed.py) as the
documented fallback for districts that don't have enough data yet.

update_district_benchmarks() is the single entrypoint. It's called:
  - once at startup (app/main.py's on_startup()), best-effort, so an
    existing database's benchmarks reflect live data immediately instead of
    waiting for the next scheduled scan;
  - after every scan cycle (app/scraper_jobs.py's run_job()), so freshly
    scraped listings feed back into the medians other listings get
    underwritten against;
  - on demand via POST /district-benchmarks/recompute.

Methodology:
  - Rolling window: only Property rows scraped within the last
    ROLLING_WINDOW_DAYS days are included — a stale, months-old listing
    shouldn't anchor today's median.
  - Grouped by district (1-23) x condition category ("raw" = Needs
    Renovation/Average, "renovated" = Renovated/New Construction — see
    app.condition_classifier), matching the two columns DistrictBenchmark
    already exposes.
  - Outlier trim: the bottom/top OUTLIER_TRIM_FRACTION of each group's
    price_per_sqm values are dropped before taking the median, so one
    mispriced/anomalous listing can't skew a whole district's benchmark.
  - MIN_LIVE_SAMPLES: a district/category needs at least this many
    *pre-trim* samples to be trusted as "live" — below that, the median
    would be too noisy to publish, so the row falls back to
    seed_data.json's documented baseline instead (source_raw/
    source_renovated="fallback"). The live sample count is still recorded
    either way, so the UI can always show "Based on N recent listings"
    even for a fallback row.
"""
import datetime
import json
import logging
import statistics
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app import models
from app.analyzer import parse_district_number
from app.condition_classifier import CONDITION_NEW_CONSTRUCTION, CONDITION_RENOVATED, classify_condition_tag

logger = logging.getLogger(__name__)

ROLLING_WINDOW_DAYS = 90  # last 30-90 days of scraped data feed the median; see module docstring
MIN_LIVE_SAMPLES = 10  # below this many collected samples, fall back to the documented baseline
OUTLIER_TRIM_FRACTION = 0.05  # drop the bottom/top 5% of each group before taking the median

# 85th-percentile exit-price basis for app.services.scenario_analysis's
# "Optimistic" scenario — see DistrictBenchmark.p85_price_sqm_renovated.
OPTIMISTIC_PERCENTILE = 85

SEED_DATA_PATH = Path(__file__).resolve().parent.parent.parent / "seed_data.json"

_RENOVATED_TAGS = {CONDITION_RENOVATED, CONDITION_NEW_CONSTRUCTION}

_baseline_cache: Optional[Dict[int, dict]] = None


def _load_baseline_benchmarks() -> Dict[int, dict]:
    """
    Documented baseline HUF/sqm benchmarks, keyed by district_number.
    seed_data.json — the same file app/seed.py auto-seeds a fresh database
    from — is this project's one documented source for these numbers, so
    this reads that file rather than duplicating a second hand-picked copy
    that could silently drift out of sync with it. Cached for the process
    lifetime: it's a static file, not something that changes at runtime.
    """
    global _baseline_cache
    if _baseline_cache is not None:
        return _baseline_cache
    baseline: Dict[int, dict] = {}
    try:
        with open(SEED_DATA_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        for row in data.get("district_benchmarks", []):
            baseline[row["district_number"]] = row
    except (OSError, json.JSONDecodeError, KeyError) as e:
        logger.warning("Could not read/parse %s for baseline benchmarks: %s", SEED_DATA_PATH, e)
    _baseline_cache = baseline
    return baseline


def _condition_category(condition_text: Optional[str]) -> str:
    """'renovated' or 'raw' — the two buckets DistrictBenchmark tracks."""
    return "renovated" if classify_condition_tag(condition_text) in _RENOVATED_TAGS else "raw"


def _trimmed_median(values: List[float]) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    n = len(ordered)
    trim = int(n * OUTLIER_TRIM_FRACTION)
    trimmed = ordered[trim : n - trim] if n - 2 * trim > 0 else ordered
    return statistics.median(trimmed)


def _percentile(values: List[float], pct: float) -> Optional[float]:
    """Nearest-rank percentile (0-100) of `values` — no interpolation, simple and dependency-free."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(0, min(len(ordered) - 1, int(round(pct / 100 * (len(ordered) - 1)))))
    return ordered[rank]


def update_district_benchmarks(db: Session) -> int:
    """
    Recomputes avg_price_sqm_raw/avg_price_sqm_renovated for every district
    from live Property data (see module docstring), upserting one
    DistrictBenchmark row per district 1-23. Never touches
    avg_rent_huf_sqm/centroid_lat/centroid_lng on an existing row — those
    aren't derivable from scraped price/sqm data and stay whatever they
    were (seeded or manually set via PATCH).

    Returns the number of districts actually touched (created or updated).
    """
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=ROLLING_WINDOW_DAYS)
    properties = (
        db.query(models.Property)
        .filter(models.Property.price_per_sqm.isnot(None))
        .filter(models.Property.created_at >= cutoff)
        .all()
    )

    # (district_number, category) -> [price_per_sqm, ...]
    groups: Dict[Tuple[int, str], List[float]] = {}
    for prop in properties:
        try:
            district_number = parse_district_number(prop.district)
        except ValueError:
            continue  # unparseable/missing district — can't attribute this listing to a benchmark row
        category = _condition_category(prop.condition)
        groups.setdefault((district_number, category), []).append(prop.price_per_sqm)

    baseline = _load_baseline_benchmarks()
    existing = {b.district_number: b for b in db.query(models.DistrictBenchmark).all()}

    touched = 0
    for district_number in range(1, 24):
        raw_values = groups.get((district_number, "raw"), [])
        renovated_values = groups.get((district_number, "renovated"), [])
        base_row = baseline.get(district_number, {})

        if len(raw_values) >= MIN_LIVE_SAMPLES:
            avg_price_sqm_raw = _trimmed_median(raw_values)
            source_raw = "live"
        else:
            avg_price_sqm_raw = base_row.get("avg_price_sqm_raw")
            source_raw = "fallback"

        if len(renovated_values) >= MIN_LIVE_SAMPLES:
            avg_price_sqm_renovated = _trimmed_median(renovated_values)
            source_renovated = "live"
            p85_price_sqm_renovated = _percentile(renovated_values, OPTIMISTIC_PERCENTILE)
        else:
            avg_price_sqm_renovated = base_row.get("avg_price_sqm_renovated")
            source_renovated = "fallback"
            # No live sample set to draw a real percentile from — leave it
            # unset; app.services.scenario_analysis falls back to a
            # documented multiplier of avg_price_sqm_renovated instead.
            p85_price_sqm_renovated = None

        benchmark = existing.get(district_number)
        if benchmark is None:
            if avg_price_sqm_raw is None and avg_price_sqm_renovated is None:
                continue  # nothing live and no documented baseline either — nothing to create
            benchmark = models.DistrictBenchmark(
                district_number=district_number,
                avg_rent_huf_sqm=base_row.get("avg_rent_huf_sqm"),
                centroid_lat=base_row.get("centroid_lat"),
                centroid_lng=base_row.get("centroid_lng"),
            )
            db.add(benchmark)

        benchmark.avg_price_sqm_raw = avg_price_sqm_raw
        benchmark.avg_price_sqm_renovated = avg_price_sqm_renovated
        benchmark.sample_count_raw = len(raw_values)
        benchmark.sample_count_renovated = len(renovated_values)
        benchmark.source_raw = source_raw
        benchmark.source_renovated = source_renovated
        benchmark.p85_price_sqm_renovated = p85_price_sqm_renovated
        touched += 1

    db.commit()
    logger.info(
        "update_district_benchmarks: refreshed %d district(s) from %d live listing(s) (last %d days)",
        touched,
        len(properties),
        ROLLING_WINDOW_DAYS,
    )
    return touched


# Below MIN_LIVE_SAMPLES for a given (district, building_type) pair, no row
# is published — a noisy 2-3-sample "median" segmented this finely would be
# actively misleading rather than just imprecise. Deliberately smaller than
# MIN_LIVE_SAMPLES (district-only medians): a per-building-type cut of the
# same rolling window naturally has fewer samples per bucket, and this
# benchmark is informational-only (see BuildingTypeBenchmark's docstring),
# never fed into the actual ROI math the way avg_price_sqm_renovated is.
MIN_BUILDING_TYPE_SAMPLES = 5


def update_building_type_benchmarks(db: Session) -> int:
    """
    Recomputes BuildingTypeBenchmark's avg_price_sqm/sample_count for every
    (district, building_type) pair seen in the same rolling window as
    update_district_benchmarks() — median HUF/sqm segmented by district AND
    building type (Polgári/Panelház/Új építés), for the "sub-market
    precision" comparison surfaced via GET /building-type-benchmarks and
    each /deals item. Purely informational — see that model's docstring for
    why the core ROI math stays on the district-only benchmark.

    Returns the number of (district, building_type) rows actually touched.
    """
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=ROLLING_WINDOW_DAYS)
    properties = (
        db.query(models.Property)
        .filter(models.Property.price_per_sqm.isnot(None))
        .filter(models.Property.building_type.isnot(None))
        .filter(models.Property.created_at >= cutoff)
        .all()
    )

    groups: Dict[Tuple[int, str], List[float]] = {}
    for prop in properties:
        try:
            district_number = parse_district_number(prop.district)
        except ValueError:
            continue
        groups.setdefault((district_number, prop.building_type), []).append(prop.price_per_sqm)

    existing = {
        (b.district_number, b.building_type): b for b in db.query(models.BuildingTypeBenchmark).all()
    }

    touched = 0
    for (district_number, building_type), values in groups.items():
        if len(values) < MIN_BUILDING_TYPE_SAMPLES:
            continue
        key = (district_number, building_type)
        benchmark = existing.get(key)
        if benchmark is None:
            benchmark = models.BuildingTypeBenchmark(district_number=district_number, building_type=building_type)
            db.add(benchmark)
        benchmark.avg_price_sqm = _trimmed_median(values)
        benchmark.sample_count = len(values)
        touched += 1

    db.commit()
    logger.info("update_building_type_benchmarks: refreshed %d (district, building_type) row(s)", touched)
    return touched
