"""
Autonomous multi-portal ingestion agent.

Runs the shared pipeline (scraper/pipeline.py) across every portal this
project scrapes, back to back in one Chromium session, with human-like page
behavior (cookie-consent dismissal + incremental scrolling — see
human_behavior.py) and per-portal fault isolation: one portal timing out or
erroring never aborts the run for the others. That isolation is the actual
fix for the original complaint that drove this project ("the ingatlanbazar
scraper timed out completely") — a single flaky/unreachable portal no longer
takes the whole `--agent` run down with it; it's logged and skipped, and
whatever portals *did* respond still get ingested.

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

from app import analyzer
from app.database import init_db
from scraper import playwright_runtime
from scraper.pipeline import ScrapeResult, run_scrape_with_browser
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


def run_agent(
    max_listings: int = 30,
    max_pages: int = 5,
    delay_range: tuple = (1.5, 3.5),
    headless: bool = True,
    eur_huf_rate: float = analyzer.DEFAULT_EUR_HUF_RATE,
    ignore_robots: bool = False,
    portal_names: Optional[List[str]] = None,
) -> List[ScrapeResult]:
    """
    Crawl every eligible portal (see AGENT_PORTAL_NAMES) in one browser
    session until `max_listings` total listings are stored across all of
    them or every portal has been tried. A portal that raises (network
    failure, timeout, launch error, unexpected markup) is logged and
    skipped — it does not stop the agent from trying the remaining portals.
    """
    from playwright.sync_api import sync_playwright  # local import: only needed when actually running

    playwright_runtime.ensure_subprocess_capable_event_loop()
    init_db()
    names = portal_names or AGENT_PORTAL_NAMES
    unknown = [n for n in names if n not in PORTALS]
    if unknown:
        raise ValueError(f"Unknown portal(s) requested for agent run: {unknown}. Valid: {sorted(PORTALS)}")

    results: List[ScrapeResult] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        try:
            for portal_name in names:
                remaining = max_listings - sum(1 for r in results if r.stored)
                if remaining <= 0:
                    logger.info("[agent] reached max_listings=%d — stopping before portal %s", max_listings, portal_name)
                    break

                scraper = get_scraper(portal_name)
                logger.info("[agent] starting portal %s (remaining budget: %d)", portal_name, remaining)
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
            browser.close()

    return results
