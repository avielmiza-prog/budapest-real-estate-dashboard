"""
robots.txt safety rail. The pipeline checks this before crawling any URL and
skips (with a warning) anything disallowed, unless the caller explicitly
opts out with ignore_robots=True.

This is a courtesy default, not a hard technical restriction — you can turn
it off — but the intent is to make "this portal said no" a conscious,
visible choice rather than something that happens silently.
"""
import logging
import urllib.robotparser
from functools import lru_cache
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


@lru_cache(maxsize=32)
def _get_parser(robots_url: str) -> urllib.robotparser.RobotFileParser:
    parser = urllib.robotparser.RobotFileParser()
    parser.set_url(robots_url)
    parser.read()
    return parser


def is_allowed(url: str, user_agent: str = "*") -> bool:
    """
    True if robots.txt for the URL's host allows fetching it (or if
    robots.txt can't be fetched/parsed at all — fail open, since a missing
    robots.txt conventionally means "no restrictions").
    """
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        parser = _get_parser(robots_url)
        return parser.can_fetch(user_agent, url)
    except Exception as e:  # noqa: BLE001 - genuinely want to fail open on any parse/network error
        logger.warning("Could not fetch/parse %s (%s) — assuming allowed.", robots_url, e)
        return True


def check_or_raise(url: str, user_agent: str = "*") -> None:
    if not is_allowed(url, user_agent):
        raise PermissionError(
            f"robots.txt disallows fetching {url!r} for user-agent {user_agent!r}. "
            "Pass ignore_robots=True to override this (see scraper/pipeline.py) — "
            "make sure you actually want to override the site's stated wishes first."
        )
