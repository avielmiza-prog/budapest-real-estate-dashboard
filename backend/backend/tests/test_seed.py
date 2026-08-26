"""
Unit tests for app.seed — the startup auto-seed that populates district
benchmarks (never listings — see app/seed.py's docstring) when that table
is empty, so a freshly-provisioned database (a new Render deploy, a
teammate's first local run) doesn't leave every deal's ROI/score null.

Run with: python -m pytest tests/test_seed.py -q
"""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_tmp_db_dir = tempfile.mkdtemp(prefix="budapest_apartments_test_seed_")
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_tmp_db_dir) / 'test.db'}"

import pytest  # noqa: E402

from app import crud, seed  # noqa: E402
from app.database import SessionLocal, init_db  # noqa: E402

init_db()


def test_real_seed_data_json_is_valid_and_has_all_23_districts():
    """The actual repo artifact, not a fixture — catches a bad export before it ships."""
    assert seed.SEED_DATA_PATH.exists(), f"expected {seed.SEED_DATA_PATH} to exist"
    data = json.loads(seed.SEED_DATA_PATH.read_text(encoding="utf-8"))
    rows = data["district_benchmarks"]
    assert len(rows) == 23
    assert {r["district_number"] for r in rows} == set(range(1, 24))
    for row in rows:
        assert row["avg_price_sqm_renovated"] is not None, row


def _clear_district_benchmarks(db) -> None:
    for b in crud.list_district_benchmarks(db):
        db.delete(b)
    db.commit()


def test_seed_populates_empty_table():
    db = SessionLocal()
    try:
        _clear_district_benchmarks(db)
        assert crud.list_district_benchmarks(db) == []
        inserted = seed.seed_district_benchmarks_if_empty(db)
        assert inserted == 23
        assert len(crud.list_district_benchmarks(db)) == 23
    finally:
        db.close()


def test_seed_is_a_noop_when_table_already_has_data():
    db = SessionLocal()
    try:
        if not crud.list_district_benchmarks(db):
            seed.seed_district_benchmarks_if_empty(db)
        before = len(crud.list_district_benchmarks(db))
        assert before > 0

        inserted = seed.seed_district_benchmarks_if_empty(db)
        assert inserted == 0
        assert len(crud.list_district_benchmarks(db)) == before
    finally:
        db.close()


def test_seed_handles_missing_file_gracefully(monkeypatch, tmp_path):
    db = SessionLocal()
    try:
        for b in crud.list_district_benchmarks(db):
            db.delete(b)
        db.commit()
        monkeypatch.setattr(seed, "SEED_DATA_PATH", tmp_path / "does-not-exist.json")
        assert seed.seed_district_benchmarks_if_empty(db) == 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
