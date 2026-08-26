"""
Lightweight HTTP fetching for portals whose listing data is present in the
server-rendered HTML — no JS execution, no browser process needed at all.
Verified true for jofogas.hu's search-results pages (its Next.js hydration
JSON is already in the raw response — see scraper/portals/jofogas.py).

This is the whole point: a plain HTTP GET is orders of magnitude cheaper
than launching Chromium, and removes Playwright's browser binary as a hard
requirement for a deploy to work at all (see render.yaml's build-command
history in this repo for how much friction that caused). Playwright is kept
as an explicit fallback in scraper/pipeline.py and scraper/agent/orchestrator.py
for portals/pages this can't handle — this module only fetches raw HTML/text,
it never tries to run JS itself.

Primary path: httpx with realistic browser headers. If that comes back
403/429 — bot-detection blocking on TLS fingerprint rather than headers,
which is common on Cloudflare-fronted sites — retries once via curl_cffi,
which impersonates a real Chrome TLS handshake (httpx/Python's `ssl` module
can't do this; its handshake is trivially distinguishable from a browser's).
"""
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "hu-HU,hu;q=0.9,en-US;q=0.8,en;q=0.7",
}

# Statuses worth retrying with a real-browser TLS fingerprint before giving
# up — anything else (404, 500, ...) is a real error curl_cffi won't fix.
_BOT_BLOCKED_STATUS_CODES = {403, 429}

DEFAULT_TIMEOUT_SECONDS = 15.0


class FetchError(Exception):
    """Raised when a URL couldn't be fetched as plain HTML by any available method — signals 'try the Playwright fallback'."""


def fetch_html(url: str, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> str:
    """
    GET `url` and return its response body as text. Raises FetchError if
    neither httpx nor the curl_cffi fallback could get a usable page —
    callers should treat that as "this portal/page needs Playwright now."
    """
    try:
        response = httpx.get(url, headers=DEFAULT_HEADERS, follow_redirects=True, timeout=timeout)
    except httpx.HTTPError as e:
        logger.info("httpx fetch of %s failed (%s) — trying curl_cffi", url, e)
        return _fetch_html_via_curl_cffi_or_raise(url, timeout, reason=str(e))

    if response.status_code in _BOT_BLOCKED_STATUS_CODES:
        logger.info("httpx fetch of %s got HTTP %d — retrying with curl_cffi's browser TLS fingerprint", url, response.status_code)
        return _fetch_html_via_curl_cffi_or_raise(url, timeout, reason=f"HTTP {response.status_code}")

    if response.status_code >= 400:
        raise FetchError(f"GET {url} -> HTTP {response.status_code}")

    return response.text


def _fetch_html_via_curl_cffi_or_raise(url: str, timeout: float, reason: str) -> str:
    html = _try_curl_cffi(url, timeout)
    if html is None:
        raise FetchError(f"GET {url} failed via httpx ({reason}) and curl_cffi fallback also failed/unavailable")
    return html


def _try_curl_cffi(url: str, timeout: float) -> Optional[str]:
    try:
        from curl_cffi import requests as curl_requests
    except ImportError:
        logger.warning("curl_cffi not installed — can't retry %s with a real browser TLS fingerprint", url)
        return None
    try:
        response = curl_requests.get(url, impersonate="chrome124", timeout=timeout)
    except Exception as e:  # noqa: BLE001 - any curl_cffi/network failure just means "no luck", not a crash
        logger.warning("curl_cffi fetch of %s failed: %s", url, e)
        return None
    if response.status_code >= 400:
        logger.warning("curl_cffi fetch of %s -> HTTP %d", url, response.status_code)
        return None
    return response.text
