"""
Autonomous multi-portal ingestion agent.

Runs the shared pipeline (scraper/pipeline.py) across every portal this
project scrapes, with per-portal fault isolation: one portal timing out or
erroring never aborts the run for the others. That isolation is the actual
fix for the original complaint that drove this project ("the ingatlanbazar
scraper timed out completely") — a single flaky/unreachable portal no longer
takes the whole `--agent` run down with it; it's logged and skipped, and
whatever portals *did* respond still get ingested.

For each portal, in order:
  1. Try scraper/pipeline.py's try_http_fetch() — a plain HTTP GET, no
     browser at all (see BaseScraper.supports_http_fetch /
     scraper/http_client.py). This is the common case now and needs nothing
     beyond network access.
  2. Only if that's unsupported or fails, lazily launch a single shared
     Playwright browser (human-like behavior — cookie-consent dismissal +
     incremental scrolling, see human_behavior.py) and fall back to the
     DOM-based path for that portal.
A browser is launched at most once per run, and only if some portal actually
needs it — a run where every portal's HTTP path succeeds never touches
Playwright/Chromium at all. If the launch itself fails (missing browser
binary, etc.), that's logged once and every remaining browser-dependent
portal is skipped rather than crashing the whole agent run.

ingatlan.com is deliberately excluded from AGENT_PORTAL_NAMES — see
EXCLUDED_PORTALS below and scraper/README.md. Its robots.txt disallows the
search-result paths (`/lista`, `/szukites`) for every user-agent, and it
runs a commercial anti-bot service (Distil/Imperva) specifically to detect
and block this kind of automated access. Defeating that with a stealth
Playwright context would mean deliberately overriding a protection the site
operator put up and explicitly asked crawlers not to cross — this project
only automates portals that allow it, not portals that have said no.
"""
import logging
from typing import Dict, List, Optional

from app import analyzer, models
from app.database import SessionLocal, init_db
from app.services import valuation_agent
from scraper import playwright_runtime
from scraper.dedup import dedup_properties
from scraper.pipeline import ScrapeResult, run_scrape_with_browser, store_and_analyze, try_http_fetch
from scraper.registry import PORTALS, get_scraper

logger = logging.getLogger(__name__)

# Attempted in this order — cheapest/most-reliable portal first, so a
# partial run (one or more later portals unreachable) still front-loads the
# listings most likely to succeed.
AGENT_PORTAL_NAMES: List[str] = ["jofogas", "otthonterkep", "ingatlanbazar"]

EXCLUDED_PORTALS: Dict[str, str] = {
    "ingatlan.com": (
        "robots.txt disallows /lista and /szukites for every user-agent, and the "
        "site runs Distil/Imperva anti-bot (distil-captcha.html) specifically to "
        "block automated access — not scraped, by design, not a bug. See scraper/README.md."
    ),
}


class _LazyBrowser:
    """
    Launches a single Playwright browser on first use, not eagerly — a run
    where every portal's HTTP path succeeds never starts Chromium at all.
    A failed launch (missing browser binary, etc.) is remembered so it's
    only attempted (and logged) once per run, not once per portal.
    """

    def __init__(self, headless: bool):
        self._headless = headless
        self._playwright_cm = None
        self._browser = None
        self._launch_failed = False

    def get(self):
        if self._browser is not None or self._launch_failed:
            return self._browser
        try:
            from playwright.sync_api import sync_playwright  # local import: only needed when actually used

            playwright_runtime.ensure_subprocess_capable_event_loop()
            self._playwright_cm = sync_playwright()
            p = self._playwright_cm.__enter__()
            self._browser = p.chromium.launch(headless=self._headless)
            logger.info("[agent] Playwright browser launched (lazily, on first portal that needed it)")
        except Exception as e:  # noqa: BLE001 - a broken/missing browser must not crash the agent run
            logger.warning(
                "[agent] Playwright browser unavailable (%s: %s) — any remaining portal that needs it will be skipped",
                type(e).__name__,
                e,
            )
            self._launch_failed = True
            self._close_playwright_cm()
            self._browser = None
        return self._browser

    def _close_playwright_cm(self) -> None:
        if self._playwright_cm is not None:
            try:
                self._playwright_cm.__exit__(None, None, None)
            except Exception:  # noqa: BLE001 - best-effort cleanup
                pass
            self._playwright_cm = None

    def close(self) -> None:
        if self._browser is not None:
            try:
                self._browser.close()
            except Exception:  # noqa: BLE001 - best-effort cleanup
                pass
            self._browser = None
        self._close_playwright_cm()


