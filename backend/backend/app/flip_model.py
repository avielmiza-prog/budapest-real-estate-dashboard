"""
Realistic flip model: the single source of truth for "is this a deal?".

Why this module exists (the problems it fixes in the older math):

1. The old "best tier" picked the cheapest renovation (Light, 250 EUR/sqm)
   but still assumed the fully-renovated exit price. Light always won, so
   every ROI on the dashboard was inflated. Here the renovation scope comes
   from the listing's own condition: a flat that needs work gets a full
   renovation budget, an average flat a medium one, an already-renovated
   flat only a pre-sale refresh.
2. The exit price was the district median of *asking* prices of every
   "renovated or new" listing. New builds sell 30-60% above renovated
   second-hand flats in Budapest (2026: ~1.8-2.0M HUF/sqm new vs ~1.37M
   used brick), so mixing them in inflated exits. stats_service now
   excludes new builds from the renovated median, and this module applies
   an asking-to-sale discount on top (asking prices are not sale prices).
3. Panel flats were valued at the district's brick median. They sell
   lower; the exit is now scaled by the building-type median when there are
   enough live samples, otherwise by a documented static factor.
4. Costs that were missing: 15% personal income tax (SZJA) on the gain when
   selling within a year of purchase (NAV: 100% of the gain is taxable in
   the year of acquisition and the following year), holding costs while
   the flat sits empty (common charges + utilities), and a contingency on
   the renovation budget instead of a flat 5% on the purchase price.
5. No answer to the question an investor actually asks: "how much can I
   offer?". max_offer_price_huf solves for the purchase price that still
   hits the target ROI.

Everything here is pure math on plain numbers: no DB access. Callers pass
in the benchmark numbers they already loaded (see app.dashboard).
"""
from dataclasses import asdict, dataclass
from typing import Optional

from app.analyzer import (
    BALCONY_WEIGHT,
    BROKER_FEE_RATE,
    LEGAL_NOTARY_FEE_RATE,
    PROPERTY_TRANSFER_TAX_RATE,
)
from app.building_classifier import (
    BUILDING_TYPE_BRICK_CLASSICAL,
    BUILDING_TYPE_NEW_BUILD,
    BUILDING_TYPE_PANEL_BLOCK,
    renovation_cost_multiplier,
)
from app.condition_classifier import (
    CONDITION_AVERAGE,
    CONDITION_NEEDS_RENOVATION,
    CONDITION_NEW_CONSTRUCTION,
    CONDITION_RENOVATED,
    classify_condition_tag,
)

# ---------------------------------------------------------------------------
# Assumptions (all tunable; each is shown to the user in the deal breakdown)
# ---------------------------------------------------------------------------

# Renovation budget, HUF per sqm, by scope. 2026 Budapest market: a basic
# refresh of a 50-60 sqm flat costs 5-8M HUF, a medium one 9-12M, a full
# renovation including wiring/plumbing/heating more (economx, Aug 2025;
# bankmonitor quotes 200-400k HUF/sqm for a real renovation).
RENOVATION_SCOPE_HUF_PER_SQM = {
    "full": 300_000,
    "medium": 170_000,
    "refresh": 30_000,
    "none": 0,
}

SCOPE_BY_CONDITION = {
    CONDITION_NEEDS_RENOVATION: "full",
    CONDITION_AVERAGE: "medium",
    CONDITION_RENOVATED: "refresh",
    CONDITION_NEW_CONSTRUCTION: "none",
}

# Months from signing the purchase to receiving the sale money.
HOLDING_MONTHS_BY_SCOPE = {"full": 9, "medium": 7, "refresh": 4, "none": 4}

# Renovation overruns are the norm, not the exception.
RENOVATION_CONTINGENCY_RATE = 0.15

# Asking prices are not sale prices. Exit comps are medians of asking
# prices, so the projected sale price is discounted by this much.
ASKING_TO_SALE_DISCOUNT = 0.05

