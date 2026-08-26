"""
Deal Attractiveness Score (0-100): a single composite number ranking how
good a deal looks, so cards, map pins, and the split-view ranking don't each
need to reconcile three separate numbers to compare deals at a glance.

Weighted composite of:
  - discount vs. district benchmark price/sqm (50%)
  - best-tier renovate-and-flip ROI (30%)
  - layout efficiency: usable sqm per room (20%) — rewards properties that
    aren't chopped into more small rooms than their size can comfortably fit

Each component is clamped to a reasonable real-world range, then linearly
rescaled to 0-100 before being weighted and summed. Clamping first (not just
scaling) matters: without it, one wildly discounted or wildly inefficient
outlier would compress every other property's score toward the middle.
"""
from typing import Optional

DISCOUNT_WEIGHT = 0.50
ROI_WEIGHT = 0.30
LAYOUT_WEIGHT = 0.20

# (min, max) clamp bounds per component, in the component's native unit.
DISCOUNT_RANGE_PERCENT = (-20.0, 40.0)
ROI_RANGE_PERCENT = (-10.0, 30.0)
LAYOUT_RANGE_SQM_PER_ROOM = (15.0, 45.0)

# Score bands the frontend's color coding (map pins / badges) keys off of.
SCORE_BAND_HIGH = 80  # >= this: green ("hot deal")
SCORE_BAND_FAIR = 60  # >= this: amber ("fair"); below: red ("overpriced")


def _clamp_scale(value: float, low: float, high: float) -> float:
    """Clamp value to [low, high], then linearly rescale to [0, 100]."""
    clamped = max(low, min(high, value))
    if high == low:
        return 50.0
    return (clamped - low) / (high - low) * 100


def compute_deal_score(
    discount_percent: Optional[float],
    roi_percent: Optional[float],
    usable_area_sqm: Optional[float] = None,
    rooms: Optional[float] = None,
) -> Optional[int]:
    """
    Returns an int 0-100, or None if there isn't enough signal (neither a
    discount-vs-benchmark nor an ROI figure) to say anything meaningful.
    A missing individual component falls back to a neutral 50 rather than
    dropping out of the weighted sum, so one missing input doesn't silently
    zero out its whole weight.
    """
    if discount_percent is None and roi_percent is None:
        return None

    discount_score = (
        _clamp_scale(discount_percent, *DISCOUNT_RANGE_PERCENT) if discount_percent is not None else 50.0
    )
    roi_score = _clamp_scale(roi_percent, *ROI_RANGE_PERCENT) if roi_percent is not None else 50.0

    layout_score = 50.0
    if usable_area_sqm and rooms and rooms > 0:
        layout_score = _clamp_scale(usable_area_sqm / rooms, *LAYOUT_RANGE_SQM_PER_ROOM)

    score = DISCOUNT_WEIGHT * discount_score + ROI_WEIGHT * roi_score + LAYOUT_WEIGHT * layout_score
    return round(score)


def score_band(deal_score: Optional[int]) -> Optional[str]:
    """'high' | 'fair' | 'low', matching the frontend's green/yellow/red map-pin coding."""
    if deal_score is None:
        return None
    if deal_score >= SCORE_BAND_HIGH:
        return "high"
    if deal_score >= SCORE_BAND_FAIR:
        return "fair"
    return "low"
