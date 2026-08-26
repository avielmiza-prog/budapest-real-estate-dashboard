"""
Scraper for otthonterkep.hu.

################################################################################
# IMPORTANT — UNVERIFIED. Browsing to otthonterkep.hu is blocked by this
# session's browsing policy (confirmed: jofogas.hu and google.com both load
# fine from the same session, so it's specific to this domain), so none of
# this — the search URL shape, the JSON-LD field names, the CSS selectors —
# could be checked against the real, live, JS-rendered site.
#
# This follows the same two-layer strategy as scraper/portals/ingatlanbazar.py:
#   1. Try schema.org JSON-LD first (script[type="application/ld+json"]) —
#      a very common SEO convention on Hungarian listing portals regardless
#      of frontend framework, and (if present) far more robust to markup
#      changes than guessed CSS selectors.
#   2. Fall back to the placeholder DOM selectors below.
#
# To finish this before running it for real:
#   1. `pip install playwright playwright-stealth && playwright install chromium`
#   2. Check https://otthonterkep.hu/robots.txt for yourself — do NOT assume
#      it's fine just because this file exists (see scraper/robots.py; the
#      pipeline checks it automatically before crawling, but you should read
#      it yourself for restrictions robotparser doesn't catch).
#   3. Open devtools on a real search-results page and a real listing page:
#      check whether __NEXT_DATA__ or JSON-LD is present (view source, or
#      `document.querySelectorAll('script[type="application/ld+json"]')` in
#      the console) — if so, note the actual field names and adjust
#      _extract_from_json_ld below to match.
#   4. `playwright codegen https://otthonterkep.hu` to get real selectors for
#      SELECTORS below if JSON-LD isn't available or doesn't cover a field.
#   5. Run tests/test_scraper_offline.py-style fixtures against the real
#      saved HTML before trusting this for a real run.
################################################################################
"""
import logging
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

from scraper import json_extract
from scraper import text_parsing as tp
from scraper import url_utils
from scraper.base import BaseScraper, RawListing

logger = logging.getLogger(__name__)

BASE_URL = "https://otthonterkep.hu"

# PLACEHOLDER — confirm the real search-results path/query params.
SEARCH_URL_TEMPLATE = BASE_URL + "/elado+lakas+budapest?page={page}"

SELECTORS = {
    "listing_card_link": "a[href*='/ingatlan/']",  # PLACEHOLDER
    "title": "h1",
    "price": "[class*='price'], [class*='ar-']",
    "size": "[class*='area'], [class*='alapterulet']",
    "rooms": "[class*='room'], [class*='szoba']",
    "address": "[class*='address'], [class*='cim']",
    "condition": "[class*='condition'], [class*='allapot']",
    "description": "[class*='description'], [class*='leiras']",
    "images": "img[src*='/kepek/'], img[data-src*='/kepek/']",
}


def _extract_from_json_ld(page) -> Optional[Dict[str, Any]]:
    """schema.org Product/Offer/RealEstateListing object, if the page embeds one."""
    objects = json_extract.extract_json_ld(page)
    return json_extract.find_by_type(objects, "Product", "RealEstateListing", "Residence", "Offer")


class OtthonterkepScraper(BaseScraper):
    portal_name = "otthonterkep"

    def build_search_url(self, page_number: int) -> str:
        return SEARCH_URL_TEMPLATE.format(page=page_number)

    def extract_listing_urls(self, page) -> List[str]:
        anchors = page.query_selector_all(SELECTORS["listing_card_link"])
        urls: List[str] = []
        for a in anchors:
            href = a.get_attribute("href")
            if href:
                urls.append(url_utils.clean_listing_url(href, base_url=BASE_URL))
        seen = set()
        deduped = []
        for u in urls:
            if u not in seen:
                seen.add(u)
                deduped.append(u)
        return deduped

    def parse_listing_page(self, page, url: str) -> Optional[RawListing]:
        json_ld = _extract_from_json_ld(page)
        if json_ld is not None:
            listing = json_extract.raw_listing_from_json_ld(json_ld, url)
            if listing is not None:
                return listing
            logger.info("JSON-LD present at %s but missing title/price — falling back to DOM selectors", url)

        return _parse_from_dom(page, url)


def _parse_from_dom(page, url: str) -> Optional[RawListing]:
    def text_of(selector: str) -> str:
        el = page.query_selector(selector)
        return el.inner_text().strip() if el else ""

    title = text_of(SELECTORS["title"])
    if not title:
        logger.warning("No title found at %s (JSON-LD and DOM both empty) — page may not be a listing", url)
        return None

    image_urls = []
    for img in page.query_selector_all(SELECTORS["images"]):
        src = img.get_attribute("src") or img.get_attribute("data-src")
        if src:
            image_urls.append(urljoin(BASE_URL, src))

    listing = RawListing(
        url=url,
        title_text=title,
        price_text=text_of(SELECTORS["price"]),
        size_text=text_of(SELECTORS["size"]),
        rooms_text=text_of(SELECTORS["rooms"]),
        address_text=text_of(SELECTORS["address"]),
        condition_text=text_of(SELECTORS["condition"]),
        description_text=text_of(SELECTORS["description"]),
        image_urls=image_urls,
    )

    full_text = page.inner_text("body")
    if not listing.price_text and (tp.parse_price_huf(full_text) or tp.parse_price_eur(full_text)):
        listing.price_text = full_text
    if not listing.size_text and tp.parse_size_sqm(full_text):
        listing.size_text = full_text
    if not listing.rooms_text and tp.parse_rooms(full_text):
        listing.rooms_text = full_text
    if not listing.address_text and tp.extract_district_roman(full_text):
        listing.address_text = full_text

    return listing
