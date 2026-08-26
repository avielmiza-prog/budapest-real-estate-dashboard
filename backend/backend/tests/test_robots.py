"""
Unit tests for scraper.robots. Network-dependent behavior (real robots.txt
fetches) is mocked so this runs offline; the "fail open on error" path is
exercised with a URL scheme that fails fast without touching the network.

Run with: python3 tests/test_robots.py
"""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scraper import robots  # noqa: E402


def test_check_or_raise_passes_when_allowed():
    with patch.object(robots, "is_allowed", return_value=True):
        robots.check_or_raise("https://example.com/somewhere")  # should not raise


def test_check_or_raise_raises_when_disallowed():
    with patch.object(robots, "is_allowed", return_value=False):
        try:
            robots.check_or_raise("https://example.com/lista")
            raise AssertionError("expected PermissionError")
        except PermissionError as e:
            assert "robots.txt disallows" in str(e)


def test_is_allowed_fails_open_on_unfetchable_robots_txt():
    robots._get_parser.cache_clear()
    # Bogus scheme -> RobotFileParser.read() raises immediately (no network I/O),
    # exercising the except-and-fail-open branch in is_allowed().
    result = robots.is_allowed("not-a-real-scheme://nope.invalid/somewhere")
    assert result is True


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
