"""
CLI entrypoint.

    python -m scraper.run --portal ingatlanbazar --max-listings 20 --eur-huf-rate 400

Autonomous multi-portal agent (see scraper/agent/orchestrator.py) — crawls
every eligible portal back to back in one browser session, with human-like
behavior and per-portal fault isolation, until max-listings is reached or
every portal has been tried:

    python -m scraper.run --agent --max-listings 30

Clearing out fake/demo data (see scripts/seed_data.py) before or instead of
a real scrape:

    python -m scraper.run --portal ingatlanbazar --clear-mock   # clear, then scrape
    python -m scraper.run --clear-mock-only                     # clear only, no scrape/browser

Requires: pip install playwright playwright-stealth && playwright install chromium
(playwright-stealth is optional — see scraper/stealth.py's manual fallback).
"""
import argparse
import json
import logging
import sys

from app.analyzer import DEFAULT_EUR_HUF_RATE
from scraper.agent.orchestrator import run_agent
from scraper.pipeline import run_scrape
from scraper.registry import PORTALS, get_scraper


def _clear_mock_data() -> int:
    """Delete every mock/demo Property row (see app.crud.MOCK_URL_PREFIX). Returns the count deleted."""
    from app import crud
    from app.database import SessionLocal, init_db

    init_db()
    db = SessionLocal()
    try:
        return crud.delete_properties_with_url_prefix(db, crud.MOCK_URL_PREFIX)
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Scrape a Budapest real-estate portal into the DB.")
    parser.add_argument(
        "--portal",
        choices=sorted(PORTALS),
        help="Which single portal to scrape. Required unless --agent or --clear-mock-only is given.",
    )
    parser.add_argument(
        "--agent",
        action="store_true",
        help="Run the autonomous multi-portal agent instead of a single --portal "
        "(see scraper/agent/orchestrator.py — human-like behavior, per-portal fault isolation).",
    )
    parser.add_argument("--max-listings", type=int, default=150, help="Stop after this many listings.")
    parser.add_argument("--max-pages", type=int, default=20, help="Stop after this many search-result pages.")
    parser.add_argument("--min-delay", type=float, default=1.5, help="Minimum seconds between requests.")
    parser.add_argument("--max-delay", type=float, default=3.5, help="Maximum seconds between requests.")
    parser.add_argument("--eur-huf-rate", type=float, default=DEFAULT_EUR_HUF_RATE, help="EUR->HUF rate for renovation cost math.")
    parser.add_argument("--headed", action="store_true", help="Show the browser window instead of running headless.")
    parser.add_argument(
        "--ignore-robots",
        action="store_true",
        help="Skip the robots.txt check. Only use this for a portal/path you've confirmed you're allowed to crawl.",
    )
    parser.add_argument(
        "--clear-mock",
        action="store_true",
        help="Delete existing mock/demo listings (see scripts/seed_data.py) before scraping, "
        "so the dashboard ends up holding only real scraped data.",
    )
    parser.add_argument(
        "--clear-mock-only",
        action="store_true",
        help="Same cleanup as --clear-mock, but skip the scrape entirely and exit — "
        "a quick reset with no browser/network involved.",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    if not args.clear_mock_only and not args.agent and not args.portal:
        parser.error("--portal (or --agent) is required unless --clear-mock-only is given")
    if args.agent and args.portal:
        parser.error("--agent runs every eligible portal itself — don't combine it with --portal")

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.clear_mock or args.clear_mock_only:
        deleted = _clear_mock_data()
        print(f"Cleared {deleted} mock/demo listing(s).", file=sys.stderr)
        if args.clear_mock_only:
            return 0

    if args.agent:
        results = run_agent(
            max_listings=args.max_listings,
            max_pages=args.max_pages,
            delay_range=(args.min_delay, args.max_delay),
            headless=not args.headed,
            eur_huf_rate=args.eur_huf_rate,
            ignore_robots=args.ignore_robots,
        )
    else:
        scraper = get_scraper(args.portal)
        results = run_scrape(
            scraper,
            max_listings=args.max_listings,
            max_pages=args.max_pages,
            delay_range=(args.min_delay, args.max_delay),
            headless=not args.headed,
            eur_huf_rate=args.eur_huf_rate,
            ignore_robots=args.ignore_robots,
        )

    if args.agent:
        # Same post-scan step the server's Scan button runs: refresh the
        # district medians from the freshly scanned listings.
        from app.database import SessionLocal
        from app.services import stats_service

        db = SessionLocal()
        try:
            stats_service.update_district_benchmarks(db)
            stats_service.update_building_type_benchmarks(db)
        finally:
            db.close()

    stored = [r for r in results if r.stored]
    print(json.dumps([r.to_dict() for r in results], indent=2, ensure_ascii=False))
    print(f"\n{len(stored)}/{len(results)} listings stored.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
