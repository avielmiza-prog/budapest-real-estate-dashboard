"""
Exponential-backoff retry for the flaky-network parts of a scrape (page
navigation, JSON/DOM extraction). A transient failure — a timeout, a dropped
connection, a portal briefly rate-limiting — shouldn't kill the whole run or
even the current listing; a few seconds later it usually just works.
"""
import functools
import logging
import random
import time
from typing import Callable, Tuple, Type, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

DEFAULT_ATTEMPTS = 3
DEFAULT_BASE_DELAY_SECONDS = 1.0


def with_retry(
    attempts: int = DEFAULT_ATTEMPTS,
    base_delay: float = DEFAULT_BASE_DELAY_SECONDS,
    exceptions: Tuple[Type[BaseException], ...] = (Exception,),
):
    """
    Decorator: retry the wrapped callable up to `attempts` times on the given
    exception types, sleeping `base_delay * 2**attempt` seconds (plus a bit
    of jitter) between tries. Re-raises the last exception if every attempt
    fails.
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_exc: BaseException = None  # type: ignore[assignment]
            for attempt in range(attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:  # noqa: BLE001 - intentionally broad, narrowed by `exceptions`
                    last_exc = e
                    if attempt == attempts - 1:
                        break
                    delay = base_delay * (2**attempt) + random.uniform(0, base_delay)
                    logger.warning(
                        "%s failed (attempt %d/%d): %s — retrying in %.1fs",
                        func.__name__,
                        attempt + 1,
                        attempts,
                        e,
                        delay,
                    )
                    time.sleep(delay)
            raise last_exc

        return wrapper

    return decorator
