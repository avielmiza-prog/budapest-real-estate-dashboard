"""
Live EUR->HUF exchange rate, fetched from frankfurter.app (ECB reference
rates, free, no API key) and cached in-memory for FX_CACHE_TTL_SECONDS so
every page load doesn't re-hit the external API. The frontend pre-fills its
editable rate input from this, but the user can always override manually —
this is a convenience default, not an authoritative source of truth for a
real transaction.
"""
import datetime
import json
import logging
import urllib.request
from typing import Optional

from app.analyzer import DEFAULT_EUR_HUF_RATE

logger = logging.getLogger(__name__)

FX_API_URL = "https://api.frankfurter.app/latest?from=EUR&to=HUF"
FX_CACHE_TTL_SECONDS = 3600
FX_SOURCE_LABEL = "frankfurter.app (ECB reference rate)"

_cache: dict = {"rate": None, "fetched_at": None}


def _fetch_live_rate() -> Optional[float]:
    try:
        request = urllib.request.Request(
            FX_API_URL, headers={"User-Agent": "budapest-apartments-dashboard/1.0"}
        )
        with urllib.request.urlopen(request, timeout=5.0) as response:
            data = json.loads(response.read().decode("utf-8"))
        return float(data["rates"]["HUF"])
    except Exception as e:  # noqa: BLE001 - any network/parse failure should fall back gracefully
        logger.warning("Could not fetch live EUR/HUF rate from %s: %s", FX_API_URL, e)
        return None


def get_fx_rate(force_refresh: bool = False) -> dict:
    """
    Returns {"rate", "updated_at", "source", "is_live"}. Serves the
    in-memory cache when it's fresh (< FX_CACHE_TTL_SECONDS old); refetches
    otherwise. Falls back to analyzer.DEFAULT_EUR_HUF_RATE (is_live=False)
    if the live fetch fails and there's no usable cached value yet.
    """
    now = datetime.datetime.utcnow()
    is_stale = (
        _cache["rate"] is None
        or _cache["fetched_at"] is None
        or (now - _cache["fetched_at"]).total_seconds() > FX_CACHE_TTL_SECONDS
    )

    if force_refresh or is_stale:
        live_rate = _fetch_live_rate()
        if live_rate is not None:
            _cache["rate"] = live_rate
            _cache["fetched_at"] = now

    if _cache["rate"] is not None:
        return {
            "rate": _cache["rate"],
            "updated_at": _cache["fetched_at"].isoformat() + "Z",
            "source": FX_SOURCE_LABEL,
            "is_live": True,
        }

    return {
        "rate": DEFAULT_EUR_HUF_RATE,
        "updated_at": now.isoformat() + "Z",
        "source": "fallback default (live fetch unavailable)",
        "is_live": False,
    }
