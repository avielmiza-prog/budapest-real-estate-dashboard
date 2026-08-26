"""
Forward geocoding for listings whose portal doesn't already give lat/lng
(jofogas.hu does; otthonterkep.hu/ingatlanbazar.hu likely don't). Uses
OpenStreetMap's Nominatim, the only geocoder that's free and requires no API
key — appropriate for this project's volume, but its usage policy caps
requests at 1/second and requires a real identifying User-Agent, both of
which this module enforces itself rather than trusting callers to.

Results are cached to disk (address -> {lat, lng}) so re-scraping the same
listings doesn't re-geocode them, and a miss/failure falls back to the
listing's district centroid (DistrictBenchmark.centroid_lat/lng) rather than
leaving the property un-mappable.
"""
import json
import logging
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "budapest-apartments-dashboard/1.0 (personal investment research tool)"
MIN_REQUEST_INTERVAL_SECONDS = 1.0  # Nominatim usage policy: max 1 request/second

CACHE_PATH = Path(__file__).resolve().parent / ".geocode_cache.json"

_last_request_at: float = 0.0


def _load_cache() -> dict:
    if not CACHE_PATH.exists():
        return {}
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_cache(cache: dict) -> None:
    try:
        CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as e:  # noqa: BLE001 - a cache write failure shouldn't break geocoding
        logger.warning("Could not write geocode cache: %s", e)


def _throttle() -> None:
    global _last_request_at
    elapsed = time.monotonic() - _last_request_at
    if elapsed < MIN_REQUEST_INTERVAL_SECONDS:
        time.sleep(MIN_REQUEST_INTERVAL_SECONDS - elapsed)
    _last_request_at = time.monotonic()


def geocode_address(address: str, cache: Optional[dict] = None) -> Optional[Tuple[float, float]]:
    """
    Returns (lat, lng) for a free-text address, or None if it couldn't be
    geocoded. `cache` lets a caller doing many lookups in one run share a
    single loaded dict (and save it once at the end) instead of round
    tripping to disk per call — falls back to a fresh load/save otherwise.
    """
    if not address:
        return None

    owns_cache = cache is None
    if cache is None:
        cache = _load_cache()

    key = address.strip().lower()
    if key in cache:
        cached = cache[key]
        return (cached["lat"], cached["lng"]) if cached else None

    query = urllib.parse.urlencode({"q": address, "format": "json", "limit": 1, "countrycodes": "hu"})
    request = urllib.request.Request(f"{NOMINATIM_URL}?{query}", headers={"User-Agent": USER_AGENT})

    result: Optional[Tuple[float, float]] = None
    try:
        _throttle()
        with urllib.request.urlopen(request, timeout=10.0) as response:
            data = json.loads(response.read().decode("utf-8"))
        if data:
            result = (float(data[0]["lat"]), float(data[0]["lon"]))
    except Exception as e:  # noqa: BLE001 - any network/parse failure -> treat as a miss, caller falls back
        logger.warning("Geocoding failed for %r: %s", address, e)

    cache[key] = {"lat": result[0], "lng": result[1]} if result else None
    if owns_cache:
        _save_cache(cache)

    return result
