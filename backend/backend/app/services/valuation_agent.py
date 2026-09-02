"""
Automated Market Valuation, Renovation & Underwriting Verification Agent.

This is a distinct layer from app/analyzer.py's interactive Light/Medium/
Full renovation-tier tool (unchanged — it still powers the deal detail
modal's slider and PDF exports, computed live on every request). This
agent instead:
  - estimates renovation cost from the listing's own condition text
    (keyword-matched — see app.condition_classifier.classify_condition())
    rather than a fixed preset the user picks,
  - runs once per scrape (scraper/pipeline.py calls validate_and_underwrite()
    from store_and_analyze()) and PERSISTS its verdict on the Property row
    (underwriting_* columns — see app/models.py), rather than recomputing
    live on every request.

That persistence is a deliberate tradeoff: the numbers reflect market
conditions "as of the last scan" (underwriting_updated_at), not the current
instant — like a real investment-committee memo, not a live ticking
dashboard figure. Re-scraping a listing (or re-running the underwriting
pass) refreshes it; a district-benchmark edit alone does not, until the
next scan touches that listing.

The benchmark this agent reads (via crud.get_district_benchmark, below) is
itself kept live by app/services/stats_service.py's
update_district_benchmarks() — a statistical median computed from recently
scraped listings in that district, falling back to the documented
seed_data.json baseline only when too few live samples exist yet (see that
module's docstring). This module doesn't call it directly; it just trusts
whatever DistrictBenchmark.avg_price_sqm_renovated currently holds, same as
before that function existed.

Formulas (all in HUF unless noted; rate constants — ACQUISITION_TAX_RATE,
LEGAL_CLOSING_RATE, BROKER_FEE_RATE — are imported from app.analyzer, the
platform's single source of truth for these fees, not redefined here):
  Renovation Cost      = size_sqm * condition-and-building-type-adjusted
                          HUF/sqm estimate (see app.renovation_estimator,
                          which layers app.building_classifier's Polgári/
                          Panelház/ceiling-height multiplier on top of
                          app.condition_classifier's condition-based baseline)
  Total Investment     = Purchase Price + Renovation Cost
                          + Purchase Price * 4%  (acquisition/transfer tax, "illeték")
                          + Purchase Price * 1.5% (legal/notary/closing costs)
  Projected Exit Price = size_sqm * district's turnkey (renovated) median HUF/sqm
  Net Flip Profit       = Exit Price - Total Investment - Exit Price * 3% (sales/broker fee)
  Flip Net ROI %        = Net Flip Profit / Total Investment * 100
  Rental Yield %         = (district avg monthly rent HUF/sqm * size_sqm * 12) / Total Investment * 100
  Deal Score (0-100)    = 50% discount-vs-benchmark + 30% flip ROI + 20% district liquidity
                          (same 50/30/20 shape as app/deal_score.py's live
                          score, for a consistent "how is this weighted"
                          story across the app — liquidity swapped in for
                          that module's layout-efficiency factor, since this
                          agent is specifically about deal *viability*, not
                          floorplan quality)
"""
import datetime
import logging
import math
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from app import analyzer, crud, models
from app.analyzer import BROKER_FEE_RATE, LEGAL_NOTARY_FEE_RATE as LEGAL_CLOSING_RATE, PROPERTY_TRANSFER_TAX_RATE as ACQUISITION_TAX_RATE
from app.renovation_estimator import estimate_adjusted_renovation_cost_huf_per_sqm

logger = logging.getLogger(__name__)

MIN_HURDLE_ROI_PERCENT = 10.0  # flip ROI below this -> "risk:below_hurdle_roi"

HIGH_POTENTIAL_FLIP_ROI_PERCENT = 20.0  # confidence tag threshold
BUY_AND_HOLD_YIELD_PERCENT = 5.0  # confidence tag threshold

DEAL_SCORE_DISCOUNT_WEIGHT = 0.50
DEAL_SCORE_ROI_WEIGHT = 0.30
DEAL_SCORE_LIQUIDITY_WEIGHT = 0.20

# Clamp ranges before rescaling to 0-100 — same rationale as app/deal_score.py:
# without clamping, one wildly discounted/high-ROI outlier compresses every
# other property's score toward the middle.
_DISCOUNT_CLAMP_RANGE_PERCENT = (-20.0, 40.0)
_ROI_CLAMP_RANGE_PERCENT = (-10.0, 30.0)

