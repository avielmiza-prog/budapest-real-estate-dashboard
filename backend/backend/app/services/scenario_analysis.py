"""
Conservative / Base / Optimistic exit-scenario sensitivity analysis for a
scraped Property — built on the exact same formula and rate constants as
app.services.valuation_agent's automated underwriting agent (condition +
building-type adjusted renovation cost from app.renovation_estimator, and
the 4% acquisition tax / 1.5% legal-closing / 3% broker fee sourced from
app.analyzer), so a scenario's "base" case always matches the persisted
underwriting numbers exactly.

Computed live on every /deals request rather than persisted — unlike the
underwriting agent's verdict, these are a "what if" toggle the frontend lets
an investor flip through interactively, not a point-in-time committee memo.

Three scenarios:
  - conservative: exit price marked down 5%, renovation cost marked up 15%
    — a downside case for a renovation running over budget in a softening
    market.
  - base: valuation_agent's own numbers, unchanged.
  - optimistic: exit price marked up to the district's 85th-percentile
    recently-scraped renovated HUF/sqm (DistrictBenchmark.p85_price_sqm_
    renovated — see app.services.stats_service), rather than the median
    avg_price_sqm_renovated used in the base case. Falls back to
    avg_price_sqm_renovated * OPTIMISTIC_FALLBACK_MULTIPLIER when no p85
    figure is on file yet (e.g. too few live samples for that district).
"""
from dataclasses import dataclass
from typing import Optional

from app import models
from app.analyzer import BROKER_FEE_RATE, LEGAL_NOTARY_FEE_RATE, PROPERTY_TRANSFER_TAX_RATE
from app.renovation_estimator import estimate_adjusted_renovation_cost_huf_per_sqm

CONSERVATIVE_EXIT_PRICE_MULTIPLIER = 0.95  # exit price -5%
CONSERVATIVE_RENOVATION_COST_MULTIPLIER = 1.15  # renovation cost +15%

# Used only when a district has no live p85_price_sqm_renovated yet (too few
# recent samples — see stats_service.MIN_LIVE_SAMPLES) — a documented,
# honest approximation of "a strong sale within this district", not a
# fabricated percentile.
OPTIMISTIC_FALLBACK_MULTIPLIER = 1.10


@dataclass
class ScenarioResult:
    exit_price_huf: float
    renovation_cost_huf: float
    total_investment_huf: float
    net_profit_huf: float
    roi_percent: Optional[float]

    def to_dict(self) -> dict:
        return {
            "exit_price_huf": round(self.exit_price_huf, 2),
            "renovation_cost_huf": round(self.renovation_cost_huf, 2),
            "total_investment_huf": round(self.total_investment_huf, 2),
            "net_profit_huf": round(self.net_profit_huf, 2),
            "roi_percent": round(self.roi_percent, 2) if self.roi_percent is not None else None,
        }


def _compute_scenario(
    prop: models.Property, exit_price_per_sqm: float, renovation_cost_multiplier: float
) -> ScenarioResult:
    base_reno_per_sqm = estimate_adjusted_renovation_cost_huf_per_sqm(
        prop.condition, prop.building_type, prop.ceiling_height_m
    )
    renovation_cost_huf = base_reno_per_sqm * prop.size_sqm * renovation_cost_multiplier

    acquisition_tax_huf = prop.price_huf * PROPERTY_TRANSFER_TAX_RATE
    legal_closing_huf = prop.price_huf * LEGAL_NOTARY_FEE_RATE
    total_investment_huf = prop.price_huf + renovation_cost_huf + acquisition_tax_huf + legal_closing_huf

    exit_price_huf = prop.size_sqm * exit_price_per_sqm
    broker_fee_huf = exit_price_huf * BROKER_FEE_RATE
    net_profit_huf = exit_price_huf - total_investment_huf - broker_fee_huf
    roi_percent = (net_profit_huf / total_investment_huf * 100) if total_investment_huf > 0 else None

    return ScenarioResult(
        exit_price_huf=exit_price_huf,
        renovation_cost_huf=renovation_cost_huf,
        total_investment_huf=total_investment_huf,
        net_profit_huf=net_profit_huf,
        roi_percent=roi_percent,
    )


def compute_scenarios(prop: models.Property, benchmark: Optional[models.DistrictBenchmark]) -> Optional[dict]:
    """
    {"conservative": {...}, "base": {...}, "optimistic": {...}}, each a
    ScenarioResult.to_dict(), or None if there isn't enough data (missing
    size/price, or no renovated-price benchmark for this district yet) to
    compute any of them.
    """
    if not prop.size_sqm or prop.size_sqm <= 0 or not prop.price_huf or prop.price_huf <= 0:
        return None
    if benchmark is None or benchmark.avg_price_sqm_renovated is None:
        return None

    base_exit_per_sqm = benchmark.avg_price_sqm_renovated
    optimistic_exit_per_sqm = (
        benchmark.p85_price_sqm_renovated
        if benchmark.p85_price_sqm_renovated is not None
        else base_exit_per_sqm * OPTIMISTIC_FALLBACK_MULTIPLIER
    )

    return {
        "conservative": _compute_scenario(
            prop,
            base_exit_per_sqm * CONSERVATIVE_EXIT_PRICE_MULTIPLIER,
            CONSERVATIVE_RENOVATION_COST_MULTIPLIER,
        ).to_dict(),
        "base": _compute_scenario(prop, base_exit_per_sqm, 1.0).to_dict(),
        "optimistic": _compute_scenario(prop, optimistic_exit_per_sqm, 1.0).to_dict(),
    }
