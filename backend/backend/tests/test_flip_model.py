"""app.flip_model: the realistic flip verdict."""
import pytest

from app import flip_model as fm
from app.building_classifier import BUILDING_TYPE_PANEL_BLOCK


def _eval(**kw):
    base = dict(size_sqm=50.0, price_huf=40_000_000.0, condition="Felújítandó",
                district_renovated_median_sqm=1_500_000.0, district_raw_median_sqm=1_100_000.0,
                renovated_sample_count=30, renovated_source="live", building_type="Brick Classical (Polgári)")
    base.update(kw)
    return fm.evaluate_flip(**base)


def test_scope_follows_condition_not_cheapest_tier():
    assert _eval(condition="Felújítandó").scope == "full"
    assert _eval(condition="Átlagos állapotú").scope == "medium"
    assert _eval(condition="Felújított").scope == "refresh"
    assert _eval(condition=None).scope == "medium"


def test_gains_tax_and_net_profit():
    r = _eval()
    taxable = r.exit_price_huf - r.sale_costs_huf - (r.total_cash_needed_huf - r.holding_cost_huf)
    assert r.gains_tax_huf == pytest.approx(0.15 * taxable)
    assert r.net_profit_huf == pytest.approx(r.profit_before_tax_huf - r.gains_tax_huf)


def test_no_tax_on_a_loss():
    r = _eval(price_huf=80_000_000.0)
    assert r.net_profit_huf < 0
    assert r.gains_tax_huf == 0
    assert r.verdict == "skip"


def test_max_offer_hits_target_roi_exactly():
    r = _eval()
    assert r.max_offer_price_huf is not None
    at_max = _eval(price_huf=r.max_offer_price_huf)
    assert at_max.roi_percent == pytest.approx(fm.TARGET_ROI_PERCENT, abs=0.01)


def test_cheap_flat_is_buy_expensive_is_skip():
    assert _eval(price_huf=30_000_000.0).verdict == "buy"
    assert _eval(price_huf=35_000_000.0).verdict == "consider"
    assert _eval(price_huf=70_000_000.0).verdict == "skip"


def test_panel_exit_is_lower_than_brick():
    brick = _eval()
    panel = _eval(building_type=BUILDING_TYPE_PANEL_BLOCK)
    assert panel.exit_price_huf < brick.exit_price_huf


def test_live_building_type_median_overrides_static_factor():
    r = _eval(building_type=BUILDING_TYPE_PANEL_BLOCK, building_type_median_sqm=1_000_000.0,
              building_type_samples=12, district_all_median_sqm=1_250_000.0)
    assert r.exit_price_sqm_huf == pytest.approx(1_500_000 * 0.8 * 0.95)
    assert "live" in r.exit_basis


def test_fallback_benchmark_lowers_confidence():
    assert _eval().confidence == "high"
    assert _eval(renovated_source="fallback", renovated_sample_count=3).confidence != "high"


def test_discount_uses_same_condition_median():
    r = _eval(price_huf=50_000_000.0)  # 1.0M/sqm vs raw median 1.1M -> ~9% below
    assert r.discount_vs_market_percent == pytest.approx((1_100_000 - 1_000_000) / 1_100_000 * 100)


def test_huge_property_is_never_a_confident_buy():
    r = _eval(size_sqm=400.0, price_huf=200_000_000.0)
    assert r.verdict != "buy"
    assert "unusual_size" in r.confidence_reasons
    assert r.confidence == "low"
