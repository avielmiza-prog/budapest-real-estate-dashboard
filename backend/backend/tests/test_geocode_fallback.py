"""
Unit tests for scraper.pipeline._fill_missing_coordinates — verifies the
three-way fallback (already has coords -> geocode address -> district
centroid) without ever hitting the real Nominatim API or a real DB.

Run with: python3 tests/test_geocode_fallback.py
"""
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scraper.pipeline import _fill_missing_coordinates  # noqa: E402


def test_skips_geocoding_when_coordinates_already_present():
    normalized = {"latitude": 47.5, "longitude": 19.05, "address": "Somewhere", "district": "VII"}
    with patch("scraper.pipeline.geocode.geocode_address") as mock_geocode:
        _fill_missing_coordinates(normalized, db=None)
    mock_geocode.assert_not_called()
    assert normalized["latitude"] == 47.5
    assert normalized["longitude"] == 19.05


def test_uses_geocoded_address_when_available():
    normalized = {"latitude": None, "longitude": None, "address": "Andrássy út 1, Budapest", "district": "VI"}
    with patch("scraper.pipeline.geocode.geocode_address", return_value=(47.51, 19.06)) as mock_geocode:
        _fill_missing_coordinates(normalized, db=None)
    mock_geocode.assert_called_once_with("Andrássy út 1, Budapest")
    assert normalized["latitude"] == 47.51
    assert normalized["longitude"] == 19.06


def test_falls_back_to_district_centroid_when_geocoding_fails():
    normalized = {"latitude": None, "longitude": None, "address": "Unresolvable address", "district": "VII"}
    fake_benchmark = SimpleNamespace(centroid_lat=47.4979, centroid_lng=19.0707)
    with patch("scraper.pipeline.geocode.geocode_address", return_value=None), patch(
        "scraper.pipeline.crud.get_district_benchmark", return_value=fake_benchmark
    ):
        _fill_missing_coordinates(normalized, db="fake-db")
    assert normalized["latitude"] == 47.4979
    assert normalized["longitude"] == 19.0707


def test_falls_back_to_centroid_when_no_address_at_all():
    normalized = {"latitude": None, "longitude": None, "address": None, "district": "III"}
    fake_benchmark = SimpleNamespace(centroid_lat=47.5636, centroid_lng=19.0396)
    with patch("scraper.pipeline.geocode.geocode_address") as mock_geocode, patch(
        "scraper.pipeline.crud.get_district_benchmark", return_value=fake_benchmark
    ):
        _fill_missing_coordinates(normalized, db="fake-db")
    mock_geocode.assert_not_called()
    assert normalized["latitude"] == 47.5636
    assert normalized["longitude"] == 19.0396


def test_leaves_coordinates_none_when_district_unparseable_and_no_benchmark():
    normalized = {"latitude": None, "longitude": None, "address": None, "district": "unknown"}
    with patch("scraper.pipeline.geocode.geocode_address") as mock_geocode:
        _fill_missing_coordinates(normalized, db="fake-db")
    mock_geocode.assert_not_called()
    assert normalized["latitude"] is None
    assert normalized["longitude"] is None


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