# Monthly cost of holding an empty flat: common charges (közös költség)
# per sqm plus a flat utilities/insurance amount.
HOLDING_COST_HUF_PER_SQM_MONTH = 450
HOLDING_COST_FIXED_HUF_MONTH = 25_000

# Personal income tax on the gain from selling a flat bought the same or
# the previous year (NAV). Deductible: purchase price, purchase costs,
# documented renovation costs, sale costs.
GAINS_TAX_RATE = 0.15

# Building-type exit factors vs. the district's renovated median, used only
# when there are not enough live samples for a real per-type median.
STATIC_BUILDING_TYPE_FACTOR = {
    BUILDING_TYPE_PANEL_BLOCK: 0.85,
    BUILDING_TYPE_BRICK_CLASSICAL: 1.0,
    BUILDING_TYPE_NEW_BUILD: 1.0,
}
BUILDING_TYPE_FACTOR_CLAMP = (0.70, 1.20)
MIN_BUILDING_TYPE_SAMPLES = 5

# Outside this size range district flat medians are not a fair comparison.
MIN_TYPICAL_FLAT_SQM = 18
MAX_TYPICAL_FLAT_SQM = 150

# Verdict thresholds on net ROI after tax.
TARGET_ROI_PERCENT = 15.0
CONSIDER_ROI_PERCENT = 8.0


@dataclass
class FlipResult:
    condition_tag: str
    scope: str
    usable_area_sqm: float
    purchase_price_huf: float
    purchase_costs_huf: float
    renovation_cost_huf: float
    contingency_huf: float
    holding_months: int
    holding_cost_huf: float
    total_cash_needed_huf: float
    exit_price_sqm_huf: float
    exit_price_huf: float
    sale_costs_huf: float
    profit_before_tax_huf: float
    gains_tax_huf: float
    net_profit_huf: float
    roi_percent: float
    annualized_roi_percent: float
    max_offer_price_huf: Optional[float]
    offer_gap_percent: Optional[float]  # how far the asking price is above (+) / below (-) the max offer
    discount_vs_market_percent: Optional[float]  # asking HUF/sqm vs. same-condition district median
    verdict: str  # "buy" | "consider" | "skip"
    confidence: str  # "high" | "medium" | "low"
    confidence_reasons: list  # codes: fallback_benchmark | no_condition | no_building_type | above_renovated_market
    exit_basis: str  # human-readable: where exit_price_sqm_huf came from

    def to_dict(self) -> dict:
        d = asdict(self)
        for key, value in d.items():
            if isinstance(value, float):
                d[key] = round(value, 2)
        return d


def _scope_for(condition_tag: str) -> str:
    return SCOPE_BY_CONDITION.get(condition_tag, "medium")


def _building_type_factor(
    building_type: Optional[str],
    district_renovated_median: float,
    building_type_median: Optional[float],
    building_type_samples: int,
    district_all_median: Optional[float],
) -> tuple:
    """(factor, basis text). Live per-type median beats the static factor."""
    if (
        building_type
        and building_type_median
        and building_type_samples >= MIN_BUILDING_TYPE_SAMPLES
        and district_all_median
    ):
        low, high = BUILDING_TYPE_FACTOR_CLAMP
        factor = max(low, min(high, building_type_median / district_all_median))
        return factor, f"live {building_type} median ({building_type_samples} listings)"
    if building_type in STATIC_BUILDING_TYPE_FACTOR:
        factor = STATIC_BUILDING_TYPE_FACTOR[building_type]
        if factor != 1.0:
            return factor, f"static {building_type} factor x{factor:.2f}"
    return 1.0, "district renovated median"