_BUDAPEST_CENTER = (47.4979, 19.0402)  # Deák Ferenc tér


def _district_liquidity_score(benchmark: Optional[models.DistrictBenchmark]) -> float:
    """
    0-100 proxy for "district liquidity" (how quickly/reliably a flip in
    that district actually sells). No real transaction-volume/days-on-
    market dataset is available for Budapest districts here, so this
    approximates it from geographic centrality — distance from Deák Ferenc
    tér using the district centroid coordinates already on file — which
    tracks reasonably well with transaction velocity in practice. This is
    an honest, documented approximation, not a fabricated "real" figure;
    treat it as a rough prior, not a market-research number.
    """
    if benchmark is None or benchmark.centroid_lat is None or benchmark.centroid_lng is None:
        return 50.0  # neutral fallback — no coordinates on file for this district
    center_lat, center_lng = _BUDAPEST_CENTER
    dx = (benchmark.centroid_lng - center_lng) * 111.320 * math.cos(math.radians(center_lat))
    dy = (benchmark.centroid_lat - center_lat) * 110.574
    distance_km = math.hypot(dx, dy)
    # 0km (dead center) -> 100; drops off ~7.5 pts/km, floored at 10 for the far outskirts.
    return max(10.0, 100.0 - distance_km * 7.5)


def _clamp_and_scale(value: Optional[float], low: float, high: float) -> float:
    if value is None:
        return 50.0  # missing signal falls back to neutral rather than dragging the weighted sum to 0
    clamped = max(low, min(high, value))
    if high == low:
        return 50.0
    return (clamped - low) / (high - low) * 100


def _compute_deal_score(discount_percent: Optional[float], flip_roi_percent: Optional[float], liquidity_score: float) -> Optional[int]:
    if discount_percent is None and flip_roi_percent is None:
        return None
    discount_score = _clamp_and_scale(discount_percent, *_DISCOUNT_CLAMP_RANGE_PERCENT)
    roi_score = _clamp_and_scale(flip_roi_percent, *_ROI_CLAMP_RANGE_PERCENT)
    score = (
        DEAL_SCORE_DISCOUNT_WEIGHT * discount_score
        + DEAL_SCORE_ROI_WEIGHT * roi_score
        + DEAL_SCORE_LIQUIDITY_WEIGHT * liquidity_score
    )
    return round(score)


@dataclass
class UnderwritingResult:
    estimated_market_value_huf: Optional[float]  # projected turnkey exit price
    renovation_cost_huf: Optional[float]
    total_investment_huf: Optional[float]
    net_profit_huf: Optional[float]
    flip_roi_percent: Optional[float]
    rental_yield_percent: Optional[float]
    deal_score: Optional[int]
    status: str
    confidence_tag: Optional[str]

    def to_dict(self) -> dict:
        return {
            "estimated_market_value_huf": self.estimated_market_value_huf,
            "renovation_cost_huf": self.renovation_cost_huf,
            "total_investment_huf": self.total_investment_huf,
            "net_profit_huf": self.net_profit_huf,
            "flip_roi_percent": self.flip_roi_percent,
            "rental_yield_percent": self.rental_yield_percent,
            "deal_score": self.deal_score,
            "status": self.status,
            "confidence_tag": self.confidence_tag,
        }


