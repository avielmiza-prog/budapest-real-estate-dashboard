"""
Orchestration: launch a stealth-configured Playwright browser, crawl a
portal's search results + listing pages, normalize + store each listing in
the database (upsert by url), then automatically run it through
app.analyzer for a renovation ROI readout.

This is the piece that actually needs network access, so it can't be
exercised end-to-end inside the sandbox this was written in (see the
top-level scraper README) — but every function it calls (text_parsing,
normalize, crud.upsert_property_by_url, analyzer) is independently tested,
and tests/test_pipeline_offline.py drives this file's own logic against a
local HTML fixture via Playwright's file:// support, with no network
involved, to check the wiring end-to-end short of the live goto().
"""
import logging
import random
import time
from dataclasses import dataclass
from typing import List, Optional

from app import analyzer, crud, schemas
from app.database import SessionLocal, init_db
from scraper import geocode, playwright_runtime, robots
from scraper.agent import human_behavior
from scraper.base import BaseScraper, RawListing
from scraper.normalize import normalize_listing
from scraper.retry import with_retry
from scraper.stealth import (
    DEFAULT_EXTRA_HTTP_HEADERS,
    DEFAULT_TIMEOUT_MS,
    DEFAULT_USER_AGENT,
    DEFAULT_VIEWPORT,
    apply_stealth,
)

logger = logging.getLogger(__name__)


@dataclass
class ScrapeResult:
    url: str
    stored: bool
    property_id: Optional[int] = None
    analysis: Optional[dict] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "stored": self.stored,
            "property_id": self.property_id,
            "analysis": self.analysis,
            "error": self.error,
        }


def _polite_sleep(delay_range: tuple) -> None:
    time.sleep(random.uniform(*delay_range))


def _new_stealth_page(browser):
    context = browser.new_context(
        user_agent=DEFAULT_USER_AGENT,
        viewport=DEFAULT_VIEWPORT,
        extra_http_headers=DEFAULT_EXTRA_HTTP_HEADERS,
    )
    context.set_default_timeout(DEFAULT_TIMEOUT_MS)
    context.set_default_navigation_timeout(DEFAULT_TIMEOUT_MS)
    page = context.new_page()
    apply_stealth(page)
    return context, page


@with_retry(attempts=3)
def _goto_with_retry(page, url: str) -> None:
    page.goto(url, timeout=DEFAULT_TIMEOUT_MS, wait_until="domcontentloaded")


def collect_listing_urls(
    browser,
    scraper: BaseScraper,
    max_listings: int,
    max_pages: int,
    delay_range: tuple,
    ignore_robots: bool,
    human_like: bool = False,
) -> List[str]:
    """Paginate through search results, collecting up to max_listings listing URLs."""
    urls: List[str] = []
    context, page = _new_stealth_page(browser)
    try:
        for page_number in range(1, max_pages + 1):
            search_url = scraper.build_search_url(page_number)
            if not ignore_robots:
                robots.check_or_raise(search_url)

            logger.info("[%s] search page %d: %s", scraper.portal_name, page_number, search_url)
            _goto_with_retry(page, search_url)
            if human_like:
                human_behavior.act_human(page)

            page_urls = scraper.extract_listing_urls(page)
            if not page_urls:
                logger.info("[%s] no listings found on page %d — stopping pagination", scraper.portal_name, page_number)
                break

            for u in page_urls:
                if u not in urls:
                    urls.append(u)
                if len(urls) >= max_listings:
                    return urls

            if not scraper.has_next_page(page):
                break
            _polite_sleep(delay_range)
    finally:
        context.close()
    return urls


def collect_bulk_listings(
    browser,
    scraper: BaseScraper,
    max_listings: int,
    max_pages: int,
    delay_range: tuple,
    ignore_robots: bool,
    human_like: bool = False,
) -> List[RawListing]:
    """
    For scrapers with supports_bulk_extraction=True: paginate search-result
    pages, extracting fully-populated RawListings directly from each page's
    own embedded data — no per-listing detail-page visit needed.
    """
    raws: List[RawListing] = []
    seen_urls = set()
    context, page = _new_stealth_page(browser)
    try:
        for page_number in range(1, max_pages + 1):
            search_url = scraper.build_search_url(page_number)
            if not ignore_robots:
                robots.check_or_raise(search_url)

            logger.info("[%s] search page %d: %s", scraper.portal_name, page_number, search_url)
            _goto_with_retry(page, search_url)
            if human_like:
                human_behavior.act_human(page)

            page_raws = scraper.extract_listings_from_search_page(page)
            if not page_raws:
                logger.info("[%s] no listings found on page %d — stopping pagination", scraper.portal_name, page_number)
                break

            for raw in page_raws:
                if raw.url not in seen_urls:
                    seen_urls.add(raw.url)
                    raws.append(raw)
                if len(raws) >= max_listings:
                    return raws

            if not scraper.has_next_page(page):
                break
            _polite_sleep(delay_range)
    finally:
        context.close()
    return raws


def _fill_missing_coordinates(normalized: dict, db) -> None:
    """
    Mutates `normalized` in place: geocodes the address if the portal didn't
    already give lat/lng (jofogas.hu does; others likely don't), falling
    back to the property's district centroid if geocoding fails/misses —
    every mappable listing should end up with *some* pin rather than none.
    """
    if normalized.get("latitude") is not None and normalized.get("longitude") is not None:
        return

    address = normalized.get("address")
    if address:
        coords = geocode.geocode_address(address)
        if coords is not None:
            normalized["latitude"], normalized["longitude"] = coords
            return

    try:
        district_number = analyzer.parse_district_number(normalized.get("district", ""))
    except ValueError:
        return
    benchmark = crud.get_district_benchmark(db, district_number)
    if benchmark is not None and benchmark.centroid_lat is not None and benchmark.centroid_lng is not None:
        normalized["latitude"], normalized["longitude"] = benchmark.centroid_lat, benchmark.centroid_lng