def _run(
    purchase_price_huf: float,
    usable_area_sqm: float,
    reno_per_sqm: float,
    holding_months: int,
    exit_price_huf: float,
) -> dict:
    purchase_costs = purchase_price_huf * (PROPERTY_TRANSFER_TAX_RATE + LEGAL_NOTARY_FEE_RATE)
    renovation = reno_per_sqm * usable_area_sqm
    contingency = renovation * RENOVATION_CONTINGENCY_RATE
    holding = holding_months * (
        HOLDING_COST_HUF_PER_SQM_MONTH * usable_area_sqm + HOLDING_COST_FIXED_HUF_MONTH
    )
    total_cash = purchase_price_huf + purchase_costs + renovation + contingency + holding
    sale_costs = exit_price_huf * BROKER_FEE_RATE
    profit_before_tax = exit_price_huf - sale_costs - total_cash
    # Holding costs (common charges/utilities) are not deductible for SZJA.
    taxable_gain = exit_price_huf - sale_costs - (total_cash - holding)
    gains_tax = max(0.0, taxable_gain) * GAINS_TAX_RATE
    net_profit = profit_before_tax - gains_tax
    roi = net_profit / total_cash * 100 if total_cash > 0 else 0.0
    return {
        "purchase_costs": purchase_costs,
        "renovation": renovation,
        "contingency": contingency,
        "holding": holding,
        "total_cash": total_cash,
        "sale_costs": sale_costs,
        "profit_before_tax": profit_before_tax,
        "gains_tax": gains_tax,
        "net_profit": net_profit,
        "roi": roi,
    }


def _max_offer(
    usable_area_sqm: float, reno_per_sqm: float, holding_months: int, exit_price_huf: float, target_roi: float
) -> Optional[float]:
    """Highest purchase price that still reaches target_roi. ROI falls monotonically with price -> bisection."""
    low, high = 0.0, exit_price_huf
    if _run(low, usable_area_sqm, reno_per_sqm, holding_months, exit_price_huf)["roi"] < target_roi:
        return None  # even a free flat would not reach the target (renovation too expensive vs. exit)
    for _ in range(60):
        mid = (low + high) / 2
        if _run(mid, usable_area_sqm, reno_per_sqm, holding_months, exit_price_huf)["roi"] >= target_roi:
            low = mid
        else:
            high = mid
    return low


