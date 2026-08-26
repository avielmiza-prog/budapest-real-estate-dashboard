"""
Exercises the REAL scraper code (Playwright DOM queries, not just the pure
text-parsing functions) against local HTML fixtures via file:// URLs — no
network access needed, so this runs even in environments where an actual
page.goto() to a live site is blocked (like the sandbox this was written in).

This proves the traversal/extraction logic and the normalize step are wired
correctly. It does NOT prove the SELECTORS in scraper/portals/ingatlanbazar.py
match the real, live ingatlanbazar.hu markup — that still needs verification
against the actual site (see that module's docstring). The fixtures here were
built to match the current placeholder selectors, by design.

Run with: python3 tests/test_scraper_offline.py
Requires the `playwright` package (already used by the scraper itself) —
no playwright-stealth or network needed for this test.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.sync_api import sync_playwright  # noqa: E402

from scraper.normalize import normalize_listing  # noqa: E402
from scraper.portals.ingatlanbazar import IngatlanbazarScraper  # noqa: E402
from scraper.portals.jofogas import JofogasScraper  # noqa: E402

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def _file_url(name: str) -> str:
    return (FIXTURES_DIR / name).resolve().as_uri()


def test_extract_listing_urls_from_search_page(page):
    page.goto(_file_url("search_results.html"))
    scraper = IngatlanbazarScraper()
    urls = scraper.extract_listing_urls(page)
    assert len(urls) == 3, f"expected 3 listing urls, got {urls}"
    assert all(u.startswith("https://ingatlanbazar.hu/hirdetes/") for u in urls), urls
    # de-duped: fixture card #1 has two <a> tags pointing at the same href
    assert len(set(urls)) == 3


def test_parse_listing_page_extracts_all_fields(page):
    page.goto(_file_url("listing_detail.html"))
    scraper = IngatlanbazarScraper()
    url = "https://ingatlanbazar.hu/hirdetes/1001-eladó-lakás-vii-kerulet"
    raw = scraper.parse_listing_page(page, url)

    assert raw is not None
    assert "Napfényes" in raw.title_text
    assert "89 900 000" in raw.price_text
    assert "55" in raw.size_text
    assert "2+1" in raw.rooms_text
    assert "VII" in raw.address_text
    assert raw.condition_text == "felújított"
    assert "Wesselényi" not in raw.description_text or "kerület" in raw.description_text
    assert len(raw.image_urls) == 2
    assert all(u.startswith("https://ingatlanbazar.hu/uploads/") for u in raw.image_urls)


def test_full_pipeline_raw_to_normalized_dict(page):
    page.goto(_file_url("listing_detail.html"))
    scraper = IngatlanbazarScraper()
    url = "https://ingatlanbazar.hu/hirdetes/1001-eladó-lakás-vii-kerulet"
    raw = scraper.parse_listing_page(page, url)
    normalized = normalize_listing(raw, scraper.portal_name)

    assert normalized is not None
    assert normalized["district"] == "VII"
    assert normalized["size_sqm"] == 55.0
    assert normalized["rooms"] == 2.5
    assert normalized["price_huf"] == 89_900_000.0
    assert normalized["price_per_sqm"] == round(89_900_000.0 / 55.0, 2)
    assert normalized["url"] == url
    assert normalized["condition"] == "felújított"
    assert len(normalized["images"]) == 2


def test_jofogas_bulk_extraction_from_search_page(page):
    """
    jofogas.hu embeds complete listing data in the search page's own
    __NEXT_DATA__ — this fixture mirrors the exact shape captured via live
    browser recon against the real site on 2026-08-26.
    """
    page.goto(_file_url("jofogas_search_results.html"))
    scraper = JofogasScraper()
    assert scraper.supports_bulk_extraction is True

    raws = scraper.extract_listings_from_search_page(page)
    # 3rd fixture ad has no url/subject (skipped), 4th is an "Iroda" (office,
    # non-residential category -> filtered out) -> only the 2 apartments remain.
    assert len(raws) == 2
    assert all("Iroda" not in r.title_text for r in raws)

    first = raws[0]
    assert "Vizivárosban" in first.title_text
    assert first.price_huf_value == 125_000_000
    assert first.size_sqm_value == 97.0
    assert first.rooms_value == 3.0
    assert first.district_value == "I"
    assert first.latitude == 47.5071427 and first.longitude == 19.0345173
    assert first.balcony_sqm is None  # portal only reports a yes/no flag, never a size
    assert len(first.image_urls) == 2
    assert first.image_urls[0] == "https://img.jofogas.hu/767x575crop/photo1.jpg"

    second = raws[1]
    assert second.district_value == "VII"
    # UTM param on the fixture's 2nd ad url must be stripped by clean_listing_url.
    assert "utm_source" not in second.url
    assert second.image_urls == []  # genuinely no photos -> empty list, never fabricated


def test_jofogas_extract_listing_urls_matches_bulk_urls(page):
    page.goto(_file_url("jofogas_search_results.html"))
    scraper = JofogasScraper()
    urls = scraper.extract_listing_urls(page)
    raws = scraper.extract_listings_from_search_page(page)
    assert urls == [r.url for r in raws]


def test_jofogas_normalize_uses_structured_overrides_not_regex(page):  # noqa: ARG001 - no page needed, kept for harness uniformity
    scraper = JofogasScraper()
    from scraper.base import RawListing

    raw = RawListing(
        url="https://ingatlan.jofogas.hu/x.htm",
        title_text="Teszt lakás",
        price_huf_value=50_000_000,
        size_sqm_value=40.0,
        rooms_value=2.0,
        district_value="XIII",
        latitude=47.5,
        longitude=19.08,
    )
    normalized = normalize_listing(raw, scraper.portal_name)
    assert normalized["price_huf"] == 50_000_000
    assert normalized["size_sqm"] == 40.0
    assert normalized["rooms"] == 2.0
    assert normalized["district"] == "XIII"
    assert normalized["portal"] == "jofogas"
    assert normalized["latitude"] == 47.5
    assert normalized["longitude"] == 19.08
    assert normalized["price_per_sqm"] == round(50_000_000 / 40.0, 2)


def test_jofogas_has_next_page_respects_robots_page_cap(page):  # noqa: ARG001 - no page needed, kept for harness uniformity
    scraper = JofogasScraper()

    class _FakePage:
        def eval_on_selector(self, selector, script):
            import json

            return json.dumps(
                {
                    "props": {
                        "pageProps": {
                            "adList": {"pager": {"current_page": 9, "last_page": 211}}
                        }
                    }
                }
            )

    # robots.txt only allows o=1..9 -> must stop even though last_page says more exist.
    assert scraper.has_next_page(_FakePage()) is False


if __name__ == "__main__":
    tests = [
        test_extract_listing_urls_from_search_page,
        test_parse_listing_page_extracts_all_fields,
        test_full_pipeline_raw_to_normalized_dict,
        test_jofogas_bulk_extraction_from_search_page,
        test_jofogas_extract_listing_urls_matches_bulk_urls,
        test_jofogas_normalize_uses_structured_overrides_not_regex,
        test_jofogas_has_next_page_respects_robots_page_cap,
    ]
    failures = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for t in tests:
            page = browser.new_page()
            try:
                t(page)
                print(f"PASS: {t.__name__}")
            except AssertionError as e:
                failures += 1
                print(f"FAIL: {t.__name__}: {e}")
            finally:
                page.close()
        browser.close()
    print(f"\n{len(tests) - failures}/{len(tests)} tests passed")
    sys.exit(1 if failures else 0)
