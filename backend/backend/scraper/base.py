"""
Portal-agnostic scraper interface. Each concrete portal (scraper/portals/*.py)
implements BaseScraper against its own markup; everything else in the
pipeline (stealth, rate limiting, DB storage, analysis) is shared.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class RawListing:
    """
    Whatever a portal's page gives up. Text fields are basically unprocessed
    (text_parsing.py's regexes turn them into numbers) — kept that way so a
    DOM-scraped portal's job is just "pull these strings off the page".

    Portals that instead extract from structured JSON (hydration data,
    JSON-LD) already have typed values, and shouldn't lossily round-trip a
    number back through a text regex just to satisfy this shape — they can
    set the matching `*_value`/`latitude`/etc. override field directly.
    normalize_listing() prefers an override over parsing its text sibling.
    """
    url: str
    title_text: str = ""
    price_text: str = ""
    size_text: str = ""
    rooms_text: str = ""
    address_text: str = ""
    condition_text: str = ""
    description_text: str = ""
    image_urls: List[str] = field(default_factory=list)

    # Optional pre-parsed overrides for portals with structured (JSON) data.
    price_huf_value: Optional[float] = None
    price_eur_value: Optional[float] = None
    size_sqm_value: Optional[float] = None
    rooms_value: Optional[float] = None
    district_value: Optional[str] = None  # already a roman numeral, e.g. "VII"
    balcony_sqm: Optional[float] = None  # only set when the portal gives an actual size, never guessed
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class BaseScraper(ABC):
    """
    Subclass this per portal. `portal_name` is used for logging and as part
    of the dedup key; everything else follows Playwright's sync Page API.
    """

    portal_name: str = "base"

    # Set True (and implement extract_listings_from_search_page) when a
    # portal embeds complete listing data in the search-results page itself
    # (e.g. Next.js hydration JSON), making a per-listing detail-page visit
    # unnecessary — faster, and far fewer requests against the target site.
    supports_bulk_extraction: bool = False

    # Set True (and implement fetch_via_http) when a portal's listing data
    # is present in the plain server-rendered HTML — no browser/JS needed at
    # all. scraper/agent/orchestrator.py tries this first and only falls
    # back to launching Playwright if it's unset or raises.
    supports_http_fetch: bool = False

    def fetch_via_http(self, max_listings: int, max_pages: int, ignore_robots: bool = False) -> List[RawListing]:
        """
        Plain-HTTP equivalent of the Playwright-based collection path (see
        scraper/http_client.py) — only implemented by portals with
        supports_http_fetch = True. Should raise (scraper.http_client.FetchError
        or anything else) rather than return an empty/partial result on
        failure, so the caller knows to fall back to Playwright instead of
        treating "couldn't fetch" as "genuinely zero listings".
        """
        raise NotImplementedError

    @abstractmethod
    def build_search_url(self, page_number: int) -> str:
        """Return the search-results URL for the given 1-indexed page number."""
        raise NotImplementedError

    @abstractmethod
    def extract_listing_urls(self, page) -> List[str]:
        """
        Given a Playwright Page already navigated to a search-results page,
        return the absolute URLs of every listing card on it.
        """
        raise NotImplementedError

    @abstractmethod
    def parse_listing_page(self, page, url: str) -> Optional[RawListing]:
        """
        Given a Playwright Page already navigated to a single listing's
        detail page, pull out the raw fields. Return None if the page
        doesn't look like a real listing (e.g. it 404'd or got redirected).
        Not called when supports_bulk_extraction is True and the bulk path
        already produced this URL's data, but still implement it — it's the
        fallback if a URL somehow needs a direct visit.
        """
        raise NotImplementedError

    def extract_listings_from_search_page(self, page) -> List[RawListing]:
        """
        Override (alongside setting supports_bulk_extraction = True) when a
        portal's search-results page already embeds full listing data. Must
        return fully-populated RawListing objects (real `url` included).
        """
        raise NotImplementedError

    def has_next_page(self, page) -> bool:
        """
        Override if a portal needs custom pagination-end detection. Default:
        keep paginating until extract_listing_urls() returns nothing.
        """
        return True
