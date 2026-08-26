"""
Pydantic (v2) schemas used for request validation and response serialization.
"""
import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, computed_field, field_validator

from app.models import PIPELINE_STATUSES


# ---------------------------------------------------------------------------
# Property
# ---------------------------------------------------------------------------

class PropertyBase(BaseModel):
    title: str
    district: str
    address: Optional[str] = None
    size_sqm: Optional[float] = None
    rooms: Optional[float] = None
    balcony_sqm: Optional[float] = None
    price_huf: Optional[float] = None
    price_eur: Optional[float] = None
    price_per_sqm: Optional[float] = None
    url: Optional[str] = None
    condition: Optional[str] = None
    images: Optional[List[str]] = None
    portal: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    is_favorite: bool = False
    pipeline_status: str = "new"

    @field_validator("pipeline_status")
    @classmethod
    def _validate_pipeline_status(cls, value: str) -> str:
        if value not in PIPELINE_STATUSES:
            raise ValueError(f"pipeline_status must be one of {PIPELINE_STATUSES}, got {value!r}")
        return value


class PropertyCreate(PropertyBase):
    """Payload for POST /properties. price_per_sqm is auto-computed if omitted."""
    pass


class PropertyUpdate(BaseModel):
    """All fields optional -> used for PATCH /properties/{id}."""
    title: Optional[str] = None
    district: Optional[str] = None
    address: Optional[str] = None
    size_sqm: Optional[float] = None
    rooms: Optional[float] = None
    balcony_sqm: Optional[float] = None
    price_huf: Optional[float] = None
    price_eur: Optional[float] = None
    price_per_sqm: Optional[float] = None
    url: Optional[str] = None
    condition: Optional[str] = None
    images: Optional[List[str]] = None
    portal: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    is_favorite: Optional[bool] = None
    pipeline_status: Optional[str] = None

    @field_validator("pipeline_status")
    @classmethod
    def _validate_pipeline_status(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and value not in PIPELINE_STATUSES:
            raise ValueError(f"pipeline_status must be one of {PIPELINE_STATUSES}, got {value!r}")
        return value


class PropertyOut(PropertyBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime.datetime

    # Read-only — set by app/services/valuation_agent.py, never by a client.
    # Not present on PropertyCreate/PropertyUpdate above, deliberately.
    underwriting_market_value_huf: Optional[float] = None
    underwriting_renovation_cost_huf: Optional[float] = None
    underwriting_total_investment_huf: Optional[float] = None
    underwriting_net_profit_huf: Optional[float] = None
    underwriting_flip_roi_percent: Optional[float] = None
    underwriting_rental_yield_percent: Optional[float] = None
    underwriting_deal_score: Optional[int] = None
    underwriting_status: Optional[str] = None
    underwriting_confidence_tag: Optional[str] = None
    underwriting_updated_at: Optional[datetime.datetime] = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def source_url(self) -> Optional[str]:
        """Alias for `url` — the exact source-portal listing page this Property was scraped from."""
        return self.url


# ---------------------------------------------------------------------------
# DistrictBenchmark
# ---------------------------------------------------------------------------

class DistrictBenchmarkBase(BaseModel):
    avg_price_sqm_raw: Optional[float] = None
    avg_price_sqm_renovated: Optional[float] = None
    avg_rent_huf_sqm: Optional[float] = None
    centroid_lat: Optional[float] = None
    centroid_lng: Optional[float] = None


class DistrictBenchmarkCreate(DistrictBenchmarkBase):
    district_number: int


class DistrictBenchmarkUpdate(DistrictBenchmarkBase):
    """All fields optional -> used for PATCH /district-benchmarks/{district_number}."""
    pass


class DistrictBenchmarkOut(DistrictBenchmarkBase):
    model_config = ConfigDict(from_attributes=True)

    district_number: int
    updated_at: datetime.datetime


# ---------------------------------------------------------------------------
# Access passcode (see app/access_control.py)
# ---------------------------------------------------------------------------

class PasscodeVerify(BaseModel):
    passcode: str
