"""
Cross-portal duplicate detection — the same real-world apartment is often
posted on more than one portal (or re-posted later at a slightly different
price). Two Property rows are treated as the same listing when they share a
district and their floor area is within ±2 sqm and price within ±2% of each
other.

Run once per scan cycle (see scraper/agent/orchestrator.py's run_agent() and
scraper/pipeline.py's run_scrape()) against the whole table, not per-listing
— a duplicate can only be recognized by comparing against every other
currently-stored row, not just the one just scraped.
"""
import logging
from typing import List

from sqlalchemy.orm import Session

from app import models

logger = logging.getLogger(__name__)

FLOOR_AREA_TOLERANCE_SQM = 2.0
PRICE_TOLERANCE_PERCENT = 0.02


def _is_duplicate(a: models.Property, b: models.Property) -> bool:
    if a.district != b.district:
        return False
    if a.size_sqm is None or b.size_sqm is None or not a.price_huf or not b.price_huf:
        return False
    if abs(a.size_sqm - b.size_sqm) > FLOOR_AREA_TOLERANCE_SQM:
        return False
    return abs(a.price_huf - b.price_huf) / a.price_huf <= PRICE_TOLERANCE_PERCENT


def dedup_properties(db: Session) -> int:
    """
    Finds clusters of duplicate Property rows (see module docstring), keeps
    the earliest (by created_at) row in each cluster, appends every other
    member's url onto the kept row's duplicate_source_urls (deduplicated),
    and deletes the rest. Returns the number of rows removed.
    """
    properties: List[models.Property] = (
        db.query(models.Property).order_by(models.Property.created_at.asc()).all()
    )

    survivors: List[models.Property] = []
    removed = 0

    for prop in properties:
        match = next((s for s in survivors if _is_duplicate(s, prop)), None)
        if match is None:
            survivors.append(prop)
            continue

        sources = list(match.duplicate_source_urls or [])
        if prop.url and prop.url != match.url and prop.url not in sources:
            sources.append(prop.url)
        match.duplicate_source_urls = sources
        db.delete(prop)
        removed += 1

    if removed:
        db.commit()
        logger.info("[dedup] removed %d duplicate listing(s) across %d survivor(s)", removed, len(survivors))
    return removed
