"""
Unit tests for app.services.valuation_agent — the automated underwriting
verification agent (distinct from app.analyzer's interactive tier tool).

Run with: python -m pytest tests/test_valuation_agent.py -q
"""
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_tmp_db_dir = tempfile.mkdtemp(prefix="budapest_apartments_test_valuation_")
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_tmp_db_dir) / 'test.db'}"

import pytest  # noqa: E402

from app import crud, models, schemas  # noqa: E402
from app.condition_classifier import (  # noqa: E402
    CONDITION_AVERAGE,
    CONDITION_NEEDS_RENOVATION,
    CONDITION_NEW_CONSTRUCTION,
    CONDITION_RENOVATED,
    classify_condition_tag,
    estimate_renovation_cost_huf_per_sqm,
)
from app.database import SessionLocal, init_db  # noqa: E402
from app.services import valuation_agent as va  # noqa: E402

init_db()


# ---------------------------------------------------------------------------
# classify_condition / estimate_renovation_cost_huf_per_sqm / classify_condition_tag
# (app.condition_classifier — valuation_agent no longer re-exports these, it
# imports app.renovation_estimator instead; see that module's docstring)
# ---------------------------------------------------------------------------

def test_unrenovated_condition_gets_needs_renovation_point_estimate():
    assert estimate_renovation_cost_huf_per_sqm("Felújítandó, jó lehetőség") == 220_000
    assert classify_condition_tag("Felújítandó, jó lehetőség") == CONDITION_NEEDS_RENOVATION
    assert classify_condition_tag("Rossz állapotú, sürgősen eladó") == CONDITION_NEEDS_RENOVATION


def test_average_condition_gets_average_point_estimate():
    assert estimate_renovation_cost_huf_per_sqm("Átlagos állapotú lakás") == 120_000
    assert classify_condition_tag("Átlagos állapotú lakás") == CONDITION_AVERAGE
    assert classify_condition_tag("Lakható állapotban") == CONDITION_AVERAGE


def test_renovated_and_new_construction_get_zero_reno_cost_but_distinct_tags():
    assert estimate_renovation_cost_huf_per_sqm("Felújított lakás") == 0
    assert classify_condition_tag("Felújított, újszerű lakás") == CONDITION_RENOVATED

    assert estimate_renovation_cost_huf_per_sqm("Új építésű, kulcsrakész") == 0
    assert classify_condition_tag("Új építésű társasházban") == CONDITION_NEW_CONSTRUCTION


def test_missing_condition_defaults_to_average_not_free():
    assert estimate_renovation_cost_huf_per_sqm(None) == 120_000
    assert estimate_renovation_cost_huf_per_sqm("") == 120_000
    assert classify_condition_tag(None) == CONDITION_AVERAGE


# ---------------------------------------------------------------------------
# validate_and_underwrite — full pipeline against real DB rows
# ---------------------------------------------------------------------------

def _make_property(db, **overrides) -> models.Property:
    payload = {
        "title": "Test flat",
        "district": "VII",
        "size_sqm": 50.0,
        "price_huf": 40_000_000.0,
        "condition": "Átlagos állapotú",
        "url": f"https://example.test/{overrides.get('title', 'listing')}-{id(overrides)}",
        "portal": "jofogas",
    }
    payload.update(overrides)
    prop = crud.create_property(db, schemas.PropertyCreate(**payload))
    return prop


def _make_benchmark(db, district_number=7, raw=800_000.0, renovated=1_500_000.0, rent=5000.0):
    return crud.create_district_benchmark(
        db,
        schemas.DistrictBenchmarkCreate(
            district_number=district_number,
            avg_price_sqm_raw=raw,
            avg_price_sqm_renovated=renovated,
            avg_rent_huf_sqm=rent,
        ),
    )


def test_insufficient_data_when_missing_size_or_price():
    db = SessionLocal()
    try:
        prop = SimpleNamespace(size_sqm=None, price_huf=40_000_000.0, condition=None, district="VII")
        result = va.validate_and_underwrite(prop, db)
        assert result.status == "insufficient_data"
        assert result.deal_score is None
    finally:
        db.close()


def test_no_benchmark_still_reports_cost_side():
    db = SessionLocal()
    try:
        prop = _make_property(db, district="I")  # no benchmark seeded for district 1 in this test
        result = va.validate_and_underwrite(prop, db)
        assert result.status == "no_benchmark"
        assert result.renovation_cost_huf == 50.0 * 120_000  # size_sqm * average-condition point estimate
        assert result.total_investment_huf is not None
        assert result.estimated_market_value_huf is None
        assert result.deal_score is None
    finally:
        db.close()


