"""
SQLAlchemy ORM models.

Property        -> one scraped/entered apartment listing
DistrictBenchmark -> per-district average price/sqm reference numbers,
                     used to judge whether a given Property is under/over priced.
"""
import datetime

from sqlalchemy import (
    Boolean,
    Column,
    Integer,
    Float,
    String,
    Text,
    DateTime,
    JSON,
)

from app.database import Base

# Pipeline status tags a user can assign to a saved deal, in rough workflow order.
PIPELINE_STATUSES = ("new", "reviewing", "tour_scheduled", "offer_sent", "archived")


class Property(Base):
    __tablename__ = "properties"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(500), nullable=False)
    district = Column(String(50), nullable=False, index=True)  # e.g. "V", "XIII", or "13"
    address = Column(String(500), nullable=True)
    size_sqm = Column(Float, nullable=True)
    rooms = Column(Float, nullable=True)  # float to allow "2+1 half room" style values (e.g. 2.5)
    balcony_sqm = Column(Float, nullable=True)  # None when the source portal doesn't report a size
    price_huf = Column(Float, nullable=True)
    price_eur = Column(Float, nullable=True)
    price_per_sqm = Column(Float, nullable=True)
    url = Column(String(1000), nullable=True, unique=True)
    condition = Column(String(100), nullable=True)  # e.g. "new", "renovated", "raw"/needs renovation
    images = Column(JSON, nullable=True, default=list)  # list[str] of image URLs
    portal = Column(String(50), nullable=True, index=True)  # e.g. "jofogas", "ingatlanbazar"
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    is_favorite = Column(Boolean, nullable=False, default=False)
    pipeline_status = Column(String(30), nullable=False, default="new")
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<Property id={self.id} title={self.title!r} district={self.district!r}>"


class DistrictBenchmark(Base):
    __tablename__ = "district_benchmarks"

    district_number = Column(Integer, primary_key=True)  # 1-23 (Budapest districts I-XXIII)
    avg_price_sqm_raw = Column(Float, nullable=True)  # avg HUF/sqm for unrenovated ("raw") condition
    avg_price_sqm_renovated = Column(Float, nullable=True)  # avg HUF/sqm for renovated condition
    avg_rent_huf_sqm = Column(Float, nullable=True)  # avg monthly HUF/sqm rent, powers rental yield
    centroid_lat = Column(Float, nullable=True)  # map fallback pin + geocoding fallback
    centroid_lng = Column(Float, nullable=True)
    updated_at = Column(
        DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<DistrictBenchmark district={self.district_number}>"
