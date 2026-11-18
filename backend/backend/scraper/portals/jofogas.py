"""
jofogas.hu (ingatlan/real-estate section) — verified via live browser recon
against the real site.

jofogas.hu is a Next.js app whose search-results page embeds COMPLETE
listing data (price, size, rooms, lat/lng, full description, full image
set, district, balcony flag, condition) directly in
`__NEXT_DATA__.props.pageProps.adList.ads[]` — no per-listing detail-page
visit is needed at all (supports_bulk_extraction = True). Detail pages carry
the same shape at `props.pageProps.product`, used here only as a fallback
safety net.

robots.txt notes (checked live, 2026-08-26):
  - The generic `User-agent: *` group — which this scraper's desktop-Chrome
    UA is evaluated against — allows search/listing pages, but disallows
    deep pagination: `/*?o=` is blocked except `o=1` through `o=9`
    (page_size 36 -> 324 listings per search). MAX_ALLOWED_PAGE enforces
    this independently of robots.txt regex parsing, as a second safety net.
  - Separately, robots.txt disallows several NAMED AI/LLM crawlers
    (ClaudeBot, Claude-Web, anthropic-ai, GPTBot, PerplexityBot, etc.) from
    everything except a few static policy pages. This scraper is evaluated
    as a generic browser (User-agent: *), not as one of those named bots.
"""
import logging
import re
from typing import Any, Dict, List, Optional

from scraper import json_extract
from scraper import text_parsing as tp
from scraper import url_utils
from scraper.base import BaseScraper, RawListing

logger = logging.getLogger(__name__)

BASE_URL = "https://www.jofogas.hu"
SEARCH_URL_TEMPLATE = BASE_URL + "/budapest/ingatlan?o={page}"

# robots.txt ('*' group) only allows o=1..9 — deep pagination is disallowed.
MAX_ALLOWED_PAGE = 9

# /budapest/ingatlan is jofogas's general real-estate category — it also
# surfaces offices, land, garages, etc. alongside apartments/houses. The
# whole underwriting model (district HUF/sqm benchmarks, renovation ROI)
# assumes a residential comp, so non-residential categories are filtered
# out here rather than ingested as if they were apartments.
RESIDENTIAL_CATEGORY_NAMES = {"lakás", "ház", "családi ház", "sorház", "ikerház", "nyaraló"}

# The same category nodes (e.g. "lakás") cover both "Eladó" (for sale) and
# "Kiadó" (for rent) listings — a rental's monthly-rent price is orders of
# magnitude below a sale price, and would otherwise get ingested as if it
# were a purchase price and wreck the flip/ROI math. jofogas titles a rental
# with the standalone word "kiadó" somewhere in the subject — either as a
# prefix ("Kiadó ház, Budapest...") or inline ("...lakás kiadó 2020-ban
# épült...") — verified against real stored listings that slipped through
# at rent-sized HUF figures before this filter existed. This platform only
# underwrites purchases, never rentals, so any such listing is excluded.
_RENTAL_WORD_RE = re.compile(r"\bkiad[oó]\b", re.IGNORECASE)


def _is_for_sale(subject: str) -> bool:
    return not _RENTAL_WORD_RE.search(subject)


def _is_residential(ad: Dict[str, Any]) -> bool:
    category_names = {c.get("name", "").strip().lower() for c in (ad.get("category_tree") or [])}
    if not category_names & RESIDENTIAL_CATEGORY_NAMES:
        return False
    return _is_for_sale(ad.get("subject", ""))


def _param(parameters: List[dict], key: str) -> Optional[dict]:
    """First `values[0]` dict for a parameter with this key, e.g. {'value': '97', 'label': '97 m2'}."""
    for p in parameters or []:
        if p.get("key") == key:
            values = p.get("values") or []
            if values:
                return values[0]
    return None


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(str(value).replace(",", "."))
    except ValueError:
        return None


def _best_image_url(image: dict) -> str:
    variations = image.get("image_size_variations") or []
    if variations and variations[0].get("url"):
        return variations[0]["url"]
    return image.get("url", "")


