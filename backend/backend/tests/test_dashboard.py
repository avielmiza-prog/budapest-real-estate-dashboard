"""
Unit tests for app.dashboard's pure helper functions (_reference_price_sqm,
_discount_percent). These only touch plain attribute access, so they're
tested here with lightweight stand-ins instead of real SQLAlchemy model
instances/a real DB — this backend's SQLAlchemy can't be installed in the
sandbox this was written in (see backend/README.md), so sqlalchemy itself is
stubbed just enough for `import app.dashboard` to succeed.

Run with: python3 tests/test_dashboard.py
"""
import sys
import types
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _stub_sqlalchemy():
    if "sqlalchemy" in sys.modules:
        return
    fake_sa = types.ModuleType("sqlalchemy")
    for name in ["Column", "Integer", "Float", "String", "Text", "DateTime", "JSON", "Boolean", "create_engine", "inspect", "text"]:
        setattr(fake_sa, name, lambda *a, **k: None)
    fake_orm = types.ModuleType("sqlalchemy.orm")
    fake_orm.Session = object
    fake_orm.declarative_base = lambda *a, **k: type(
        "Base", (), {"metadata": SimpleNamespace(create_all=lambda **kw: None)}
    )
    fake_orm.sessionmaker = lambda *a, **k: (lambda: None)
    fake_sa.orm = fake_orm
    sys.modules["sqlalchemy"] = fake_sa
    sys.modules["sqlalchemy.orm"] = fake_orm


_stub_sqlalchemy()

from app.dashboard import _discount_percent, _reference_price_sqm  # noqa: E402

BENCHMARK = SimpleNamespace(avg_price_sqm_raw=950_000, avg_price_sqm_renovated=1_250_000)
RENOVATED_ONLY_BENCHMARK = SimpleNamespace(avg_price_sqm_raw=None, avg_price_sqm_renovated=1_250_000)


def test_reference_price_uses_renovated_benchmark_for_renovated_condition():
    prop = SimpleNamespace(condition="felújított", price_per_sqm=1_000_000)
    assert _reference_price_sqm(prop, BENCHMARK) == 1_250_000


def test_reference_price_uses_raw_benchmark_for_unrenovated_condition():
    prop = SimpleNamespace(condition="original allapotu", price_per_sqm=800_000)
    assert _reference_price_sqm(prop, BENCHMARK) == 950_000


def test_reference_price_treats_unknown_condition_as_raw():
    prop = SimpleNamespace(condition=None, price_per_sqm=900_000)
    assert _reference_price_sqm(prop, BENCHMARK) == 950_000


def test_reference_price_falls_back_when_preferred_benchmark_missing():
    prop = SimpleNamespace(condition="raw", price_per_sqm=800_000)
    assert _reference_price_sqm(prop, RENOVATED_ONLY_BENCHMARK) == 1_250_000


def test_discount_percent_positive_when_underpriced():
    prop = SimpleNamespace(condition="original allapotu", price_per_sqm=800_000)
    expected = round((950_000 - 800_000) / 950_000 * 100, 2)
    assert _discount_percent(prop, BENCHMARK) == expected
    assert expected > 0


def test_discount_percent_negative_when_overpriced():
    prop = SimpleNamespace(condition="felújított", price_per_sqm=1_500_000)
    result = _discount_percent(prop, BENCHMARK)
    assert result is not None and result < 0


def test_discount_percent_none_without_price():
    prop = SimpleNamespace(condition="raw", price_per_sqm=None)
    assert _discount_percent(prop, BENCHMARK) is None


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