def run_agent(
    max_listings: int = 150,
    max_pages: int = 9,
    delay_range: tuple = (1.5, 3.5),
    headless: bool = True,
    eur_huf_rate: float = analyzer.DEFAULT_EUR_HUF_RATE,
    ignore_robots: bool = False,
    portal_names: Optional[List[str]] = None,
) -> List[ScrapeResult]:
    """
    Crawl every eligible portal (see AGENT_PORTAL_NAMES) until `max_listings`
    total listings are stored across all of them or every portal has been
    tried. A portal that raises (network failure, timeout, launch error,
    unexpected markup) is logged and skipped — it does not stop the agent
    from trying the remaining portals.
    """
    init_db()
    names = portal_names or AGENT_PORTAL_NAMES
    unknown = [n for n in names if n not in PORTALS]
    if unknown:
        raise ValueError(f"Unknown portal(s) requested for agent run: {unknown}. Valid: {sorted(PORTALS)}")

    results: List[ScrapeResult] = []
    lazy_browser = _LazyBrowser(headless=headless)

    try:
        for portal_name in names:
            remaining = max_listings - sum(1 for r in results if r.stored)
            if remaining <= 0:
                logger.info("[agent] reached max_listings=%d — stopping before portal %s", max_listings, portal_name)
                break

            scraper = get_scraper(portal_name)
            logger.info("[agent] starting portal %s (remaining budget: %d)", portal_name, remaining)

            raws = try_http_fetch(scraper, remaining, max_pages, ignore_robots)
            if raws is not None:
                portal_results = [
                    store_and_analyze(raw, scraper.portal_name, raw.url, eur_huf_rate) for raw in raws
                ]
            else:
                browser = lazy_browser.get()
                if browser is None:
                    logger.warning("[agent] portal %s needs a browser but none is available — skipping", portal_name)
                    continue
                try:
                    portal_results = run_scrape_with_browser(
                        browser,
                        scraper,
                        max_listings=remaining,
                        max_pages=max_pages,
                        delay_range=delay_range,
                        eur_huf_rate=eur_huf_rate,
                        ignore_robots=ignore_robots,
                        human_like=True,
                    )
                except Exception as e:  # noqa: BLE001 - one portal's total failure must not sink the agent run
                    logger.warning("[agent] portal %s failed entirely, skipping: %s: %s", portal_name, type(e).__name__, e)
                    continue

            stored = sum(1 for r in portal_results if r.stored)
            logger.info("[agent] portal %s done: %d/%d stored", portal_name, stored, len(portal_results))
            results.extend(portal_results)
    finally:
        lazy_browser.close()

    found = len(results)
    filtered_anomalies = sum(1 for r in results if r.anomaly)
    stored = sum(1 for r in results if r.stored)

    db = SessionLocal()
    try:
        deduplicated = dedup_properties(db)

        # Underwriting is persisted per-listing during store_and_analyze() above
        # (valuation_agent.validate_and_underwrite_and_persist), so by now every
        # property this scan touched already has its flip ROI verdict on file.
        scanned_ids = [r.property_id for r in results if r.stored and r.property_id is not None]
        passed_hurdle = rejected_sub_hurdle = 0
        if scanned_ids:
            scanned_props = db.query(models.Property).filter(models.Property.id.in_(scanned_ids)).all()
            for prop in scanned_props:
                roi = prop.underwriting_flip_roi_percent
                if roi is None:
                    continue  # not yet underwritten (no benchmark) — not counted either way
                if roi >= valuation_agent.MIN_HURDLE_ROI_PERCENT:
                    passed_hurdle += 1
                else:
                    rejected_sub_hurdle += 1
    finally:
        db.close()

    live_deals_added = max(stored - deduplicated, 0)
    logger.info(
        "[SCAN CYCLE] Found: %d | Filtered Anomalies: %d | Deduplicated: %d | Live Deals Added: %d",
        found,
        filtered_anomalies,
        deduplicated,
        live_deals_added,
    )
    logger.info(
        "[FILTER LOG] Passed %.0f%%+ Hurdle: %d deals | Rejected Sub-%.0f%%: %d deals",
        valuation_agent.MIN_HURDLE_ROI_PERCENT,
        passed_hurdle,
        valuation_agent.MIN_HURDLE_ROI_PERCENT,
        rejected_sub_hurdle,
    )

    return results