def test_full_underwriting_math_and_formulas():
    """Scan-time verdict must equal app.flip_model's realistic numbers (hand-checked below)."""
    db = SessionLocal()
    try:
        _make_benchmark(db, district_number=7, renovated=1_500_000.0, rent=5000.0)
        prop = _make_property(db, district="VII", size_sqm=50.0, price_huf=40_000_000.0, condition="Átlagos állapotú")

        result = va.validate_and_underwrite(prop, db)

        # Average condition -> medium scope: 170k HUF/sqm + 15% contingency, 7 holding months.
        renovation = 50 * 170_000 * 1.15  # 9,775,000
        purchase_costs = 40_000_000 * 0.055  # 2,200,000
        holding = 7 * (450 * 50 + 25_000)  # 332,500
        total_cash = 40_000_000 + purchase_costs + renovation + holding
        # Exit anchored to the flat's own price (800k/sqm) + medium-scope
        # uplift of the raw(800k)->renovated(1.5M) gap; no sample counts ->
        # thin data -> 75% anchor weight; asking-to-sale discount 5%.
        uplift = (1_500_000 - 800_000) * 0.6
        anchored = 40_000_000 / 50 + uplift
        exit_sqm = min(1_500_000, 0.75 * anchored + 0.25 * 1_500_000) * 0.95
        exit_price = 50 * exit_sqm
        sale_costs = exit_price * 0.03
        taxable_gain = exit_price - sale_costs - (total_cash - holding)
        net_profit = exit_price - sale_costs - total_cash - 0.15 * taxable_gain

        assert result.renovation_cost_huf == pytest.approx(renovation)
        assert result.total_investment_huf == pytest.approx(total_cash)
        assert result.estimated_market_value_huf == pytest.approx(exit_price)
        assert result.net_profit_huf == pytest.approx(net_profit)
        assert result.flip_roi_percent == pytest.approx(net_profit / total_cash * 100, abs=0.01)

        annual_rent = 5000.0 * 50.0 * 12
        assert result.rental_yield_percent == pytest.approx(annual_rent / total_cash * 100, abs=0.01)
        assert result.deal_score is not None and 0 <= result.deal_score <= 100
        assert "overpriced" not in result.status
    finally:
        db.close()


def test_overpriced_and_below_hurdle_risk_flags():
    db = SessionLocal()
    try:
        _make_benchmark(db, district_number=8, renovated=1_000_000.0, rent=3000.0)
        # asking price/sqm (1,600,000) is above the district's turnkey median (1,000,000) -> overpriced,
        # and this math also nets a negative/low ROI -> below_hurdle_roi too
        prop = _make_property(db, district="VIII", size_sqm=50.0, price_huf=80_000_000.0, condition="Felújítandó")

        result = va.validate_and_underwrite(prop, db)
        assert "overpriced" in result.status
        assert "below_hurdle_roi" in result.status
        assert result.confidence_tag is None
    finally:
        db.close()


def test_high_roi_gets_high_potential_flip_tag():
    db = SessionLocal()
    try:
        _make_benchmark(db, district_number=9, renovated=2_000_000.0, rent=1000.0)
        # deeply discounted vs. benchmark, cheap partial reno -> big margin -> high ROI
        prop = _make_property(db, district="IX", size_sqm=50.0, price_huf=20_000_000.0, condition="Átlagos állapotú")

        result = va.validate_and_underwrite(prop, db)
        assert result.flip_roi_percent >= va.HIGH_POTENTIAL_FLIP_ROI_PERCENT
        assert result.confidence_tag == "High Potential Flip"
    finally:
        db.close()


def test_persist_writes_all_fields_and_updated_at():
    db = SessionLocal()
    try:
        _make_benchmark(db, district_number=10, renovated=900_000.0, rent=4000.0)
        prop = _make_property(db, district="X", size_sqm=40.0, price_huf=25_000_000.0)

        assert prop.underwriting_updated_at is None
        result = va.validate_and_underwrite_and_persist(db, prop.id)
        assert result is not None

        refreshed = crud.get_property(db, prop.id)
        assert refreshed.underwriting_deal_score == result.deal_score
        assert refreshed.underwriting_flip_roi_percent == result.flip_roi_percent
        assert refreshed.underwriting_status == result.status
        assert refreshed.underwriting_updated_at is not None
    finally:
        db.close()


def test_persist_returns_none_for_missing_property():
    db = SessionLocal()
    try:
        assert va.validate_and_underwrite_and_persist(db, 9_999_999) is None
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
