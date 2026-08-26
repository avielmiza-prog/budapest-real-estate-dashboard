"""
Reference scraper for ingatlanbazar.hu.

Why this portal: its robots.txt (checked 2026-08-25) disallows only
/hitel-kereses, /fiokom, /admin, /magazin/kereses, /magazin/hirdetesek and
/magazin/publicapi/ — it does NOT disallow listing search or detail pages,
unlike ingatlan.com (whose robots.txt blocks /lista and /szukites outright
and which runs a dedicated anti-bot/captcha service specifically to stop
this kind of automated access — see the top-level scraper README before
even considering pointing this at ingatlan.com).

################################################################################
# IMPORTANT — SELECTORS BELOW ARE BEST-EFFORT PLACEHOLDERS, NOT VERIFIED.
#
# This code runs in a sandboxed environment with no general internet access
# (only a short allowlist of package registries and dev-tool hosts — even a
# plain Playwright page.goto() to an arbitrary site fails here). So none of
# the CSS selectors below could be checked against the live, JS-rendered
# ingatlanbazar.hu DOM. They're informed guesses based on common Hungarian
# listing-portal markup conventions, wired into a SELECTORS dict specifically
# so they're easy to correct in one place.
#
# To finish this before running it for real:
#   1. `pip install playwright playwright-stealth && playwright install chromium`
#   2. `playwright codegen https://ingatlanbazar.hu` (or your target search
#      URL) — click around, and the codegen inspector shows you the real
#      selector for each element you click.
#   3. Update SELECTORS below to match. Everything else (pagination loop,
#      stealth, rate limiting, DB upsert, analyzer hookup) doesn't need to
#      change.
#
# As a safety net, parse_listing_page() also runs the regex-based
# text_parsing helpers over the whole page's visible text, so even a
# slightly-off selector for one field often doesn't lose that field
# entirely — see _fallback_from_full_text().
################################################################################

UPDATE (this upgrade): parse_listing_page now tries schema.org JSON-LD
(script[type="application/ld+json"]) first — a common SEO convention this
portal may already emit regardless of the above, and (if present) more
robust to markup changes than the CSS guesses below. Falls back to the
SELECTORS-based DOM parse, unchanged, when no usable JSON-LD is found. This
doesn't resolve the "unverified" status above — it just gives the scraper a
second, likely-more-durable way to succeed once it's pointed at the real site.
"""
import logging
from typing import List, Optional
from urllib.parse import urljoin

from scraper import json_extract
from scraper import text_parsing as tp
from scraper import url_utils
from scraper.base import BaseScraper, RawListing

logger = logging.getLogger(__name__)

BASE_URL = "https://ingatlanbazar.hu"

# PLACEHOLDER — confirm the real search-results path/query params via codegen.
# This guess follows the "/<listing-type>/<city>?page=N" shape common on
# Hungarian portals; ingatlanbazar.hu's actual routing may differ.
SEARCH_URL_TEMPLATE = BASE_URL + "/elado-lakas/budapest?oldal={page}"

# Centralized so a markup change is a one-line fix, not a hunt through the code.
SELECTORS = {
    "listing_card_link": "a[href*='/hirdetes/']",  # PLACEHOLDER: card -> detail page link
    "title": "h1",
    "price": "[class*='price'], [class*='ar-']",
    "size": "[class*='area'], [class*='alapterulet']",
    "rooms": "[class*='room'], [class*='szoba']",
    "address": "[class*='address'], [class*='cim']",
    "condition": "[class*='condition'], [class*='allapot']",
    "description": "[class*='description'], [class*='leiras']",
    "images": "img[src*='/uploads/'], img[data-src*='/uploads/']",
}


class IngatlanbazarScraper(BaseScraper):
    portal_name = "ingatlanbazar"

    def build_search_url(self, page_number: int) -> str:
        return SEARCH_URL_TEMPLATE.format(page=page_number)

    def extract_listing_urls(self, page) -> List[str]:
        anchors = page.query_selector_all(SELECTORS["listing_card_link"])
        urls: List[str] = []
        for a in anchors:
            href = a.get_attribute("href")
            if not href:
                continue
            # Absolute + tracking-params-stripped, so every stored listing
            # URL points at the exact canonical page (see scraper/url_utils.py).
            urls.append(url_utils.clean_listing_url(href, base_url=BASE_URL))
        # de-dupe while preserving order (a card's link often appears twice: image + title)
        seen = set()
        deduped = []
        for u in urls:
            if u not in seen:
                seen.add(u)
                deduped.append(u)
        return deduped

    def parse_listing_page(self, page, url: str) -> Optional[RawListing]:
        json_ld_objects = json_extract.extract_json_ld(page)
        json_ld = json_extract.find_by_type(json_ld_objects, "Product", "RealEstateListing", "Residence", "Offer")
        if json_ld is not None:
            listing = json_extract.raw_listing_from_json_ld(json_ld, url)
            if listing is not None:
                return listing
            logger.info("JSON-LD present at %s but missing title/price — falling back to DOM selectors", url)

        return self._parse_from_dom(page, url)

    def _parse_from_dom(self, page, url: str) -> Optional[RawListing]:
        def text_of(selector: str) -> str:
            el = page.query_selector(selector)
            return el.inner_text().strip() if el else ""

        title = text_of(SELECTORS["title"])
        if not title:
            logger.warning("No title found at %s — page may not be a listing (404/redirect?)", url)
            return None

        # Only genuine photo URLs found on the listing page itself go in here.
        # Deliberately no fallback to a stock/placeholder image service if a
        # listing has no photos — an empty list is the correct, honest result
        # in that case (see normalize.py, which passes it through as-is).
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

        # Safety net: if any selector-based field came up empty, try to
        # recover it from the whole page's visible text instead.
        full_text = page.inner_text("body")
        _fill_gaps_from_full_text(listing, full_text)
        return listing


def _fill_gaps_from_full_text(listing: RawListing, full_text: str) -> None:
    """Mutates `listing` in place, filling only fields that came up empty."""
    if not listing.price_text and (tp.parse_price_huf(full_text) or tp.parse_price_eur(full_text)):
        listing.price_text = full_text
    if not listing.size_text and tp.parse_size_sqm(full_text):
        listing.size_text = full_text
    if not listing.rooms_text and tp.parse_rooms(full_text):
        listing.rooms_text = full_text
    if not listing.address_text and tp.extract_district_roman(full_text):
        listing.address_text = full_text
