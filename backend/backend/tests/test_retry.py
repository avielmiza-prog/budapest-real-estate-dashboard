"""
Unit tests for scraper.retry.with_retry — pure stdlib, no Playwright needed.
Uses base_delay=0 throughout so the tests run instantly (still exercises the
real retry/backoff control flow, just without real waiting).

Run with: python3 tests/test_retry.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scraper.retry import with_retry  # noqa: E402


def test_succeeds_first_try_no_retry_needed():
    calls = []

    @with_retry(attempts=3, base_delay=0)
    def flaky():
        calls.append(1)
        return "ok"

    assert flaky() == "ok"
    assert len(calls) == 1


def test_succeeds_after_transient_failures():
    calls = []

    @with_retry(attempts=3, base_delay=0)
    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise ValueError("transient")
        return "ok"

    assert flaky() == "ok"
    assert len(calls) == 3


def test_raises_after_exhausting_all_attempts():
    calls = []

    @with_retry(attempts=3, base_delay=0)
    def always_fails():
        calls.append(1)
        raise ValueError("permanent")

    try:
        always_fails()
        raise AssertionError("expected ValueError to propagate")
    except ValueError:
        pass
    assert len(calls) == 3


def test_only_retries_matching_exception_types():
    @with_retry(attempts=3, base_delay=0, exceptions=(ValueError,))
    def raises_type_error():
        raise TypeError("not covered by the retry")

    try:
        raises_type_error()
        raise AssertionError("expected TypeError to propagate immediately, uncaught")
    except TypeError:
        pass


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