def validate_and_underwrite(prop: models.Property, db: Session) -> UnderwritingResult:
    """
    The agent's single entrypoint: given a Property row (already in the DB —
    call after crud.upsert_property_by_url, not before), looks up its
    district benchmark and returns the full underwriting verdict. Does not
    persist anything itself — see persist_underwriting_result() /
    scraper/pipeline.py, which calls both together after every scrape.
    """
    if not prop.size_sqm or prop.size_sqm <= 0 or not prop.price_huf or prop.price_huf <= 0:
        return UnderwritingResult(None, None, None, None, None, None, None, "insufficient_data", None)

    reno_cost_per_sqm = estimate_adjusted_renovation_cost_huf_per_sqm(
        prop.condition, prop.building_type, prop.ceiling_height_m
    )
    renovation_cost_huf = reno_cost_per_sqm * prop.size_sqm

    acquisition_tax_huf = prop.price_huf * ACQUISITION_TAX_RATE
    legal_closing_huf = prop.price_huf * LEGAL_CLOSING_RATE
    total_investment_huf = prop.price_huf + renovation_cost_huf + acquisition_tax_huf + legal_closing_huf

    benchmark: Optional[models.DistrictBenchmark] = None
    try:
        district_number = analyzer.parse_district_number(prop.district)
        benchmark = crud.get_district_benchmark(db, district_number)
    except ValueError:
        pass  # unparseable district — fall through with benchmark=None

    if benchmark is None or benchmark.avg_price_sqm_renovated is None:
        return UnderwritingResult(
            estimated_market_value_huf=None,
            renovation_cost_huf=round(renovation_cost_huf, 2),
            total_investment_huf=round(total_investment_huf, 2),
            net_profit_huf=None,
            rental_yield_percent=None,
            flip_roi_percent=None,
            deal_score=None,
            status="no_benchmark",
            confidence_tag=None,
        )

    exit_price_huf = prop.size_sqm * benchmark.avg_price_sqm_renovated
    broker_fee_huf = exit_price_huf * BROKER_FEE_RATE
    net_profit_huf = exit_price_huf - total_investment_huf - broker_fee_huf
    flip_roi_percent = (net_profit_huf / total_investment_huf * 100) if total_investment_huf > 0 else None

    rental_yield_percent = None
    if benchmark.avg_rent_huf_sqm and total_investment_huf > 0:
        annual_rent_huf = benchmark.avg_rent_huf_sqm * prop.size_sqm * 12
        rental_yield_percent = annual_rent_huf / total_investment_huf * 100

    asking_price_per_sqm = prop.price_huf / prop.size_sqm
    discount_percent = (
        (benchmark.avg_price_sqm_renovated - asking_price_per_sqm) / benchmark.avg_price_sqm_renovated * 100
    )

    liquidity_score = _district_liquidity_score(benchmark)
    deal_score = _compute_deal_score(discount_percent, flip_roi_percent, liquidity_score)

    risk_flags = []
    if discount_percent < 0:  # asking price/sqm is above the district's turnkey median
        risk_flags.append("overpriced")
    if flip_roi_percent is not None and flip_roi_percent < MIN_HURDLE_ROI_PERCENT:
        risk_flags.append("below_hurdle_roi")
    status = "validated" if not risk_flags else "risk:" + ",".join(risk_flags)

    confidence_tag = None
    if flip_roi_percent is not None and flip_roi_percent >= HIGH_POTENTIAL_FLIP_ROI_PERCENT:
        confidence_tag = "High Potential Flip"
    elif rental_yield_percent is not None and rental_yield_percent >= BUY_AND_HOLD_YIELD_PERCENT:
        confidence_tag = "Buy & Hold Yield"

    return UnderwritingResult(
        estimated_market_value_huf=round(exit_price_huf, 2),
        renovation_cost_huf=round(renovation_cost_huf, 2),
        total_investment_huf=round(total_investment_huf, 2),
        net_profit_huf=round(net_profit_huf, 2),
        flip_roi_percent=round(flip_roi_percent, 2) if flip_roi_percent is not None else None,
        rental_yield_percent=round(rental_yield_percent, 2) if rental_yield_percent is not None else None,
        deal_score=deal_score,
        status=status,
        confidence_tag=confidence_tag,
    )


def persist_underwriting_result(db: Session, property_id: int, result: UnderwritingResult) -> Optional[models.Property]:
    """Writes an UnderwritingResult onto its Property row's underwriting_* columns and commits."""
    prop = crud.get_property(db, property_id)
    if prop is None:
        return None
    prop.underwriting_market_value_huf = result.estimated_market_value_huf
    prop.underwriting_renovation_cost_huf = result.renovation_cost_huf
    prop.underwriting_total_investment_huf = result.total_investment_huf
    prop.underwriting_net_profit_huf = result.net_profit_huf
    prop.underwriting_flip_roi_percent = result.flip_roi_percent
    prop.underwriting_rental_yield_percent = result.rental_yield_percent
    prop.underwriting_deal_score = result.deal_score
    prop.underwriting_status = result.status
    prop.underwriting_confidence_tag = result.confidence_tag
    prop.underwriting_updated_at = datetime.datetime.utcnow()
    db.commit()
    db.refresh(prop)
    return prop


def validate_and_underwrite_and_persist(db: Session, property_id: int) -> Optional[UnderwritingResult]:
    """Convenience wrapper: fetch -> validate_and_underwrite -> persist, in one call. Used by scraper/pipeline.py."""
    prop = crud.get_property(db, property_id)
    if prop is None:
        return None
    result = validate_and_underwrite(prop, db)
    persist_underwriting_result(db, property_id, result)
    return result
