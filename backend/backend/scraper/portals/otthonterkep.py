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
import re
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

from scraper import json_extract
from scraper import text_parsing as tp
from scraper import url_utils
from scraper.base import BaseScraper, RawListing

logger = logging.getLogger(__name__)

BASE_URL = "https://otthonterkep.hu"

# PLACEHOLDER — confirm the real search-results path/query params.
# Verified live 2026-11-18: "/elado+lakas+budapest?page=N" now returns
# listings from ALL of Hungary and ignores ?page. The Budapest-only search
# is /elado+lakas/budapest, paged with ?p=N (20 per page, ~6,500 flats),
# newest first.
SEARCH_URL_TEMPLATE = BASE_URL + "/elado+lakas/budapest?p={page}&sort=ad_feladas_time%7Cdesc"

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
    # Best-effort: same SELECTORS/JSON-LD-first guesses as the Playwright
    # path below, just fetched via plain HTTP — see fetch_via_http(). This
    # portal's markup is UNVERIFIED either way (module docstring), but
    # scraper/pipeline.py's try_http_fetch() treats any exception here as
    # "fall back to Playwright", so enabling this can never make a run
    # worse than before — only skip Playwright when it happens to work.
    supports_http_fetch = True

    def build_search_url(self, page_number: int) -> str:
        return SEARCH_URL_TEMPLATE.format(page=page_number)

    def fetch_via_http(self, max_listings: int, max_pages: int, ignore_robots: bool = False) -> List[RawListing]:
        """
        Reads the search-result cards (price, size, rooms, floor, district,
        photo: all on the card), and opens a listing's own page only for
        listings not seen before, to get the description and building
        material. Known listings just get their last_seen bumped.
        """
        from scraper import http_client
        from scraper import robots as robots_mod

        raws: List[RawListing] = []
        seen_urls = set()
        new_count = 0
        for page_number in range(1, max_pages + 1):
            search_url = self.build_search_url(page_number)
            if not ignore_robots:
                robots_mod.check_or_raise(search_url)
            html = http_client.fetch_html(search_url)
            cards = parse_search_cards(html)
            if not cards:
                break
            fresh_on_page = 0
            for raw in cards:
                if raw.url in seen_urls:
                    continue
                seen_urls.add(raw.url)
                fresh_on_page += 1
                if raw.url in self.known_urls:
                    self.seen_known_urls.append(raw.url)
                    continue
                time.sleep(1.0)  # polite delay between detail-page fetches
                _enrich_from_detail(raw)
                raws.append(raw)
                new_count += 1
                if new_count >= max_listings:
                    return raws
            if fresh_on_page == 0:
                break  # paging stopped advancing
        return raws

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


def _fetch_listing_via_http(url: str) -> Optional[RawListing]:
    """HTTP+BeautifulSoup mirror of parse_listing_page()/_parse_from_dom() above — see fetch_via_http()."""
    from bs4 import BeautifulSoup

    from scraper import http_client

    try:
        html = http_client.fetch_html(url)
    except http_client.FetchError as e:
        logger.info("Could not fetch %s via HTTP: %s", url, e)
        return None

    json_ld_objects = json_extract.extract_json_ld_from_html(html)
    json_ld = json_extract.find_by_type(json_ld_objects, "Product", "RealEstateListing", "Residence", "Offer")
    if json_ld is not None:
        listing = json_extract.raw_listing_from_json_ld(json_ld, url)
        if listing is not None:
            return listing

    soup = BeautifulSoup(html, "lxml")

    def text_of(selector: str) -> str:
        el = soup.select_one(selector)
        return el.get_text(strip=True) if el else ""

    title = text_of(SELECTORS["title"])
    if not title:
        logger.warning("No title found at %s (JSON-LD and DOM both empty) — page may not be a listing", url)
        return None

    image_urls = []
    for img in soup.select(SELECTORS["images"]):
        src = img.get("src") or img.get("data-src")
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

    full_text = soup.get_text(" ", strip=True)
    if not listing.price_text and (tp.parse_price_huf(full_text) or tp.parse_price_eur(full_text)):
        listing.price_text = full_text
    if not listing.size_text and tp.parse_size_sqm(full_text):
        listing.size_text = full_text
    if not listing.rooms_text and tp.parse_rooms(full_text):
        listing.rooms_text = full_text
    if not listing.address_text and tp.extract_district_roman(full_text):
        listing.address_text = full_text

    return listing


_NUMBER_RE = re.compile(r"(\d[\d\s\u00a0\.]*)(?:[,](\d+))?")


def _first_number(text: str):
    m = re.search(r"\d+(?:[.,]\d+)?", text or "")
    return float(m.group(0).replace(",", ".")) if m else None


def _labelled_value(card_text: str, label: str) -> str:
    m = re.search(label + r"\s*:\s*([^\n]+)", card_text)
    return m.group(1).strip() if m else ""


def parse_search_cards(html: str) -> List[RawListing]:
    """One RawListing per `.card.property` on a search page (markup verified 2026-11-18)."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    out: List[RawListing] = []
    for card in soup.select(".card.property"):
        link = card.select_one("a.card-header-link") or card.select_one("a[href*='/ingatlan/elado+lakas/']")
        if link is None or not link.get("href"):
            continue
        url = url_utils.clean_listing_url(link["href"], base_url=BASE_URL)
        heading = link.get_text(" ", strip=True)  # e.g. "Budapest VIII. kerület Práter utca"
        price_el = card.select_one(".fw-price")
        text = card.get_text("\n", strip=True)
        size_text = _labelled_value(text, "Alapterület")
        rooms_text = _labelled_value(text, "Szobaszám")
        floor_text = _labelled_value(text, "Emelet")
        img = card.select_one("img")
        image_urls = []
        if img is not None:
            src = img.get("src") or img.get("data-src") or ""
            if src and "noimage" not in src:
                image_urls.append(urljoin(BASE_URL, src))
        slug_district = re.search(r"/budapest-([ivx]+)-kerulet/", url, re.I)
        out.append(
            RawListing(
                url=url,
                title_text=heading,
                address_text=heading,
                price_text=price_el.get_text(" ", strip=True) if price_el else "",
                size_sqm_value=_first_number(size_text),
                rooms_value=_first_number(rooms_text),
                district_value=slug_district.group(1).upper() if slug_district else None,
                floor_text=floor_text,
                image_urls=image_urls,
            )
        )
    return out


def _enrich_from_detail(raw: RawListing) -> None:
    """Description (JSON-LD Product, HTML-escaped twice on this site) and building material."""
    import html as html_mod

    from bs4 import BeautifulSoup

    from scraper import http_client

    try:
        page = http_client.fetch_html(raw.url)
    except http_client.FetchError as e:
        logger.info("Could not fetch %s: %s", raw.url, e)
        return
    for obj in json_extract.extract_json_ld_from_html(page):
        if isinstance(obj, dict) and obj.get("@type") == "Product" and obj.get("description"):
            raw.description_text = html_mod.unescape(html_mod.unescape(obj["description"]))
            break
    soup = BeautifulSoup(page, "lxml")
    for li in soup.select("li"):
        t = li.get_text(" ", strip=True)
        if t.startswith("Építőanyag"):
            raw.building_material_text = t.replace("Építőanyag", "").strip()
        elif t.startswith("Lift"):
            v = t.replace("Lift", "").strip().lower()
            raw.has_elevator = True if v.startswith("van") else (False if v.startswith("nincs") else None)
