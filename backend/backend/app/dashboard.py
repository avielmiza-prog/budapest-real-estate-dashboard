"""
Aggregation logic for the dashboard: top-line KPIs and the enriched,
ROI-filterable "deals" list the frontend's table/card views render from.

Kept out of main.py so the route handlers stay thin, and out of analyzer.py
since analyzer.py is single-property math with zero DB awareness — this
module is the layer that fans analyzer.py out across many properties.
"""
import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from app import analyzer, crud, deal_score as deal_score_module, models


def _district_benchmark_or_none(db: Session, district: str) -> Optional[models.DistrictBenchmark]:
    try:
        district_number = analyzer.parse_district_number(district)
    except ValueError:
        return None
    return crud.get_district_benchmark(db, district_number)


def _reference_price_sqm(prop: models.Property, benchmark: models.DistrictBenchmark) -> Optional[float]:
    """
    Which benchmark column to compare a property's price/sqm against depends
    on its own condition: an already-renovated listing should be judged
    against avg_price_sqm_renovated, everything else (raw/unknown/needs-work)
    against avg_price_sqm_raw, falling back to whichever one is populated if
    only one of the two is.
    """
    condition = (prop.condition or "").lower()
    looks_renovated = any(word in condition for word in ("renov", "felújít", "new", "új"))

    if looks_renovated and benchmark.avg_price_sqm_renovated is not None:
        return benchmark.avg_price_sqm_renovated
    if not looks_renovated and benchmark.avg_price_sqm_raw is not None:
        return benchmark.avg_price_sqm_raw
    # fall back to whichever exists
    return benchmark.avg_price_sqm_raw if benchmark.avg_price_sqm_raw is not None else benchmark.avg_price_sqm_renovated


def _discount_percent(prop: models.Property, benchmark: models.DistrictBenchmark) -> Optional[float]:
    reference = _reference_price_sqm(prop, benchmark)
    if not reference or not prop.price_per_sqm:
        return None
    return round((reference - prop.price_per_sqm) / reference * 100, 2)


def compute_stats(db: Session, eur_huf_rate: float, top_n: int = 5) -> dict:
    """
    total_listings         - count of every stored Property
    avg_price_sqm_huf/eur  - average price_per_sqm across properties that have one
    top_undervalued        - up to top_n properties scraped today, ranked by
                              discount vs. their district benchmark (highest first).
                              Falls back to ranking across ALL properties (any date)
                              if nothing was scraped today, so the dashboard isn't
                              just empty on a quiet day — `is_today_only` says which.
    """
    properties: List[models.Property] = db.query(models.Property).all()
    total_listings = len(properties)

    priced = [p.price_per_sqm for p in properties if p.price_per_sqm]
    avg_price_sqm_huf = round(sum(priced) / len(priced), 2) if priced else None
    avg_price_sqm_eur = round(avg_price_sqm_huf / eur_huf_rate, 2) if avg_price_sqm_huf else None

    today_start = datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    todays_properties = [p for p in properties if p.created_at and p.created_at >= today_start]

    is_today_only = True
    pool = todays_properties
    if not pool:
        is_today_only = False
        pool = properties

    scored = []
    for prop in pool:
        benchmark = _district_benchmark_or_none(db, prop.district)
        if benchmark is None:
            continue
        discount = _discount_percent(prop, benchmark)
        if discount is None:
            continue
        scored.append((discount, prop, benchmark))

    scored.sort(key=lambda t: t[0], reverse=True)
    top_undervalued = [
        {
            "property_id": prop.id,
            "title": prop.title,
            "district": prop.district,
            "price_huf": prop.price_huf,
            "price_per_sqm": prop.price_per_sqm,
            "benchmark_price_per_sqm": _reference_price_sqm(prop, benchmark),
            "discount_percent": discount,
        }
        for discount, prop, benchmark in scored[:top_n]
    ]

    return {
        "total_listings": total_listings,
        "avg_price_sqm_huf": avg_price_sqm_huf,
        "avg_price_sqm_eur": avg_price_sqm_eur,
        "eur_huf_rate": eur_huf_rate,
        "top_undervalued": top_undervalued,
        "is_today_only": is_today_only,
        "today_new_listings": len(todays_properties),
        "computed_at": datetime.datetime.utcnow().isoformat() + "Z",
    }


