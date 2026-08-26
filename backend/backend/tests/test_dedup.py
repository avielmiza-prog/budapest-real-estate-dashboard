"""
Unit tests for scraper.dedup — cross-portal duplicate detection run once per
scan cycle (see scraper/agent/orchestrator.py's run_agent()).

Run with: python -m pytest tests/test_dedup.py -q
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_tmp_db_dir = tempfile.mkdtemp(prefix="budapest_apartments_test_dedup_")
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_tmp_db_dir) / 'test.db'}"

from app import crud, models, schemas  # noqa: E402
from app.database import SessionLocal, init_db  # noqa: E402
from scraper.dedup import dedup_properties  # noqa: E402

init_db()


def _make_property(db, **overrides) -> models.Property:
    payload = {
        "title": "Test flat",
        "district": "VII",
        "size_sqm": 50.0,
        "price_huf": 40_000_000.0,
        "portal": "jofogas",
    }
    payload.update(overrides)
    payload.setdefault("url", f"https://example.test/dedup/{id(payload)}-{payload['title']}")
    prop = crud.create_property(db, schemas.PropertyCreate(**payload))
    return prop


def test_no_duplicates_removes_nothing():
    db = SessionLocal()
    try:
        _make_property(db, url="https://a.test/1", district="V", size_sqm=40.0, price_huf=30_000_000.0)
        _make_property(db, url="https://a.test/2", district="VI", size_sqm=60.0, price_huf=50_000_000.0)
        removed = dedup_properties(db)
        assert removed == 0
        assert db.query(models.Property).count() == 2
    finally:
        db.close()


def test_matching_district_size_and_price_are_merged():
    db = SessionLocal()
    try:
        earlier = _make_property(
            db, url="https://portal-a.test/listing-1", district="VIII", size_sqm=55.0, price_huf=45_000_000.0
        )
        later = _make_property(
            # within tolerance: size +1.5 sqm, price +1% -> should merge
            db, url="https://portal-b.test/listing-1", district="VIII", size_sqm=56.5, price_huf=45_450_000.0
        )

        removed = dedup_properties(db)
        assert removed == 1

        survivor = crud.get_property(db, earlier.id)
        assert survivor is not None
        assert crud.get_property(db, later.id) is None
        assert survivor.duplicate_source_urls == ["https://portal-b.test/listing-1"]
    finally:
        db.close()


def test_different_district_is_not_merged():
    db = SessionLocal()
    try:
        _make_property(db, url="https://a.test/x", district="II", size_sqm=50.0, price_huf=40_000_000.0)
        _make_property(db, url="https://a.test/y", district="III", size_sqm=50.0, price_huf=40_000_000.0)
        assert dedup_properties(db) == 0
    finally:
        db.close()


def test_price_outside_tolerance_is_not_merged():
    db = SessionLocal()
    try:
        _make_property(db, url="https://a.test/p1", district="IX", size_sqm=50.0, price_huf=40_000_000.0)
        # +5% price -> outside the 2% tolerance
        _make_property(db, url="https://a.test/p2", district="IX", size_sqm=50.0, price_huf=42_000_000.0)
        assert dedup_properties(db) == 0
    finally:
        db.close()


def test_size_outside_tolerance_is_not_merged():
    db = SessionLocal()
    try:
        _make_property(db, url="https://a.test/s1", district="X", size_sqm=50.0, price_huf=40_000_000.0)
        # +3 sqm -> outside the ±2 sqm tolerance
        _make_property(db, url="https://a.test/s2", district="X", size_sqm=53.0, price_huf=40_000_000.0)
        assert dedup_properties(db) == 0
    finally:
        db.close()


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
