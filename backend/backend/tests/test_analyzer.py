"""
Unit tests for app.analyzer — pure stdlib, no SQLAlchemy/FastAPI needed.

Run with:  python3 -m pytest tests/test_analyzer.py   (if pytest is installed)
or just:   python3 tests/test_analyzer.py             (plain assertions, no deps)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import analyzer  # noqa: E402


def test_acquisition_costs():
    assert analyzer.calculate_acquisition_costs(45_000_000) == 45_000_000 * 0.05
    assert analyzer.calculate_acquisition_costs(0) == 0
    try:
        analyzer.calculate_acquisition_costs(-1)
        raise AssertionError("expected ValueError for negative price")
    except ValueError:
        pass


def test_renovation_cost_tiers():
    rate = 400.0
    assert analyzer.calculate_renovation_cost_huf(50, "light", rate) == 50 * 250 * rate
    assert analyzer.calculate_renovation_cost_huf(50, "MEDIUM", rate) == 50 * 450 * rate  # case-insensitive
    assert analyzer.calculate_renovation_cost_huf(50, "full", rate) == 50 * 700 * rate
    try:
        analyzer.calculate_renovation_cost_huf(50, "luxury", rate)
        raise AssertionError("expected ValueError for unknown tier")
    except ValueError:
        pass


def test_exit_price():
    assert analyzer.calculate_exit_price_huf(60, 1_000_000) == 60_000_000


def test_full_analysis_matches_hand_calculation():
    result = analyzer.analyze_property(
        size_sqm=55,
        asking_price_huf=45_000_000,
        avg_price_sqm_renovated_huf=1_250_000,
        district="VII",
    )
    assert result.acquisition_cost_huf == 45_000_000 * 0.05
    assert result.exit_price_huf == 55 * 1_250_000

    light = next(t for t in result.tiers if t.tier == "light")
    expected_reno = 55 * 250 * analyzer.DEFAULT_EUR_HUF_RATE
    expected_buffer = analyzer.SAFETY_BUFFER_RATE * (
        45_000_000 + result.acquisition_cost_huf + expected_reno
    )
    expected_investment = 45_000_000 + result.acquisition_cost_huf + expected_reno + expected_buffer
    expected_profit = result.exit_price_huf - expected_investment
    expected_roi = expected_profit / expected_investment * 100

    assert light.renovation_cost_huf == expected_reno
    assert abs(light.safety_buffer_huf - expected_buffer) < 1e-6
    assert abs(light.total_investment_huf - expected_investment) < 1e-6
    assert abs(light.net_profit_huf - expected_profit) < 1e-6
    assert abs(light.roi_percent - expected_roi) < 1e-6

    # ROI should decrease as renovation tier gets more expensive, holding
    # exit price fixed (since exit price doesn't vary by tier in this model).
    rois = [t.roi_percent for t in result.tiers]
    assert rois == sorted(rois, reverse=True), "expected light > medium > full ROI"

    assert result.best_tier().tier == "light"


def test_zero_investment_edge_case_does_not_divide_by_zero():
    # Degenerate case: everything zero -> total_investment is 0, ROI should be None not a crash.
    result = analyzer.analyze_property(
        size_sqm=1,
        asking_price_huf=0,
        avg_price_sqm_renovated_huf=0,
        eur_huf_rate=0,
    )
    for t in result.tiers:
        assert t.roi_percent is None


def test_negative_size_rejected():
    try:
        analyzer.analyze_property(size_sqm=-10, asking_price_huf=1, avg_price_sqm_renovated_huf=1)
        raise AssertionError("expected ValueError for non-positive size_sqm")
    except ValueError:
        pass


def test_balcony_weighted_usable_area():
    result = analyzer.analyze_property(
        size_sqm=50,
        asking_price_huf=40_000_000,
        avg_price_sqm_renovated_huf=1_000_000,
        balcony_sqm=10,
    )
    # 50 + 10*0.5 = 55 sqm usable
    assert result.usable_area_sqm == 55
    assert result.exit_price_huf == 55 * 1_000_000


def test_custom_renovation_tier():
    result = analyzer.analyze_property(
        size_sqm=50,
        asking_price_huf=40_000_000,
        avg_price_sqm_renovated_huf=1_000_000,
        custom_cost_eur_per_sqm=500,
    )
    tiers = {t.tier for t in result.tiers}
    assert tiers == {"light", "medium", "full", "custom"}
    custom = next(t for t in result.tiers if t.tier == "custom")
    assert custom.cost_eur_per_sqm == 500
    assert custom.renovation_cost_huf == 50 * 500 * analyzer.DEFAULT_EUR_HUF_RATE


def test_rental_yield_requires_benchmark():
    no_rent = analyzer.analyze_property(
        size_sqm=50, asking_price_huf=40_000_000, avg_price_sqm_renovated_huf=1_000_000
    )
    assert all(t.gross_yield_percent is None for t in no_rent.tiers)

    with_rent = analyzer.analyze_property(
        size_sqm=50,
        asking_price_huf=40_000_000,
        avg_price_sqm_renovated_huf=1_000_000,
        avg_rent_huf_sqm=3_000,
    )
    light = next(t for t in with_rent.tiers if t.tier == "light")
    expected_gross_rent = 3_000 * 50 * 12
    assert light.gross_annual_rent_huf == expected_gross_rent
    assert abs(light.gross_yield_percent - expected_gross_rent / light.total_investment_huf * 100) < 1e-6
    expected_net_rent = expected_gross_rent * (1 - analyzer.RENTAL_OPEX_RATE)
    assert abs(light.net_yield_percent - expected_net_rent / light.total_investment_huf * 100) < 1e-6


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
