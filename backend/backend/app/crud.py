import datetime
"""
Plain data-access functions, kept separate from the route handlers in main.py
so the HTTP layer and the DB layer don't get tangled together.
"""
from typing import List, Optional

from sqlalchemy.orm import Session

from app import models, schemas

# scripts/seed_data.py stamps every fake/demo listing's url with this prefix
# (e.g. "https://mock.ingatlanbazar.hu/listing/..."), specifically so mock
# rows can always be told apart from real scraped ones (which use the
# portal's real domain, e.g. "https://ingatlanbazar.hu/...").
MOCK_URL_PREFIX = "https://mock."


# ---------------------------------------------------------------------------
# Property
# ---------------------------------------------------------------------------

def _compute_price_per_sqm(price_huf: Optional[float], size_sqm: Optional[float]) -> Optional[float]:
    if price_huf and size_sqm:
        return round(price_huf / size_sqm, 2)
    return None


def create_property(db: Session, payload: schemas.PropertyCreate) -> models.Property:
    data = payload.model_dump()
    if data.get("price_per_sqm") is None:
        data["price_per_sqm"] = _compute_price_per_sqm(data.get("price_huf"), data.get("size_sqm"))
    prop = models.Property(**data)
    db.add(prop)
    db.commit()
    db.refresh(prop)
    return prop


def get_property(db: Session, property_id: int) -> Optional[models.Property]:
    return db.query(models.Property).filter(models.Property.id == property_id).first()


def get_property_by_url(db: Session, url: str) -> Optional[models.Property]:
    return db.query(models.Property).filter(models.Property.url == url).first()


def upsert_property_by_url(db: Session, payload: schemas.PropertyCreate) -> models.Property:
    """
    Create the property if its url isn't already stored, otherwise update the
    existing row in place. This is what the scraper uses — re-scraping the
    same listing (e.g. on a later run, or a price change) should update it,
    not fail on the `url` unique constraint or create a duplicate.
    """
    existing = get_property_by_url(db, payload.url) if payload.url else None
    data = payload.model_dump()
    if data.get("price_per_sqm") is None:
        data["price_per_sqm"] = _compute_price_per_sqm(data.get("price_huf"), data.get("size_sqm"))

    now = datetime.datetime.utcnow()
    if existing is None:
        prop = models.Property(**data)
        prop.last_seen_at = now
        db.add(prop)
    else:
        old_price = existing.price_huf
        new_price = data.get("price_huf")
        if old_price and new_price and abs(new_price - old_price) / old_price > 0.005:
            existing.previous_price_huf = old_price
            existing.price_changed_at = now
        for key, value in data.items():
            setattr(existing, key, value)
        existing.last_seen_at = now
        prop = existing

    db.commit()
    db.refresh(prop)
    return prop


def list_properties(
    db: Session,
    skip: int = 0,
    limit: Optional[int] = 100,
    district: Optional[str] = None,
    districts: Optional[List[str]] = None,
    min_price_huf: Optional[float] = None,
    max_price_huf: Optional[float] = None,
    min_price_per_sqm: Optional[float] = None,
    max_price_per_sqm: Optional[float] = None,
    min_size_sqm: Optional[float] = None,
    max_size_sqm: Optional[float] = None,
    portals: Optional[List[str]] = None,
    favorites_only: bool = False,
    pipeline_status: Optional[str] = None,
) -> List[models.Property]:
    """`limit=None` returns every matching row — no truncation."""
    query = db.query(models.Property)
    if districts:
        query = query.filter(models.Property.district.in_(districts))
    elif district is not None:
        query = query.filter(models.Property.district == district)
    if min_price_huf is not None:
        query = query.filter(models.Property.price_huf >= min_price_huf)
    if max_price_huf is not None:
        query = query.filter(models.Property.price_huf <= max_price_huf)
    if min_price_per_sqm is not None:
        query = query.filter(models.Property.price_per_sqm >= min_price_per_sqm)
    if max_price_per_sqm is not None:
        query = query.filter(models.Property.price_per_sqm <= max_price_per_sqm)
    if min_size_sqm is not None:
        query = query.filter(models.Property.size_sqm >= min_size_sqm)
    if max_size_sqm is not None:
        query = query.filter(models.Property.size_sqm <= max_size_sqm)
    if portals:
        query = query.filter(models.Property.portal.in_(portals))
    if favorites_only:
        query = query.filter(models.Property.is_favorite.is_(True))
    if pipeline_status is not None:
        query = query.filter(models.Property.pipeline_status == pipeline_status)
    query = query.order_by(models.Property.created_at.desc()).offset(skip)
    if limit is not None:
        query = query.limit(limit)
    return query.all()


