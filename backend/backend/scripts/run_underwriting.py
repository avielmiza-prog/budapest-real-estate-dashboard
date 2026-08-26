"""
Run the automated underwriting agent (app/services/valuation_agent.py)
against every existing Property row, persisting a fresh verdict for each.

New scrapes already run this automatically (see scraper/pipeline.py's
store_and_analyze) — this script is for backfilling listings that predate
the feature, or refreshing everything after editing district benchmarks.

Run from backend/backend:
    python3 scripts/run_underwriting.py              # every property
    python3 scripts/run_underwriting.py --district VII
    python3 scripts/run_underwriting.py --only-stale  # skip rows already underwritten
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import models  # noqa: E402
from app.database import SessionLocal, init_db  # noqa: E402
from app.services import valuation_agent  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--district", help="Only process this district (e.g. 'VII').")
    parser.add_argument(
        "--only-stale",
        action="store_true",
        help="Skip properties that already have an underwriting verdict (underwriting_updated_at is set).",
    )
    args = parser.parse_args()

    init_db()
    db = SessionLocal()
    try:
        query = db.query(models.Property)
        if args.district:
            query = query.filter(models.Property.district == args.district)
        if args.only_stale:
            query = query.filter(models.Property.underwriting_updated_at.is_(None))
        properties = query.all()

        processed = 0
        by_status: dict = {}
        for prop in properties:
            result = valuation_agent.validate_and_underwrite_and_persist(db, prop.id)
            if result is None:
                continue
            processed += 1
            by_status[result.status] = by_status.get(result.status, 0) + 1

        print(f"Underwrote {processed}/{len(properties)} propert{'y' if processed == 1 else 'ies'}.", file=sys.stderr)
        for status, count in sorted(by_status.items()):
            print(f"  {status}: {count}", file=sys.stderr)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
