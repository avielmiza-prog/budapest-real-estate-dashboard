"""
Unit tests for scraper.text_parsing — pure stdlib + app.analyzer, no
Playwright/SQLAlchemy/network needed.

Run with:  python3 tests/test_text_parsing.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scraper import text_parsing as tp  # noqa: E402


def test_parse_price_huf():
    assert tp.parse_price_huf("89 900 000 Ft") == 89_900_000.0
    assert tp.parse_price_huf("45,5 M Ft") == 45_500_000.0
    assert tp.parse_price_huf("45.5 millió Ft") == 45_500_000.0
    assert tp.parse_price_huf("120000000 HUF") == 120_000_000.0
    assert tp.parse_price_huf("no price here") is None
    assert tp.parse_price_huf("") is None


def test_parse_price_eur():
    assert tp.parse_price_eur("289 000 €") == 289_000.0
    assert tp.parse_price_eur("289,000 EUR") == 289_000.0
    assert tp.parse_price_eur("no eur") is None


def test_parse_size_sqm():
    assert tp.parse_size_sqm("55 m²") == 55.0
    assert tp.parse_size_sqm("55m2") == 55.0
    assert tp.parse_size_sqm("72,5 nm") == 72.5
    assert tp.parse_size_sqm("no size") is None


def test_parse_rooms():
    assert tp.parse_rooms("2+1 fél szoba") == 2.5
    assert tp.parse_rooms("4+2") == 5.0
    assert tp.parse_rooms("3 szoba") == 3.0
    assert tp.parse_rooms("2.5 szoba") == 2.5
    assert tp.parse_rooms("3") == 3.0
    assert tp.parse_rooms("") is None


def test_extract_district_roman_from_kerulet_text():
    assert tp.extract_district_roman("1073 Budapest, VII. kerület, Wesselényi utca") == "VII"
    assert tp.extract_district_roman("Budapest, 13. kerület") == "XIII"
    assert tp.extract_district_roman("V. ker., belváros") == "V"


def test_extract_district_roman_falls_back_to_postcode():
    assert tp.extract_district_roman("1146 Budapest, Thököly út 51.") == "XIV"
    assert tp.extract_district_roman("1051 Budapest, Széchenyi tér") == "V"


def test_extract_district_roman_rejects_invalid_or_missing():
    assert tp.extract_district_roman("no district info") is None
    assert tp.extract_district_roman("Budapest XXIV. kerület") is None  # 24 doesn't exist


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
