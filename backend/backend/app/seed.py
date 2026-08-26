"""
Startup auto-seed for district benchmarks ONLY — not listings.

Deliberately scoped this narrowly. Real property listings already come from
an actual live scrape (jofogas.hu etc. — see scraper/) and that already
works end to end; auto-loading a static JSON snapshot of listings into the
properties table would reintroduce exactly the stale-snapshot-vs-live-data
ambiguity this project has spent real effort eliminating (see
scripts/seed_data.py's fictional-mock-data warnings and every "clear mock
data" pass in this codebase's history). District benchmarks are different:
they're a small, mostly-static per-district reference table (avg HUF/sqm,
avg rent) that the analysis/deal-score engine needs to compute anything at
all — it isn't scraped, so a fresh database (a brand-new Render deploy, a
teammate's first local run) has zero rows for it until someone manually
POSTs all 23 or runs scripts/seed_data.py, and every deal's ROI/score comes
back null in the meantime even though real listings are already flowing in.

seed_data.json is a snapshot of this project's own district_benchmarks
table (see the git history for how it was generated) — not fictional.
"""
import json
import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app import crud, schemas

logger = logging.getLogger(__name__)

SEED_DATA_PATH = Path(__file__).resolve().parent.parent / "seed_data.json"


def seed_district_benchmarks_if_empty(db: Session) -> int:
    """Returns the number of rows inserted (0 if the table already had data or the seed file is missing)."""
    if crud.list_district_benchmarks(db):
        return 0

    if not SEED_DATA_PATH.exists():
        logger.info("No seed_data.json at %s — skipping district-benchmark auto-seed.", SEED_DATA_PATH)
        return 0

    try:
        with open(SEED_DATA_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("Could not read/parse %s — skipping district-benchmark auto-seed: %s", SEED_DATA_PATH, e)
        return 0

    rows = data.get("district_benchmarks", [])
    inserted = 0
    for row in rows:
        try:
            payload = schemas.DistrictBenchmarkCreate(**row)
        except Exception as e:  # noqa: BLE001 - one malformed row shouldn't block the rest
            logger.warning("Skipping malformed district-benchmark seed row %r: %s", row, e)
            continue
        crud.create_district_benchmark(db, payload)
        inserted += 1

    if inserted:
        logger.info("Auto-seeded %d district benchmark(s) from %s (table was empty).", inserted, SEED_DATA_PATH)
    return inserted
