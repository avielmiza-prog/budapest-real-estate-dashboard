"""
Verifies app.database.run_startup_migrations (invoked via init_db()) is
additive and idempotent: starting from a table matching the schema BEFORE
this upgrade (missing portal/latitude/longitude/balcony_sqm/is_favorite/
pipeline_status), it should add exactly the missing columns via
ALTER TABLE without touching existing rows, and running it again should be
a safe no-op.

Run with: python3 tests/test_migration.py
Requires the real `sqlalchemy` package (already a project dependency) and
runs against a throwaway SQLite file — never the real budapest_apartments.db.
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sqlalchemy as sa  # noqa: E402


def _make_old_schema_db(db_path: Path) -> None:
    """A `properties` table shaped like it was before this upgrade added new columns."""
    engine = sa.create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                """
                CREATE TABLE properties (
                    id INTEGER PRIMARY KEY,
                    title VARCHAR(500) NOT NULL,
                    district VARCHAR(50) NOT NULL,
                    address VARCHAR(500),
                    size_sqm FLOAT,
                    rooms FLOAT,
                    price_huf FLOAT,
                    price_eur FLOAT,
                    price_per_sqm FLOAT,
                    url VARCHAR(1000) UNIQUE,
                    condition VARCHAR(100),
                    images JSON,
                    created_at DATETIME NOT NULL
                )
                """
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO properties (id, title, district, created_at) "
                "VALUES (1, 'Old row', 'VII', '2026-01-01 00:00:00')"
            )
        )
    engine.dispose()


def test_migration_adds_missing_columns_without_losing_data():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "old.db"
        _make_old_schema_db(db_path)

        os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
        for mod in list(sys.modules):
            if mod == "app" or mod.startswith("app."):
                del sys.modules[mod]
        from app import database  # noqa: E402 - first import in this process picks up DATABASE_URL above

        database.init_db()

        inspector = sa.inspect(database.engine)
        columns = {c["name"] for c in inspector.get_columns("properties")}
        for expected in [
            "portal",
            "latitude",
            "longitude",
            "balcony_sqm",
            "is_favorite",
            "pipeline_status",
        ]:
            assert expected in columns, f"{expected} missing after migration"

        with database.engine.connect() as conn:
            row = conn.execute(
                sa.text("SELECT title, is_favorite, pipeline_status FROM properties WHERE id = 1")
            ).fetchone()
        assert row[0] == "Old row", "pre-existing row's data must survive the migration"
        assert row[1] in (0, False), "NOT NULL column added via migration needs its DEFAULT applied to old rows"
        assert row[2] == "new"

        # Idempotent: running it again on an already-migrated DB must not error or duplicate columns.
        database.init_db()
        inspector_again = sa.inspect(database.engine)
        assert {c["name"] for c in inspector_again.get_columns("properties")} == columns

        database.engine.dispose()


if __name__ == "__main__":
    tests = [test_migration_adds_missing_columns_without_losing_data]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"PASS: {t.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL: {t.__name__}: {e}")
    print(f"\n{len(tests) - failures}/{len(tests)} tests passed")
    sys.exit(1 if failures else 0)
