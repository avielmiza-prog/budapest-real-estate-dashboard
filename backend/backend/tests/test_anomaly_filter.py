"""
Unit tests for scraper.anomaly_filter — the price/size sanity guardrails
applied to every scraped listing in scraper/pipeline.py's store_and_analyze().

Run with: python -m pytest tests/test_anomaly_filter.py -q
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scraper.anomaly_filter import anomaly_reason  # noqa: E402


def _normalized(**overrides) -> dict:
    base = {"price_huf": 40_000_000.0, "size_sqm": 50.0, "price_per_sqm": 800_000.0}
    base.update(overrides)
    return base


def test_passes_a_normal_listing():
    assert anomaly_reason(_normalized()) is None


def test_rejects_price_below_sale_floor():
    reason = anomaly_reason(_normalized(price_huf=10_000_000.0, price_per_sqm=200_000.0))
    assert reason is not None and "price" in reason


def test_rejects_size_below_floor():
    reason = anomaly_reason(_normalized(size_sqm=10.0, price_per_sqm=4_000_000.0))
    assert reason is not None and "size" in reason


def test_rejects_price_per_sqm_below_floor():
    reason = anomaly_reason(_normalized(price_per_sqm=100_000.0))
    assert reason is not None and "price/sqm" in reason


def test_rejects_price_per_sqm_above_ceiling():
    reason = anomaly_reason(_normalized(price_per_sqm=9_000_000.0))
    assert reason is not None and "price/sqm" in reason


def test_boundary_values_pass():
    assert anomaly_reason(_normalized(price_huf=15_000_000.0, price_per_sqm=800_000.0)) is None
    assert anomaly_reason(_normalized(size_sqm=15.0)) is None
    assert anomaly_reason(_normalized(price_per_sqm=400_000.0)) is None
    assert anomaly_reason(_normalized(price_per_sqm=4_500_000.0)) is None


def test_missing_fields_are_not_treated_as_anomalous():
    # normalize_listing() already drops listings with no price at all; a
    # missing size (portal didn't report one) shouldn't itself be a rejection.
    assert anomaly_reason(_normalized(size_sqm=None, price_per_sqm=None)) is None


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
