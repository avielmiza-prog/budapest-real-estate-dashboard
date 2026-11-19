"""
Turns a portal-specific RawListing into the dict shape app.schemas.PropertyCreate
expects. Kept separate from both the portal modules (which shouldn't need to
know about the DB schema) and the pipeline (which shouldn't need to know
about text parsing).
"""
import logging
from typing import Optional

import re

from app.building_classifier import (
    BUILDING_TYPE_BRICK_CLASSICAL,
    BUILDING_TYPE_NEW_BUILD,
    BUILDING_TYPE_PANEL_BLOCK,
    classify_building_type,
    extract_ceiling_height_m,
)
from app.sub_district import extract_sub_district
from scraper import text_parsing as tp
from scraper import url_utils
from scraper.base import RawListing

logger = logging.getLogger(__name__)


# Only explicit, whole-flat condition phrases. A bare "felújított" is too
# loose ("felújított fürdőszoba" says nothing about the rest of the flat).
_CONDITION_FROM_TEXT = [
    ("Felújítandó", re.compile(r"felújítandó|felujitando|felújításra szorul|felujitasra szorul|felújításra vár|lakhatatlan|romos", re.I)),
    ("Felújított", re.compile(r"(teljes(?:\s|-)?körűen|teljesen|frissen|újonnan|nemrég|most)\s+felújított|kulcsrakész|újszerű állapot", re.I)),
    ("Átlagos", re.compile(r"átlagos állapot|jó állapotú|lakható állapot", re.I)),
]


def infer_condition_from_text(text: str) -> str:
    """Condition label from description text, or "" when nothing explicit is said."""
    for label, pattern in _CONDITION_FROM_TEXT:
        if pattern.search(text or ""):
            return label
    return ""


def _building_type_from_material(material: str):
    m = (material or "").lower()
    if "panel" in m:
        return BUILDING_TYPE_PANEL_BLOCK
    if "új" in m and "épít" in m:
        return BUILDING_TYPE_NEW_BUILD
    if "tégla" in m or "tegla" in m:
        return BUILDING_TYPE_BRICK_CLASSICAL
    return None


def normalize_listing(raw: RawListing, portal_name: str) -> Optional[dict]:
    """
    Returns a dict with keys matching app.schemas.PropertyCreate, or None if
    the listing is missing so much data it isn't worth storing (no title, or
    no price at all).
    """
    if not raw.title_text:
        logger.warning("Dropping %s: no title", raw.url)
        return None

    # Portals with structured (JSON) data set the *_value overrides directly,
    # skipping a lossy round-trip through the text regexes below.
    price_huf = raw.price_huf_value if raw.price_huf_value is not None else tp.parse_price_huf(raw.price_text)
    price_eur = raw.price_eur_value if raw.price_eur_value is not None else tp.parse_price_eur(raw.price_text)
    if price_huf is None and price_eur is None:
        logger.warning("Dropping %s: no parseable price", raw.url)
        return None

    size_sqm = raw.size_sqm_value if raw.size_sqm_value is not None else tp.parse_size_sqm(raw.size_text)
    rooms = raw.rooms_value if raw.rooms_value is not None else tp.parse_rooms(raw.rooms_text)
    district = (
        raw.district_value
        or tp.extract_district_roman(raw.address_text)
        or tp.extract_district_roman(raw.description_text)
    )
    if district is None:
        logger.warning("%s: could not determine district from address/description", raw.url)

    price_per_sqm = None
    if price_huf and size_sqm:
        price_per_sqm = round(price_huf / size_sqm, 2)

    # Sub-market precision fields — best-effort keyword extraction from
    # whatever free text the portal gave us (title/description carry these
    # signals far more often than the structured address field). See
    # app.building_classifier / app.sub_district for the matching rules.
    combined_text = " ".join(
        filter(None, [raw.title_text, raw.description_text, raw.condition_text])
    )
    building_type = _building_type_from_material(raw.building_material_text) or classify_building_type(combined_text)
    condition_text = raw.condition_text or infer_condition_from_text(raw.description_text)
    ceiling_height_m = extract_ceiling_height_m(combined_text)
    sub_district = extract_sub_district(
        " ".join(filter(None, [raw.address_text, raw.title_text, raw.description_text])),
        district,
    )

    return {
        "title": raw.title_text,
        "district": district or "unknown",
        "address": raw.address_text or None,
        "size_sqm": size_sqm,
        "rooms": rooms,
        "price_huf": price_huf,
        "price_eur": price_eur,
        "price_per_sqm": price_per_sqm,
        # Idempotent safety net: the portal module should already have
        # returned an absolute, tracking-param-free URL, but clean it again
        # here so every portal is covered even if a future one forgets.
        "url": url_utils.clean_listing_url(raw.url),
        "condition": condition_text or None,
        # Whatever the portal module actually found in the page's <img>/data-src
        # attributes, and nothing else — no stock-photo/placeholder fallback.
        # RawListing.image_urls defaults to [], so a listing with no real
        # photos on the page stores an empty array here, never None and never
        # a generated image.
        "images": raw.image_urls,
        "portal": portal_name,
        "latitude": raw.latitude,
        "longitude": raw.longitude,
        # Never fabricated: only set when the portal itself reports a real
        # balcony/terrace size. A boolean "has balcony" flag with no size
        # (e.g. jofogas.hu) is not enough to populate this.
        "balcony_sqm": raw.balcony_sqm,
        "building_type": building_type,
        "ceiling_height_m": ceiling_height_m,
        "sub_district": sub_district,
        "description": (raw.description_text or "")[:6000] or None,
        "floor": raw.floor_text or None,
        "has_elevator": raw.has_elevator,
    }
