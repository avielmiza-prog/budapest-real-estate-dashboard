"""
Fast, instant-parse extraction from a page's embedded JSON — no DOM
traversal needed. Two shapes are common enough across Hungarian real-estate
portals to share here:

  - Next.js hydration data (`<script id="__NEXT_DATA__" type="application/json">`)
    — used by jofogas.hu, and by many modern-stack listing sites generally.
  - JSON-LD structured data (`<script type="application/ld+json">`), a
    schema.org convention many portals embed for SEO regardless of their
    frontend framework — a good first thing to try on any portal before
    falling back to CSS selectors.

Both just read already-loaded page content (no extra network requests), so
trying them first is strictly cheaper than a DOM query, not just more robust
to markup changes.
"""
import json
import logging
import re
from typing import Any, Dict, List, Optional

from scraper.base import RawListing
from scraper.url_utils import clean_listing_url

logger = logging.getLogger(__name__)

_NEXT_DATA_HTML_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.DOTALL
)
_JSON_LD_HTML_RE = re.compile(
    r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.DOTALL | re.IGNORECASE
)


def extract_next_data_from_html(html: str) -> Optional[Dict[str, Any]]:
    """
    Same as extract_next_data, but reads straight from a raw HTML string —
    no Playwright page needed. Works whenever a site server-renders its
    Next.js hydration data into the initial response (verified true for
    jofogas.hu's search-results pages), which is the common case for
    Next.js SSR/SSG pages regardless of what runs client-side afterward.
    """
    match = _NEXT_DATA_HTML_RE.search(html)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError as e:
        logger.warning("__NEXT_DATA__ present but not valid JSON: %s", e)
        return None


def extract_json_ld_from_html(html: str) -> List[Dict[str, Any]]:
    """HTML-string counterpart to extract_json_ld — see its docstring."""
    results: List[Dict[str, Any]] = []
    for raw in _JSON_LD_HTML_RE.findall(html):
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, list):
            results.extend(item for item in parsed if isinstance(item, dict))
        elif isinstance(parsed, dict):
            if isinstance(parsed.get("@graph"), list):
                results.extend(item for item in parsed["@graph"] if isinstance(item, dict))
            else:
                results.append(parsed)
    return results


def extract_next_data(page) -> Optional[Dict[str, Any]]:
    """Reads and parses `#__NEXT_DATA__`'s JSON contents. None if absent/unparseable."""
    try:
        raw = page.eval_on_selector("script#__NEXT_DATA__", "el => el.textContent")
    except Exception as e:  # noqa: BLE001 - selector not present, or page has no JS DOM at all
        logger.debug("No __NEXT_DATA__ script found: %s", e)
        return None
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        logger.warning("__NEXT_DATA__ present but not valid JSON: %s", e)
        return None


def extract_json_ld(page) -> List[Dict[str, Any]]:
    """
    Reads every `script[type="application/ld+json"]` on the page and returns
    the parsed objects (flattening any top-level @graph/array wrappers).
    Empty list if none are present or none parse.
    """
    try:
        raw_scripts: List[str] = page.eval_on_selector_all(
            'script[type="application/ld+json"]', "els => els.map(e => e.textContent)"
        )
    except Exception as e:  # noqa: BLE001
        logger.debug("No JSON-LD scripts found: %s", e)
        return []

    results: List[Dict[str, Any]] = []
    for raw in raw_scripts:
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, list):
            results.extend(item for item in parsed if isinstance(item, dict))
        elif isinstance(parsed, dict):
            if isinstance(parsed.get("@graph"), list):
                results.extend(item for item in parsed["@graph"] if isinstance(item, dict))
            else:
                results.append(parsed)
    return results


def find_by_type(objects: List[Dict[str, Any]], *types: str) -> Optional[Dict[str, Any]]:
    """First JSON-LD object whose @type matches one of `types` (case-sensitive, schema.org convention)."""
    for obj in objects:
        obj_type = obj.get("@type")
        if obj_type in types or (isinstance(obj_type, list) and any(t in types for t in obj_type)):
            return obj
    return None


def raw_listing_from_json_ld(obj: Dict[str, Any], url: str) -> Optional[RawListing]:
    """
    Best-effort conversion of a schema.org Product/Offer/RealEstateListing
    JSON-LD object into a RawListing. Shared by any portal that embeds this
    fairly standard SEO markup, so each portal module doesn't reimplement
    the same offers/address/image unwrapping. Returns None if the object is
    missing even a title (`name`) — not worth treating as a listing.
    """
    title = obj.get("name")
    if not title:
        return None

    offers = obj.get("offers") or {}
    price = offers.get("price") if isinstance(offers, dict) else None
    price_currency = offers.get("priceCurrency") if isinstance(offers, dict) else None

    price_huf_value = None
    price_eur_value = None
    if price is not None:
        try:
            price_number = float(price)
            if price_currency == "EUR":
                price_eur_value = price_number
            else:
                price_huf_value = price_number
        except (TypeError, ValueError):
            pass

    address_obj = obj.get("address") or {}
    address_text = address_obj.get("streetAddress", "") if isinstance(address_obj, dict) else str(address_obj)

    images = obj.get("image")
    if isinstance(images, str):
        image_urls = [images]
    elif isinstance(images, list):
        image_urls = [i for i in images if isinstance(i, str)]
    else:
        image_urls = []

    return RawListing(
        url=clean_listing_url(url),
        title_text=title,
        address_text=address_text,
        description_text=obj.get("description", "") or "",
        image_urls=image_urls,
        price_huf_value=price_huf_value,
        price_eur_value=price_eur_value,
    )
