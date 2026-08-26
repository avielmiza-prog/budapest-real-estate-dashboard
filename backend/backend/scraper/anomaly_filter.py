"""
Anomaly guardrails for freshly-scraped listings — catches known bad-data
patterns from the source portals rather than genuine investment judgment
calls (that's app.deal_score / app.services.valuation_agent's job): rental
listings misposted in the sale section (suspiciously low absolute price),
mis-tagged/non-residential listings (price/sqm wildly outside Budapest's
real range), and storage/parking-space listings miscategorized as
apartments (implausibly small floor area).

Applied once, at scraper/pipeline.py's store_and_analyze() — the single
funnel both the HTTP-fetch path and the Playwright path feed into — so
every scrape source gets the same guardrails regardless of which path
found it.
"""
from typing import Optional

MIN_SALE_PRICE_HUF = 15_000_000
MIN_PRICE_PER_SQM_HUF = 400_000
MAX_PRICE_PER_SQM_HUF = 4_500_000
MIN_SIZE_SQM = 15


def anomaly_reason(normalized: dict) -> Optional[str]:
    """
    `normalized` is a dict shaped like scraper.normalize.normalize_listing's
    return value. Returns a short human-readable reason the listing should
    be discarded, or None if it passes every guardrail. Any field that's
    None (couldn't be parsed) is *not* treated as anomalous by that specific
    check — normalize_listing already drops listings with no price at all.
    """
    price_huf = normalized.get("price_huf")
    size_sqm = normalized.get("size_sqm")
    price_per_sqm = normalized.get("price_per_sqm")

    if price_huf is not None and price_huf < MIN_SALE_PRICE_HUF:
        return (
            f"price {price_huf:,.0f} HUF is below the {MIN_SALE_PRICE_HUF:,.0f} HUF sale-listing floor "
            "(likely a rental misposted as a sale)"
        ).replace(",", " ")
    if size_sqm is not None and size_sqm < MIN_SIZE_SQM:
        return f"size {size_sqm:.1f} sqm is below the {MIN_SIZE_SQM:.0f} sqm floor"
    if price_per_sqm is not None and price_per_sqm < MIN_PRICE_PER_SQM_HUF:
        return f"price/sqm {price_per_sqm:,.0f} HUF is below the {MIN_PRICE_PER_SQM_HUF:,.0f} HUF/sqm floor".replace(",", " ")
    if price_per_sqm is not None and price_per_sqm > MAX_PRICE_PER_SQM_HUF:
        return f"price/sqm {price_per_sqm:,.0f} HUF exceeds the {MAX_PRICE_PER_SQM_HUF:,.0f} HUF/sqm ceiling".replace(",", " ")
    return None
