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
    notes = Column(Text, nullable=True)  # free-text investor notes on a shortlisted deal, editable via PATCH
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False, index=True)

    # Freshness tracking. last_seen_at is bumped every time a scan sees the
    # listing on a portal's search results (even when its detail page is
    # not re-fetched). A listing not seen for app.dashboard.STALE_AFTER_DAYS
    # is treated as sold/withdrawn and hidden from the deals list.
    # Nullable on purpose: rows created before this column existed fall
    # back to created_at.
    last_seen_at = Column(DateTime, nullable=True, index=True)
    # Previous asking price, kept when a re-scan finds a different price, so
    # the UI can show "price dropped 8%" (a strong negotiation signal).
    previous_price_huf = Column(Float, nullable=True)
    # Listing details used by app.listing_assessment's red-flag checks.
    description = Column(Text, nullable=True)
    floor = Column(String(40), nullable=True)
    has_elevator = Column(Boolean, nullable=True)
    price_changed_at = Column(DateTime, nullable=True)

    # Sub-market precision fields — extracted from listing text by
    # app/building_classifier.py and app/sub_district.py (see their
    # docstrings). All nullable/best-effort: a listing whose text doesn't
    # match any known keyword simply leaves these unset rather than guessing.
    building_type = Column(String(40), nullable=True)  # "Brick Classical (Polgári)" | "Panel Block (Panelház)" | "New Build (Új építés)"
    ceiling_height_m = Column(Float, nullable=True)  # parsed from listing text, e.g. "3,2 m belmagasság"
    sub_district = Column(String(60), nullable=True)  # micro-neighborhood, e.g. "Újlipótváros", "Belső-Erzsébetváros"

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
    avg_price_sqm_raw = Column(Float, nullable=True)  # median HUF/sqm for unrenovated ("raw") condition — live or fallback, see source_raw
    avg_price_sqm_renovated = Column(Float, nullable=True)  # median HUF/sqm for renovated condition — live or fallback, see source_renovated
    avg_rent_huf_sqm = Column(Float, nullable=True)  # avg monthly HUF/sqm rent, powers rental yield
    centroid_lat = Column(Float, nullable=True)  # map fallback pin + geocoding fallback
    centroid_lng = Column(Float, nullable=True)

    # Set by app/services/stats_service.py's update_district_benchmarks() —
    # how many live scraped listings (within its rolling window) the
    # avg_price_sqm_raw/renovated figure above is actually based on, and
    # whether that figure is a live-computed median ("live") or the
    # documented seed_data.json baseline ("fallback", used whenever a
    # district/category has fewer than stats_service.MIN_LIVE_SAMPLES
    # samples). Both null until update_district_benchmarks() has run at
    # least once (e.g. a row created by hand via POST /district-benchmarks).
    sample_count_raw = Column(Integer, nullable=True)
    sample_count_renovated = Column(Integer, nullable=True)
    source_raw = Column(String(20), nullable=True)  # "live" | "fallback"
    source_renovated = Column(String(20), nullable=True)  # "live" | "fallback"

    # 85th percentile of recently-scraped renovated HUF/sqm listings in this
    # district — the "Optimistic" exit-price basis for
    # app/services/scenario_analysis.py. Falls back to
    # avg_price_sqm_renovated * OPTIMISTIC_FALLBACK_MULTIPLIER (see that
    # module) when too few live samples exist for a real percentile. Set by
    # the same update_district_benchmarks() pass as the fields above.
    p85_price_sqm_renovated = Column(Float, nullable=True)

    updated_at = Column(
        DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<DistrictBenchmark district={self.district_number}>"


class BuildingTypeBenchmark(Base):
    """
    Median HUF/sqm segmented by district AND building type (Polgári /
    Panelház / Új építés) — a finer-grained cut than DistrictBenchmark's
    district-only medians, computed by
    app/services/stats_service.py::update_building_type_benchmarks().
    Purely informational (surfaced via GET /building-type-benchmarks and
    attached to each /deals item) — the exit-price benchmark used in the
    actual ROI math stays DistrictBenchmark.avg_price_sqm_renovated, so a
    building type with too few samples never silently changes anyone's ROI.
    """

    __tablename__ = "building_type_benchmarks"

    district_number = Column(Integer, primary_key=True)
    building_type = Column(String(40), primary_key=True)
    avg_price_sqm = Column(Float, nullable=True)  # trimmed median HUF/sqm for this district x building type
    sample_count = Column(Integer, nullable=False, default=0)
    updated_at = Column(
        DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow, nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<BuildingTypeBenchmark district={self.district_number} type={self.building_type!r}>"
