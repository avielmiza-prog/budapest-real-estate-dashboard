"""
URL hygiene shared by every portal scraper: resolve relative links to
absolute URLs, and strip tracking query parameters so the URL stored as a
listing's `url`/`source_url` points straight at the canonical listing page.
"""
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

# Denylist, not "strip everything" — some portals use meaningful query
# params (e.g. a listing variant/unit id) that must survive cleaning.
_TRACKING_PARAM_PREFIXES = ("utm_",)
_TRACKING_PARAMS = {
    "fbclid",
    "gclid",
    "gclsrc",
    "msclkid",
    "yclid",
    "mc_cid",
    "mc_eid",
    "igshid",
    "ref",
    "referrer",
    "source",
    "campaign",
    "_ga",
    "_gl",
    "sessionid",
    "sid",
    "phpsessid",
}


def _is_tracking_param(key: str) -> bool:
    key_lower = key.lower()
    return key_lower in _TRACKING_PARAMS or key_lower.startswith(_TRACKING_PARAM_PREFIXES)


def clean_listing_url(url: str, base_url: Optional[str] = None) -> str:
    """
    Normalize a scraped listing URL:
      - resolve it against `base_url` if it's relative
        (e.g. "/ingatlan/123" + "https://example.com" -> "https://example.com/ingatlan/123")
      - drop tracking query parameters (utm_*, fbclid, gclid, ...) so the
        stored URL points directly at the canonical listing page, not a
        particular ad-campaign click-through variant of it.

    A URL that's already absolute and already clean passes through unchanged
    (this is idempotent — safe to call more than once on the same value, e.g.
    once in a portal module and again as a shared safety net in normalize.py).
    """
    if not url:
        return url

    if base_url:
        url = urljoin(base_url, url)

    parts = urlsplit(url)
    kept_params = [
        (key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True) if not _is_tracking_param(key)
    ]
    cleaned_query = urlencode(kept_params)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, cleaned_query, parts.fragment))
