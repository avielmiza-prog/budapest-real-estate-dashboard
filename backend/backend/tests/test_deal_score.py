"""
Unit tests for app.deal_score — pure stdlib, no SQLAlchemy/FastAPI needed.

Run with: python3 tests/test_deal_score.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import deal_score  # noqa: E402


def test_none_when_no_signal_at_all():
    assert deal_score.compute_deal_score(discount_percent=None, roi_percent=None) is None


def test_bounds_are_0_to_100():
    # Way outside the clamp ranges on both sides -> still 0-100.
    high = deal_score.compute_deal_score(discount_percent=1000, roi_percent=1000, usable_area_sqm=1000, rooms=1)
    low = deal_score.compute_deal_score(discount_percent=-1000, roi_percent=-1000, usable_area_sqm=1, rooms=100)
    assert 0 <= high <= 100
    assert 0 <= low <= 100
    assert high > low


def test_higher_discount_and_roi_score_higher():
    weak = deal_score.compute_deal_score(discount_percent=0, roi_percent=0)
    strong = deal_score.compute_deal_score(discount_percent=30, roi_percent=20)
    assert strong > weak


def test_missing_component_falls_back_to_neutral_not_zero():
    # Only discount known (strong) — roi missing shouldn't drag score down to 0.
    only_discount = deal_score.compute_deal_score(discount_percent=30, roi_percent=None)
    assert only_discount is not None and only_discount > 50


def test_layout_efficiency_affects_score():
    cramped = deal_score.compute_deal_score(
        discount_percent=10, roi_percent=10, usable_area_sqm=30, rooms=4
    )
    spacious = deal_score.compute_deal_score(
        discount_percent=10, roi_percent=10, usable_area_sqm=120, rooms=4
    )
    assert spacious > cramped


def test_score_band_thresholds():
    assert deal_score.score_band(80) == "high"
    assert deal_score.score_band(deal_score.SCORE_BAND_HIGH) == "high"
    assert deal_score.score_band(deal_score.SCORE_BAND_HIGH - 1) == "fair"
    assert deal_score.score_band(deal_score.SCORE_BAND_FAIR) == "fair"
    assert deal_score.score_band(deal_score.SCORE_BAND_FAIR - 1) == "low"
    assert deal_score.score_band(None) is None


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"PASS: {t.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL: {t.__name__}: {e}")
    print(f"\n{len(tests) - failures}/{len(tests)} tests passed")
    sys.exit(1 if failures else 0)
