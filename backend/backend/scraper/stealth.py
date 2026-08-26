"""
Stealth setup for a Playwright page/context — reduces the most common
automated-browser fingerprints (navigator.webdriver, missing plugins list,
inconsistent languages, headless-only permissions quirks, etc).

Prefers the `playwright-stealth` package when it's installed (pip install
playwright-stealth); falls back to a hand-rolled set of the same well-known
JS patches when it isn't, so this module works out of the box either way.

IMPORTANT — use this responsibly:
Reducing generic automation fingerprints is standard practice for browser
automation and QA tooling generally, not just scraping. But some sites
(ingatlan.com is one — see scraper/portals/README or the top-level scraper
README) explicitly disallow automated access to their listing pages in
robots.txt and run dedicated anti-bot services (e.g. Distil/Imperva) to
enforce it. Pointing this module at a site that has said "no" via robots.txt
is a deliberate choice to override that — make it consciously, per target,
rather than by default. See scraper/robots.py for a helper that checks
robots.txt before scraping.
"""
import logging

logger = logging.getLogger(__name__)

try:
    from playwright_stealth import stealth_sync as _vendor_stealth_sync  # type: ignore

    _HAVE_PLAYWRIGHT_STEALTH = True
except ImportError:  # pragma: no cover - exercised whenever the package isn't installed
    _HAVE_PLAYWRIGHT_STEALTH = False

# Manual fallback patches, applied via an init script so they run before any
# page JS executes (including on every subsequent navigation in the page).
_MANUAL_STEALTH_JS = r"""
// Hide the automation flag Playwright/Selenium set on navigator.
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

// Headless Chrome reports an empty plugins array; real browsers don't.
Object.defineProperty(navigator, 'plugins', {
    get: () => [1, 2, 3, 4, 5].map(() => ({ name: 'Chrome PDF Plugin' })),
});

// Real browsers report a populated languages list.
Object.defineProperty(navigator, 'languages', { get: () => ['hu-HU', 'hu', 'en-US', 'en'] });

// window.chrome is missing in headless mode by default.
window.chrome = window.chrome || { runtime: {} };

// Permissions.query for 'notifications' behaves oddly under headless; normalize it.
const originalQuery = window.navigator.permissions && window.navigator.permissions.query;
if (originalQuery) {
    window.navigator.permissions.query = (parameters) => (
        parameters && parameters.name === 'notifications'
            ? Promise.resolve({ state: Notification.permission })
            : originalQuery(parameters)
    );
}
"""


def apply_stealth(page) -> None:
    """
    Apply stealth patches to a Playwright Page (sync API). Call this right
    after `context.new_page()`, before any navigation.
    """
    if _HAVE_PLAYWRIGHT_STEALTH:
        _vendor_stealth_sync(page)
        return

    logger.info(
        "playwright-stealth not installed; using built-in manual stealth patches. "
        "Run `pip install playwright-stealth` for more thorough coverage."
    )
    page.add_init_script(_MANUAL_STEALTH_JS)


# A realistic desktop Chrome UA — pair with apply_stealth() when creating the
# browser context. Update periodically; a stale UA is itself a fingerprint.
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)

DEFAULT_VIEWPORT = {"width": 1366, "height": 900}

# Rounds out the desktop-Chrome fingerprint alongside the UA/viewport above —
# a real browser sends these on every navigation; a bare Playwright request
# doesn't unless told to.
DEFAULT_EXTRA_HTTP_HEADERS = {
    "Accept-Language": "hu-HU,hu;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Sec-Ch-Ua": '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
}

# Page-level timeouts (navigation + all other Playwright actions), applied
# to every context this scraper creates. Generous enough to ride out a slow
# portal or a mid-run retry without being mistaken for a hang.
DEFAULT_TIMEOUT_MS = 45_000
