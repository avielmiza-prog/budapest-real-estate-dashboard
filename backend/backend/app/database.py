"""
Database engine / session setup for the Budapest Apartments backend.

Uses SQLite by default (file: budapest_apartments.db in the backend/ folder).
Override with the DATABASE_URL env var to point at Postgres instead (e.g. for
a Render/Railway/Supabase deployment) without touching this file — see
.env.example for the exact variables this module and app/main.py read.
"""
import os
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

# app/__init__.py loads .env before any app.* submodule (this one included)
# runs its own module-level os.getenv(...) calls — see its docstring.
BASE_DIR = Path(__file__).resolve().parent.parent

DEFAULT_SQLITE_PATH = BASE_DIR / "budapest_apartments.db"

_raw_database_url = os.getenv("DATABASE_URL", f"sqlite:///{DEFAULT_SQLITE_PATH}")
# Render/Railway/Supabase/Heroku-style providers often hand out a
# `postgres://` URL — SQLAlchemy 1.4+ only accepts the `postgresql://`
# scheme and raises on the old one, which is a common first-deploy trip-up.
if _raw_database_url.startswith("postgres://"):
    _raw_database_url = "postgresql://" + _raw_database_url[len("postgres://") :]
DATABASE_URL = _raw_database_url

# check_same_thread=False is needed only for SQLite, since FastAPI can hand
# requests to different threads than the one that created the connection.
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency that yields a DB session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _sql_default_literal(value):
    """Render a Python default value as a SQL literal for an ALTER TABLE ... DEFAULT clause."""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    return None  # callables (e.g. datetime.utcnow) or anything else: no safe literal, omit DEFAULT


def run_startup_migrations() -> None:
    """
    Lightweight, idempotent auto-migration for the existing SQLite file: adds
    any column present on the SQLAlchemy models but missing from the actual
    database (e.g. after a schema change) via `ALTER TABLE ... ADD COLUMN`.
    No-op for columns that already exist. Only additive — never drops,
    renames, or alters an existing column, which is all SQLite itself
    supports via ALTER TABLE anyway. Deliberately no external migration tool
    (Alembic etc.) since this is a single SQLite file, not multi-environment
    infra — proportionate for this project's size.
    """
    from app import models  # noqa: F401 - ensure models are registered on Base.metadata

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    with engine.begin() as conn:
        for table in Base.metadata.tables.values():
            if table.name not in existing_tables:
                continue  # brand-new table: create_all() (called separately) already handles it
            existing_columns = {col["name"] for col in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing_columns:
                    continue
                column_type = column.type.compile(dialect=engine.dialect)
                default_sql = ""
                if column.default is not None and getattr(column.default, "is_scalar", False):
                    literal = _sql_default_literal(column.default.arg)
                    if literal is not None:
                        default_sql = f" DEFAULT {literal}"
                elif not column.nullable:
                    # NOT NULL with no usable scalar default (e.g. a server-side
                    # generated value) — fall back to nullable so ADD COLUMN
                    # doesn't fail on SQLite's "NOT NULL needs a default" rule.
                    column_type = column.type.compile(dialect=engine.dialect)
                conn.execute(
                    text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {column_type}{default_sql}')
                )


def init_db() -> None:
    """Create all tables that don't exist yet, then patch existing tables up to the current schema."""
    # Import models here so they're registered on Base.metadata before create_all.
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    run_startup_migrations()