def _store_and_analyze(raw: RawListing, portal_name: str, url: str, eur_huf_rate: float) -> ScrapeResult:
    """Shared tail of both scrape paths: normalize -> geocode -> upsert -> run app.analyzer."""
    normalized = normalize_listing(raw, portal_name)
    if normalized is None:
        return ScrapeResult(url=url, stored=False, error="not enough data to store (missing title/price)")

    db = SessionLocal()
    try:
        _fill_missing_coordinates(normalized, db)
        payload = schemas.PropertyCreate(**normalized)
        prop = crud.upsert_property_by_url(db, payload)

        analysis_dict = None
        analysis_error = None
        try:
            analysis = analyzer.analyze_property_by_id(db, prop.id, eur_huf_rate=eur_huf_rate)
            analysis_dict = analysis.to_dict()
        except (LookupError, ValueError) as e:
            # Missing/unparseable district benchmark shouldn't block storing the listing itself.
            analysis_error = str(e)
            logger.info("No analysis for property %d (%s): %s", prop.id, url, e)

        return ScrapeResult(
            url=url, stored=True, property_id=prop.id, analysis=analysis_dict, error=analysis_error
        )
    finally:
        db.close()


def scrape_one_listing(
    browser,
    scraper: BaseScraper,
    url: str,
    eur_huf_rate: float,
    ignore_robots: bool,
    human_like: bool = False,
) -> ScrapeResult:
    if not ignore_robots and not robots.is_allowed(url):
        return ScrapeResult(url=url, stored=False, error="robots.txt disallows this URL")

    context, page = _new_stealth_page(browser)
    try:
        _goto_with_retry(page, url)
        if human_like:
            human_behavior.dismiss_cookie_consent(page)
        raw = scraper.parse_listing_page(page, url)
    except Exception as e:  # noqa: BLE001 - one bad listing shouldn't kill the whole run
        logger.exception("Failed to load/parse %s", url)
        return ScrapeResult(url=url, stored=False, error=f"{type(e).__name__}: {e}")
    finally:
        context.close()

    if raw is None:
        return ScrapeResult(url=url, stored=False, error="page did not look like a listing")

    return _store_and_analyze(raw, scraper.portal_name, url, eur_huf_rate)


def run_scrape_with_browser(
    browser,
    scraper: BaseScraper,
    max_listings: int = 20,
    max_pages: int = 5,
    delay_range: tuple = (1.5, 3.5),
    eur_huf_rate: float = analyzer.DEFAULT_EUR_HUF_RATE,
    ignore_robots: bool = False,
    human_like: bool = False,
) -> List[ScrapeResult]:
    """
    Same pipeline as run_scrape(), but takes an already-launched Playwright
    browser instead of managing its own — lets a caller (e.g.
    scraper.agent.orchestrator) run several portals back to back in one
    browser session rather than paying Chromium startup cost per portal.
    """
    results: List[ScrapeResult] = []

    if scraper.supports_bulk_extraction:
        raw_listings = collect_bulk_listings(
            browser, scraper, max_listings, max_pages, delay_range, ignore_robots, human_like=human_like
        )
        logger.info(
            "[%s] found %d listings with full data on search pages — no detail-page visits needed",
            scraper.portal_name,
            len(raw_listings),
        )
        for raw in raw_listings:
            result = _store_and_analyze(raw, scraper.portal_name, raw.url, eur_huf_rate)
            results.append(result)
            logger.info("[%s] %s -> stored=%s error=%s", scraper.portal_name, raw.url, result.stored, result.error)
    else:
        listing_urls = collect_listing_urls(
            browser, scraper, max_listings, max_pages, delay_range, ignore_robots, human_like=human_like
        )
        logger.info("[%s] found %d listing URLs to scrape", scraper.portal_name, len(listing_urls))

        for url in listing_urls:
            result = scrape_one_listing(browser, scraper, url, eur_huf_rate, ignore_robots, human_like=human_like)
            results.append(result)
            logger.info("[%s] %s -> stored=%s error=%s", scraper.portal_name, url, result.stored, result.error)
            _polite_sleep(delay_range)

    return results


def run_scrape(
    scraper: BaseScraper,
    max_listings: int = 20,
    max_pages: int = 5,
    delay_range: tuple = (1.5, 3.5),
    headless: bool = True,
    eur_huf_rate: float = analyzer.DEFAULT_EUR_HUF_RATE,
    ignore_robots: bool = False,
    human_like: bool = False,
) -> List[ScrapeResult]:
    """
    Full pipeline for one portal: launch a browser, crawl search results ->
    visit each listing -> normalize -> upsert into the DB -> run
    app.analyzer -> return results.

    Requires network access and a real Playwright browser.
    """
    from playwright.sync_api import sync_playwright  # local import: only needed when actually running

    playwright_runtime.ensure_subprocess_capable_event_loop()
    init_db()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        try:
            return run_scrape_with_browser(
                browser,
                scraper,
                max_listings=max_listings,
                max_pages=max_pages,
                delay_range=delay_range,
                eur_huf_rate=eur_huf_rate,
                ignore_robots=ignore_robots,
                human_like=human_like,
            )
        finally:
            browser.close()