def ad_to_raw_listing(ad: Dict[str, Any]) -> Optional[RawListing]:
    """Turns one `adList.ads[]` (or detail-page `product`) entry into a RawListing."""
    url = ad.get("url")
    subject = ad.get("subject")
    if not url or not subject:
        return None

    price_value = _to_float((ad.get("price") or {}).get("value"))
    parameters = ad.get("parameters") or []

    size_sqm_value = _to_float((_param(parameters, "size") or {}).get("value"))
    rooms_value = _to_float((_param(parameters, "rooms") or {}).get("value"))

    zipcode_param = _param(parameters, "zipcode")
    zipcode_label = zipcode_param.get("label", "") if zipcode_param else ""
    district_value = tp.extract_district_roman(zipcode_label) if zipcode_label else None

    area_param = _param(parameters, "jfg_area")
    address_text = ", ".join(filter(None, [(area_param or {}).get("label", "").strip(), zipcode_label]))

    condition_param = _param(parameters, "realestate_condition")
    condition_text = condition_param.get("label", "") if condition_param else ""

    image_urls = [u for u in (_best_image_url(img) for img in (ad.get("images") or [])) if u]

    return RawListing(
        url=url_utils.clean_listing_url(url, base_url=BASE_URL),
        title_text=subject,
        address_text=address_text,
        description_text=ad.get("body", "") or "",
        condition_text=condition_text,
        image_urls=image_urls,
        price_huf_value=price_value,
        size_sqm_value=size_sqm_value,
        rooms_value=rooms_value,
        district_value=district_value,
        # jofogas.hu only reports balcony presence (yes/no), never a size —
        # leaving balcony_sqm unset rather than guessing one.
        latitude=ad.get("latitude"),
        longitude=ad.get("longitude"),
    )


def _ads_to_raw_listings(ads: List[Dict[str, Any]]) -> List[RawListing]:
    """Shared by both the Playwright and plain-HTTP paths — same adList.ads[] shape either way."""
    raws = []
    for ad in ads:
        if not _is_residential(ad):
            continue
        raw = ad_to_raw_listing(ad)
        if raw is not None:
            raws.append(raw)
        else:
            logger.warning("Skipping malformed jofogas ad (missing url/subject): %r", ad.get("list_id"))
    return raws


class JofogasScraper(BaseScraper):
    portal_name = "jofogas"
    supports_bulk_extraction = True
    supports_http_fetch = True

    def build_search_url(self, page_number: int) -> str:
        return SEARCH_URL_TEMPLATE.format(page=page_number)

    def _pager(self, page) -> dict:
        data = json_extract.extract_next_data(page)
        if not data:
            return {}
        return (data.get("props", {}).get("pageProps", {}).get("adList", {}) or {}).get("pager", {}) or {}

    def has_next_page(self, page) -> bool:
        pager = self._pager(page)
        current_page = pager.get("current_page", 1)
        last_page = pager.get("last_page", current_page)
        return current_page < min(last_page, MAX_ALLOWED_PAGE)

    def extract_listings_from_search_page(self, page) -> List[RawListing]:
        data = json_extract.extract_next_data(page)
        if not data:
            return []
        ads = (data.get("props", {}).get("pageProps", {}).get("adList", {}) or {}).get("ads", [])
        return _ads_to_raw_listings(ads)

    def fetch_via_http(self, max_listings: int, max_pages: int, ignore_robots: bool = False) -> List[RawListing]:
        """
        jofogas.hu server-renders its full Next.js hydration JSON into the
        search-results page's raw HTML (verified live against the real
        site) — a plain HTTP GET gets the same adList.ads[] data
        extract_listings_from_search_page() reads from a Playwright page,
        with no browser involved at all.
        """
        from scraper import http_client, robots as robots_mod

        raws: List[RawListing] = []
        seen_urls = set()
        new_count = 0
        for page_number in range(1, max_pages + 1):
            search_url = self.build_search_url(page_number)
            if not ignore_robots:
                robots_mod.check_or_raise(search_url)

            html = http_client.fetch_html(search_url)
            data = json_extract.extract_next_data_from_html(html)
            if data is None:
                raise http_client.FetchError(
                    f"__NEXT_DATA__ not found on {search_url} — jofogas.hu may no longer server-render it"
                )

            ad_list = data.get("props", {}).get("pageProps", {}).get("adList", {}) or {}
            ads = ad_list.get("ads", [])
            if not ads:
                break

            for raw in _ads_to_raw_listings(ads):
                if raw.url in seen_urls:
                    continue
                seen_urls.add(raw.url)
                # Search pages already carry every field, so known listings
                # are re-stored too (cheap, and catches price changes), but
                # only NEW listings count against the budget.
                raws.append(raw)
                if raw.url not in self.known_urls:
                    new_count += 1
                if new_count >= max_listings:
                    return raws

            pager = ad_list.get("pager", {}) or {}
            current_page = pager.get("current_page", page_number)
            last_page = pager.get("last_page", current_page)
            if current_page >= min(last_page, MAX_ALLOWED_PAGE):
                break
        return raws

    def extract_listing_urls(self, page) -> List[str]:
        return [raw.url for raw in self.extract_listings_from_search_page(page)]

    def parse_listing_page(self, page, url: str) -> Optional[RawListing]:
        """
        Fallback only — bulk extraction above already covers every listing
        found via search. Detail pages carry the same ad shape at
        props.pageProps.product (confirmed via live recon).
        """
        data = json_extract.extract_next_data(page)
        if not data:
            return None
        product = data.get("props", {}).get("pageProps", {}).get("product")
        if not product:
            return None
        return ad_to_raw_listing(product)