def evaluate_flip(
    *,
    size_sqm: float,
    price_huf: float,
    condition: Optional[str],
    district_renovated_median_sqm: float,
    district_raw_median_sqm: Optional[float] = None,
    balcony_sqm: Optional[float] = None,
    building_type: Optional[str] = None,
    ceiling_height_m: Optional[float] = None,
    building_type_median_sqm: Optional[float] = None,
    building_type_samples: int = 0,
    district_all_median_sqm: Optional[float] = None,
    renovated_sample_count: Optional[int] = None,
    renovated_source: Optional[str] = None,
    target_roi_percent: float = TARGET_ROI_PERCENT,
) -> FlipResult:
    if size_sqm <= 0 or price_huf <= 0:
        raise ValueError("size_sqm and price_huf must be > 0")

    condition_tag = classify_condition_tag(condition)
    scope = _scope_for(condition_tag)
    usable_area_sqm = size_sqm + (balcony_sqm or 0) * BALCONY_WEIGHT
    reno_per_sqm = RENOVATION_SCOPE_HUF_PER_SQM[scope] * renovation_cost_multiplier(building_type, ceiling_height_m)
    holding_months = HOLDING_MONTHS_BY_SCOPE[scope]

    factor, exit_basis = _building_type_factor(
        building_type,
        district_renovated_median_sqm,
        building_type_median_sqm,
        building_type_samples,
        district_all_median_sqm,
    )
    exit_price_sqm = district_renovated_median_sqm * factor * (1 - ASKING_TO_SALE_DISCOUNT)
    exit_price = exit_price_sqm * usable_area_sqm

    r = _run(price_huf, usable_area_sqm, reno_per_sqm, holding_months, exit_price)
    annualized = r["roi"] * 12 / holding_months if holding_months else r["roi"]

    max_offer = _max_offer(usable_area_sqm, reno_per_sqm, holding_months, exit_price, target_roi_percent)
    offer_gap = (price_huf - max_offer) / max_offer * 100 if max_offer else None

    # Discount vs. the market for flats in the SAME condition (a raw flat
    # compared to the raw median, a renovated one to the renovated median).
    price_sqm = price_huf / size_sqm
    same_condition_median = (
        district_raw_median_sqm
        if scope in ("full", "medium") and district_raw_median_sqm
        else district_renovated_median_sqm
    )
    discount = (
        (same_condition_median - price_sqm) / same_condition_median * 100 if same_condition_median else None
    )

    reasons = []
    if renovated_source == "fallback" or (renovated_sample_count or 0) < 10:
        reasons.append("fallback_benchmark")  # fewer than 10 live renovated listings in the district
    if condition is None or not condition.strip():
        reasons.append("no_condition")  # condition not stated; assumed average
    if building_type is None:
        reasons.append("no_building_type")
    if exit_price_sqm < price_sqm and scope != "none":
        reasons.append("above_renovated_market")  # asking HUF/sqm already above the renovated exit
    unusual_size = size_sqm > MAX_TYPICAL_FLAT_SQM or size_sqm < MIN_TYPICAL_FLAT_SQM
    if unusual_size:
        # Very large "flats" in outer districts are usually family houses or
        # whole buildings; district flat medians don't apply to them.
        reasons.append("unusual_size")
    confidence = "high" if not reasons else ("medium" if len(reasons) == 1 else "low")

    if r["roi"] >= target_roi_percent:
        verdict = "buy"
    elif r["roi"] >= CONSIDER_ROI_PERCENT or (offer_gap is not None and offer_gap <= 10):
        verdict = "consider"  # close enough that a negotiated price could make it work
    else:
        verdict = "skip"
    if unusual_size and verdict == "buy":
        verdict = "consider"  # never a confident "buy" off flat comps for a non-typical property
    if unusual_size:
        confidence = "low"

    return FlipResult(
        condition_tag=condition_tag,
        scope=scope,
        usable_area_sqm=usable_area_sqm,
        purchase_price_huf=price_huf,
        purchase_costs_huf=r["purchase_costs"],
        renovation_cost_huf=r["renovation"],
        contingency_huf=r["contingency"],
        holding_months=holding_months,
        holding_cost_huf=r["holding"],
        total_cash_needed_huf=r["total_cash"],
        exit_price_sqm_huf=exit_price_sqm,
        exit_price_huf=exit_price,
        sale_costs_huf=r["sale_costs"],
        profit_before_tax_huf=r["profit_before_tax"],
        gains_tax_huf=r["gains_tax"],
        net_profit_huf=r["net_profit"],
        roi_percent=r["roi"],
        annualized_roi_percent=annualized,
        max_offer_price_huf=max_offer,
        offer_gap_percent=offer_gap,
        discount_vs_market_percent=discount,
        verdict=verdict,
        confidence=confidence,
        confidence_reasons=reasons,
        exit_basis=exit_basis,
    )


ASSUMPTIONS = {
    "renovation_huf_per_sqm": RENOVATION_SCOPE_HUF_PER_SQM,
    "holding_months": HOLDING_MONTHS_BY_SCOPE,
    "renovation_contingency_rate": RENOVATION_CONTINGENCY_RATE,
    "asking_to_sale_discount": ASKING_TO_SALE_DISCOUNT,
    "holding_cost_huf_per_sqm_month": HOLDING_COST_HUF_PER_SQM_MONTH,
    "holding_cost_fixed_huf_month": HOLDING_COST_FIXED_HUF_MONTH,
    "transfer_tax_rate": PROPERTY_TRANSFER_TAX_RATE,
    "legal_fee_rate": LEGAL_NOTARY_FEE_RATE,
    "broker_fee_rate": BROKER_FEE_RATE,
    "gains_tax_rate": GAINS_TAX_RATE,
    "target_roi_percent": TARGET_ROI_PERCENT,
    "consider_roi_percent": CONSIDER_ROI_PERCENT,
}
