"""
Combines app.condition_classifier's condition-based baseline HUF/sqm
renovation estimate with app.building_classifier's building-type/ceiling-
height multiplier into one adjusted per-sqm figure.

Used by app/services/valuation_agent.py (persisted underwriting) and
app/services/scenario_analysis.py (Conservative/Base/Optimistic sensitivity)
— both want "how much would renovating this specific unit actually cost",
not just a condition-only estimate that treats a high-ceiling Polgári flat
the same as a standardized Panelház unit in the same condition.

Kept as its own leaf module rather than folded into either source module, so
neither has to import the other.
"""
from typing import Optional

from app.building_classifier import renovation_cost_multiplier
from app.condition_classifier import estimate_renovation_cost_huf_per_sqm as _condition_baseline_huf_per_sqm


def estimate_adjusted_renovation_cost_huf_per_sqm(
    condition_text: Optional[str],
    building_type: Optional[str] = None,
    ceiling_height_m: Optional[float] = None,
) -> float:
    """
    Condition-based baseline HUF/sqm (see app.condition_classifier), scaled
    by a building-type/ceiling-height multiplier (see
    app.building_classifier.renovation_cost_multiplier). Unknown
    building_type/ceiling_height_m -> multiplier of 1.0, i.e. identical to
    the unadjusted condition-only estimate.
    """
    baseline = _condition_baseline_huf_per_sqm(condition_text)
    multiplier = renovation_cost_multiplier(building_type, ceiling_height_m)
    return baseline * multiplier
