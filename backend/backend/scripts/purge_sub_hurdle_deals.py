"""
Delete every stored Property row whose persisted underwriting flip ROI is
below the strict Net ROI hurdle (app.services.valuation_agent.MIN_HURDLE_ROI_PERCENT).

Only rows that HAVE a computed flip_roi_percent are considered — a property
that hasn't been underwritten yet (no district benchmark, or never scanned by
the agent) is left alone rather than guessed at. Run scripts/run_underwriting.py
first if you want every row re-evaluated before purging.

Run from backend/backend:
    python3 scripts/purge_sub_hurdle_deals.py --dry-run   # preview, deletes nothing
    python3 scripts/purge_sub_hurdle_deals.py              # actually deletes
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
    parser.add_argument("--dry-run", action="store_true", help="Report what would be deleted without deleting it.")
    args = parser.parse_args()

    init_db()
    db = SessionLocal()
    try:
        hurdle = valuation_agent.MIN_HURDLE_ROI_PERCENT
        condemned = (
            db.query(models.Property)
            .filter(
                models.Property.underwriting_flip_roi_percent.isnot(None),
                models.Property.underwriting_flip_roi_percent < hurdle,
            )
            .all()
        )

        print(f"{len(condemned)} propert{'y' if len(condemned) == 1 else 'ies'} below the {hurdle:.0f}% hurdle:", file=sys.stderr)
        for prop in condemned:
            print(f"  #{prop.id} {prop.title!r} ({prop.district}) flip_roi={prop.underwriting_flip_roi_percent:.2f}%", file=sys.stderr)

        if args.dry_run:
            print("Dry run — nothing deleted.", file=sys.stderr)
            return 0

        for prop in condemned:
            db.delete(prop)
        db.commit()
        print(f"Deleted {len(condemned)} propert{'y' if len(condemned) == 1 else 'ies'}.", file=sys.stderr)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