def list_deals(
    db: Session,
    district: Optional[str] = None,
    districts: Optional[List[str]] = None,
    min_roi: Optional[float] = None,
    min_size_sqm: Optional[float] = None,
    max_size_sqm: Optional[float] = None,
    min_price_huf: Optional[float] = None,
    max_price_huf: Optional[float] = None,
    portals: Optional[List[str]] = None,
    favorites_only: bool = False,
    pipeline_status: Optional[str] = None,
    eur_huf_rate: float = analyzer.DEFAULT_EUR_HUF_RATE,
    skip: int = 0,
    limit: int = 200,
) -> List[dict]:
    """
    Property rows (DB-level filtered by district/size/price/portal/favorite/
    pipeline status) enriched with their full renovation analysis and a
    0-100 Deal Score, then optionally filtered by min_roi (best tier's ROI%
    >= min_roi). A property with no district benchmark yet gets
    analysis=None and is excluded whenever min_roi is set, since there's
    nothing to compare it against.
    """
    properties = crud.list_properties(
        db,
        skip=skip,
        limit=limit,
        district=district,
        districts=districts,
        min_price_huf=min_price_huf,
        max_price_huf=max_price_huf,
        min_size_sqm=min_size_sqm,
        max_size_sqm=max_size_sqm,
        portals=portals,
        favorites_only=favorites_only,
        pipeline_status=pipeline_status,
    )

    deals = []
    for prop in properties:
        analysis_dict = None
        best_tier = None
        try:
            analysis = analyzer.analyze_property_by_id(db, prop.id, eur_huf_rate=eur_huf_rate)
            analysis_dict = analysis.to_dict()
            best = analysis.best_tier()
            best_tier = best.to_dict() if best else None
        except (LookupError, ValueError):
            pass  # no benchmark yet, or unparseable district/missing size/price — leave analysis as None

        if min_roi is not None:
            if best_tier is None or best_tier["roi_percent"] is None or best_tier["roi_percent"] < min_roi:
                continue

        benchmark = _district_benchmark_or_none(db, prop.district)
        discount_percent = _discount_percent(prop, benchmark) if benchmark else None
        usable_area_sqm = analysis_dict["usable_area_sqm"] if analysis_dict else prop.size_sqm
        score = deal_score_module.compute_deal_score(
            discount_percent=discount_percent,
            roi_percent=best_tier["roi_percent"] if best_tier else None,
            usable_area_sqm=usable_area_sqm,
            rooms=prop.rooms,
        )

        deals.append(
            {
                "id": prop.id,
                "title": prop.title,
                "district": prop.district,
                "address": prop.address,
                "size_sqm": prop.size_sqm,
                "rooms": prop.rooms,
                "balcony_sqm": prop.balcony_sqm,
                "price_huf": prop.price_huf,
                "price_eur": prop.price_eur,
                "price_per_sqm": prop.price_per_sqm,
                "url": prop.url,
                "source_url": prop.url,  # alias for `url` — the exact source-portal listing page
                "condition": prop.condition,
                "images": prop.images or [],
                "portal": prop.portal,
                "latitude": prop.latitude,
                "longitude": prop.longitude,
                "is_favorite": prop.is_favorite,
                "pipeline_status": prop.pipeline_status,
                "created_at": prop.created_at.isoformat() if prop.created_at else None,
                "analysis": analysis_dict,
                "best_tier": best_tier,
                "discount_percent": discount_percent,
                "deal_score": score,
                "deal_score_band": deal_score_module.score_band(score),
            }
        )

    return deals