def count_properties(db: Session) -> int:
    return db.query(models.Property).count()


def update_property(
    db: Session, property_id: int, payload: schemas.PropertyUpdate
) -> Optional[models.Property]:
    prop = get_property(db, property_id)
    if prop is None:
        return None
    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(prop, key, value)

    # Recompute price_per_sqm if either input changed and it wasn't explicitly set.
    if "price_per_sqm" not in update_data and ("price_huf" in update_data or "size_sqm" in update_data):
        prop.price_per_sqm = _compute_price_per_sqm(prop.price_huf, prop.size_sqm)

    db.commit()
    db.refresh(prop)
    return prop


def delete_property(db: Session, property_id: int) -> bool:
    prop = get_property(db, property_id)
    if prop is None:
        return False
    db.delete(prop)
    db.commit()
    return True


def delete_properties_with_url_prefix(db: Session, prefix: str) -> int:
    """
    Delete every Property whose url starts with `prefix`. Used to clear
    fake/mock demo listings (see MOCK_URL_PREFIX, scripts/seed_data.py)
    before or instead of a real scrape, without touching genuinely scraped
    rows. Returns the number of rows deleted.
    """
    matches = db.query(models.Property).filter(models.Property.url.like(f"{prefix}%")).all()
    count = len(matches)
    for prop in matches:
        db.delete(prop)
    db.commit()
    return count


# ---------------------------------------------------------------------------
# DistrictBenchmark
# ---------------------------------------------------------------------------

def create_district_benchmark(
    db: Session, payload: schemas.DistrictBenchmarkCreate
) -> models.DistrictBenchmark:
    benchmark = models.DistrictBenchmark(**payload.model_dump())
    db.add(benchmark)
    db.commit()
    db.refresh(benchmark)
    return benchmark


def get_district_benchmark(db: Session, district_number: int) -> Optional[models.DistrictBenchmark]:
    return (
        db.query(models.DistrictBenchmark)
        .filter(models.DistrictBenchmark.district_number == district_number)
        .first()
    )


def list_district_benchmarks(db: Session) -> List[models.DistrictBenchmark]:
    return db.query(models.DistrictBenchmark).order_by(models.DistrictBenchmark.district_number).all()


def upsert_district_benchmark(
    db: Session, district_number: int, payload: schemas.DistrictBenchmarkUpdate
) -> models.DistrictBenchmark:
    """Create the benchmark row if missing, otherwise patch it. Handy for a scraper/import job."""
    benchmark = get_district_benchmark(db, district_number)
    update_data = payload.model_dump(exclude_unset=True)
    if benchmark is None:
        benchmark = models.DistrictBenchmark(district_number=district_number, **update_data)
        db.add(benchmark)
    else:
        for key, value in update_data.items():
            setattr(benchmark, key, value)
    db.commit()
    db.refresh(benchmark)
    return benchmark


def delete_district_benchmark(db: Session, district_number: int) -> bool:
    benchmark = get_district_benchmark(db, district_number)
    if benchmark is None:
        return False
    db.delete(benchmark)
    db.commit()
    return True


def touch_last_seen(db: Session, urls: List[str]) -> int:
    """Mark listings as still live without re-fetching them. Returns rows updated."""
    if not urls:
        return 0
    now = datetime.datetime.utcnow()
    updated = (
        db.query(models.Property)
        .filter(models.Property.url.in_(list(urls)))
        .update({models.Property.last_seen_at: now}, synchronize_session=False)
    )
    db.commit()
    return updated


def recently_seen_urls(db: Session, portal: str, within_days: int = 7) -> set:
    """URLs of this portal's listings already stored and seen recently: a scan can skip their detail pages."""
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=within_days)
    rows = (
        db.query(models.Property.url)
        .filter(models.Property.portal == portal)
        .filter(models.Property.url.isnot(None))
        .filter(models.Property.last_seen_at >= cutoff)
        .all()
    )
    return {r[0] for r in rows}
