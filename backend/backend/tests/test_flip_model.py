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
    r = _eval(price_huf=15_000_000.0)  # profitable, so there is a gain to tax
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
    assert _eval(price_huf=15_000_000.0).verdict == "buy"
    assert _eval(price_huf=21_000_000.0).verdict == "consider"
    assert _eval(price_huf=70_000_000.0).verdict == "skip"


def test_panel_exit_is_lower_than_brick():
    brick = _eval()
    panel = _eval(building_type=BUILDING_TYPE_PANEL_BLOCK)
    assert panel.exit_price_huf < brick.exit_price_huf


def test_live_building_type_median_overrides_static_factor():
    r = _eval(building_type=BUILDING_TYPE_PANEL_BLOCK, building_type_median_sqm=1_000_000.0,
              building_type_samples=12, district_all_median_sqm=1_250_000.0)
    district_exit = 1_500_000 * 0.8
    anchored = 40_000_000 / 50 + (1_500_000 - 1_100_000) * 0.8
    assert r.exit_price_sqm_huf == pytest.approx(min(district_exit, 0.6 * anchored + 0.4 * district_exit) * 0.95)
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


def test_basement_lowers_exit_and_usufruct_blocks_buy():
    base = _eval(price_huf=15_000_000.0)
    basement = _eval(price_huf=15_000_000.0, floor="szuterén")
    assert basement.exit_price_huf < base.exit_price_huf
    assert "basement" in basement.red_flags
    blocked = _eval(price_huf=15_000_000.0, description="A lakáson holtig tartó haszonélvezeti jog van.")
    assert base.verdict == "buy" and blocked.verdict == "consider"
    assert "usufruct" in blocked.red_flags and blocked.confidence == "low"


def test_high_floor_without_elevator_is_flagged():
    r = _eval(floor="4", has_elevator=False)
    assert "no_elevator_high_floor" in r.red_flags
    assert r.flags_exit_factor < 1


def test_exit_is_anchored_to_the_flats_own_price():
    """Regression: a cheap already-renovated flat must not be assumed to sell at the district average."""
    r = _eval(size_sqm=85.0, price_huf=69_000_000.0, condition="Felújított",
              district_renovated_median_sqm=1_680_000.0, district_raw_median_sqm=1_230_000.0,
              renovated_source="fallback", renovated_sample_count=3)
    own = 69_000_000 / 85
    assert r.exit_price_sqm_huf < own * 1.35  # was ~1.97x before the fix
    assert r.exit_price_sqm_huf < 1_680_000 * 0.95


def test_exit_never_exceeds_district_ceiling():
    r = _eval(price_huf=80_000_000.0)  # 1.6M/sqm, above the renovated median
    assert r.exit_price_sqm_huf <= 1_500_000 * 0.95 + 1
