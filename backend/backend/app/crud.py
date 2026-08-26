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

    if existing is None:
        prop = models.Property(**data)
        db.add(prop)
    else:
        for key, value in data.items():
            setattr(existing, key, value)
        prop = existing

    db.commit()
    db.refresh(prop)
    return prop


def list_properties(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    district: Optional[str] = None,
    districts: Optional[List[str]] = None,
    min_price_huf: Optional[float] = None,
    max_price_huf: Optional[float] = None,
    min_size_sqm: Optional[float] = None,
    max_size_sqm: Optional[float] = None,
    portals: Optional[List[str]] = None,
    favorites_only: bool = False,
    pipeline_status: Optional[str] = None,
) -> List[models.Property]:
    query = db.query(models.Property)
    if districts:
        query = query.filter(models.Property.district.in_(districts))
    elif district is not None:
        query = query.filter(models.Property.district == district)
    if min_price_huf is not None:
        query = query.filter(models.Property.price_huf >= min_price_huf)
    if max_price_huf is not None:
        query = query.filter(models.Property.price_huf <= max_price_huf)
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
    return query.order_by(models.Property.created_at.desc()).offset(skip).limit(limit).all()


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
