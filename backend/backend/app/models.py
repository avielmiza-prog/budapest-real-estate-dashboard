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

    # Other portals' URLs for the same real-world listing, found by
    # scraper/dedup.py (district + floor area ±2 sqm + price ±2% match) and
    # merged onto this (the earliest-seen) row rather than kept as separate
    # duplicate Property rows. Empty list, never None, when nothing merged.
    duplicate_source_urls = Column(JSON, nullable=True, default=list)

    # Persisted verdict from app/services/valuation_agent.py, computed once
    # per scan (not recomputed live like app.analyzer/app.deal_score's
    # interactive tier tool) — see that module's docstring for why. All
    # nullable: unset until a scan has actually run validate_and_underwrite()
    # against this row (e.g. a property added by hand via POST /properties).
    underwriting_market_value_huf = Column(Float, nullable=True)  # projected turnkey exit price
    underwriting_renovation_cost_huf = Column(Float, nullable=True)
    underwriting_total_investment_huf = Column(Float, nullable=True)
    underwriting_net_profit_huf = Column(Float, nullable=True)
    underwriting_flip_roi_percent = Column(Float, nullable=True)
    underwriting_rental_yield_percent = Column(Float, nullable=True)
    underwriting_deal_score = Column(Integer, nullable=True)  # 1-100, this agent's own score — see its docstring for why it's distinct from app.deal_score
    underwriting_status = Column(String(100), nullable=True)  # "validated" | "risk:overpriced" | "risk:below_hurdle_roi" | "risk:overpriced,below_hurdle_roi" | "no_benchmark" | "insufficient_data"
    underwriting_confidence_tag = Column(String(50), nullable=True)  # "High Potential Flip" | "Buy & Hold Yield" | None
    underwriting_updated_at = Column(DateTime, nullable=True)  # when the above was last computed — deliberately surfaced so it's never mistaken for a live number

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
