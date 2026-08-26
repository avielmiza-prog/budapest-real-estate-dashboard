"""
Unit tests for scraper.url_utils — pure stdlib, no SQLAlchemy/FastAPI needed.

Run with:  python3 -m pytest tests/test_url_utils.py   (if pytest is installed)
or just:   python3 tests/test_url_utils.py             (plain assertions, no deps)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scraper import url_utils  # noqa: E402


def test_relative_url_resolved_against_base():
    assert (
        url_utils.clean_listing_url("/hirdetes/1001-eladó-lakás", base_url="https://ingatlanbazar.hu")
        == "https://ingatlanbazar.hu/hirdetes/1001-eladó-lakás"
    )


def test_already_absolute_url_left_alone_when_no_tracking_params():
    url = "https://ingatlanbazar.hu/hirdetes/1001-eladó-lakás"
    assert url_utils.clean_listing_url(url, base_url="https://ingatlanbazar.hu") == url


def test_tracking_params_stripped():
    dirty = "https://ingatlan.com/ingatlan/12345?utm_source=fb&utm_campaign=x&fbclid=abc123"
    assert url_utils.clean_listing_url(dirty) == "https://ingatlan.com/ingatlan/12345"


def test_non_tracking_query_params_kept():
    url = "https://example.com/listing/42?unit=b&gclid=xyz"
    assert url_utils.clean_listing_url(url) == "https://example.com/listing/42?unit=b"


def test_idempotent_when_called_twice():
    once = url_utils.clean_listing_url("/x?utm_source=a", base_url="https://example.com")
    twice = url_utils.clean_listing_url(once)
    assert once == twice == "https://example.com/x"


def test_empty_url_passed_through():
    assert url_utils.clean_listing_url("") == ""


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
