"""
Generic, portal-agnostic "act like a human" helpers layered on top of a
Playwright Page: dismissing cookie/GDPR consent modals and scrolling down
incrementally so lazy-loaded listing cards/images actually mount before
extraction runs, the way a real visitor scanning a results page would.

Deliberately has no dependency on scraper.pipeline or any portal module, so
pipeline.py can import this directly without a circular import back to
scraper/agent/orchestrator.py (which does import pipeline.py).
"""
import logging
import random
import time

logger = logging.getLogger(__name__)

# Hungarian + English text commonly used on "Accept all cookies" buttons
# across the portals this agent targets. Matched case-insensitively against
# a clickable element's visible text.
COOKIE_ACCEPT_TEXT_PATTERNS = [
    "összes elfogadása",
    "mind elfogadása",
    "elfogadom",
    "elfogadás",
    "rendben",
    "értem",
    "accept all",
    "accept cookies",
    "i agree",
    "agree",
    "accept",
]

# Common consent-management-platform selectors (OneTrust, Cookiebot, etc.)
# tried before falling back to a text scan.
COOKIE_BANNER_SELECTORS = [
    "#onetrust-accept-btn-handler",
    "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
    "[id*='cookie' i] button",
    "[class*='cookie' i] button",
    "[id*='consent' i] button",
    "[class*='consent' i] button",
    "button[aria-label*='cookie' i]",
]


def dismiss_cookie_consent(page, timeout_ms: int = 4000) -> bool:
    """
    Best-effort: click through a cookie/GDPR consent modal if one is
    currently showing. Returns True if something was clicked, False if no
    modal was found (the common case on a second visit in the same context,
    or a portal with no consent modal at all). Never raises — a missing or
    already-dismissed banner is not an error, just a no-op.
    """
    for selector in COOKIE_BANNER_SELECTORS:
        try:
            el = page.query_selector(selector)
            if el is not None and el.is_visible():
                el.click(timeout=1000)
                logger.debug("Dismissed cookie consent via selector %r", selector)
                time.sleep(0.3)
                return True
        except Exception:  # noqa: BLE001 - best-effort, any failure just tries the next approach
            continue

    deadline = time.time() + timeout_ms / 1000
    try:
        candidates = page.query_selector_all("button, a[role='button'], [role='button']")
    except Exception:  # noqa: BLE001
        candidates = []
    for el in candidates:
        if time.time() > deadline:
            break
        try:
            if not el.is_visible():
                continue
            text = (el.inner_text() or "").strip().lower()
        except Exception:  # noqa: BLE001
            continue
        if not text or len(text) > 40:
            continue
        if any(pattern in text for pattern in COOKIE_ACCEPT_TEXT_PATTERNS):
            try:
                el.click(timeout=1000)
                logger.debug("Dismissed cookie consent via text match %r", text)
                time.sleep(0.3)
                return True
            except Exception:  # noqa: BLE001
                continue
    return False


def human_like_scroll(page, steps: int = 6, min_pause: float = 0.15, max_pause: float = 0.45) -> None:
    """
    Scrolls down the page in several irregular increments (rather than
    jumping straight to the bottom) so infinite-scroll/lazy-loaded listing
    cards and images have a chance to mount. Best-effort: silently stops if
    the page navigates away or errors mid-scroll.
    """
    try:
        total_height = page.evaluate("document.body.scrollHeight")
    except Exception:  # noqa: BLE001
        return
    if not total_height:
        return
    for i in range(1, steps + 1):
        target = int(total_height * i / steps)
        try:
            page.evaluate(f"window.scrollTo(0, {target})")
        except Exception:  # noqa: BLE001
            return
        time.sleep(random.uniform(min_pause, max_pause))


def act_human(page) -> None:
    """Convenience wrapper: dismiss any consent modal, then scroll the page."""
    dismiss_cookie_consent(page)
    human_like_scroll(page)
