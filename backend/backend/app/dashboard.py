"""
Aggregation logic for the dashboard: top-line KPIs and the enriched,
ROI-filterable "deals" list the frontend's table/card views render from.

Kept out of main.py so the route handlers stay thin, and out of analyzer.py
since analyzer.py is single-property math with zero DB awareness — this
module is the layer that fans analyzer.py out across many properties.
"""
import csv
import datetime
import io
from typing import List, Optional

from sqlalchemy.orm import Session

from app import analyzer, crud, deal_score as deal_score_module, models
from app.condition_classifier import classify_condition_tag

# Strict Net ROI hurdle applied by default — must match
# app.services.valuation_agent.MIN_HURDLE_ROI_PERCENT (the same threshold the
# underwriting agent uses to flag "risk:below_hurdle_roi"). Kept as a literal
# rather than importing app.services.valuation_agent here: several tests
# import app.dashboard/app.main before pinning their own throwaway
# DATABASE_URL, and app.database's engine is created once at first import —
# pulling in another module's import chain this early has repeatedly caused
# tests to share a DB unintentionally. See test_api.py's module docstring.
#
# Only excludes properties that HAVE a persisted flip ROI below the hurdle —
# a property with no underwriting verdict yet (flip_roi_percent=None) still
# shows up, so a fresh scrape isn't hidden before its first underwriting
# pass. Callers that want the pre-hurdle full market (e.g. an analyst
# reviewing everything) can pass min_flip_roi=None explicitly.
DEFAULT_MIN_FLIP_ROI_PERCENT = 10.0


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


def compute_live_deal_metrics(db: Session, prop: models.Property, eur_huf_rate: float) -> tuple:
    """
    (analysis_dict, best_tier, discount_percent, score) for one property —
    the live (app.analyzer + app.deal_score) readout shared by list_deals()
    and app.main's investment-memo route, so both compute this identically.
    analysis_dict/best_tier are None when there's no benchmark yet or the
    district/size/price can't be parsed; discount_percent/score degrade
    gracefully in that case too (see app.deal_score.compute_deal_score).
    """
    analysis_dict = None
    best_tier = None
    try:
        analysis = analyzer.analyze_property_by_id(db, prop.id, eur_huf_rate=eur_huf_rate)
        analysis_dict = analysis.to_dict()
        best = analysis.best_tier()
        best_tier = best.to_dict() if best else None
    except (LookupError, ValueError):
        pass  # no benchmark yet, or unparseable district/missing size/price — leave analysis as None

    benchmark = _district_benchmark_or_none(db, prop.district)
    discount_percent = _discount_percent(prop, benchmark) if benchmark else None
    usable_area_sqm = analysis_dict["usable_area_sqm"] if analysis_dict else prop.size_sqm
    score = deal_score_module.compute_deal_score(
        discount_percent=discount_percent,
        roi_percent=best_tier["roi_percent"] if best_tier else None,
        usable_area_sqm=usable_area_sqm,
        rooms=prop.rooms,
    )
    return analysis_dict, best_tier, discount_percent, score


def build_underwriting_dict(prop: models.Property, best_tier: Optional[dict], score: Optional[int]) -> Optional[dict]:
    """
    The persisted agent verdict (prop.underwriting_*) is the primary source
    for the numeric fields here, but it's null until a scan has actually
    underwritten this row (or if the agent hit "no_benchmark"/
    "insufficient_data"). Whenever a live analysis exists (`best_tier`/
    `score`, both from app.analyzer + app.deal_score — see list_deals()),
    backfill from it instead of returning null: the underwriting agent and
    app.analyzer's best tier are two independently-computed but equivalent
    readouts of the same deal, so this never fabricates a number, it just
    prefers whichever of the two actually ran. Only a property with neither
    (no benchmark AND analysis failed) still comes back null — nothing left
    to compute it from. `status`/`confidence_tag`/`updated_at` are left
    exactly as persisted (never backfilled), so callers can still tell a
    real agent verdict apart from a live-only fallback.

    Shared by list_deals() (below) and app.main's investment-memo route, so
    the Deal Memo PDF and the /deals list can never disagree about whether
    a given deal's Score/ROI/Net Profit is "null" or not.
    """
    has_underwriting = prop.underwriting_updated_at is not None
    if not has_underwriting and best_tier is None:
        return None

    return {
        "estimated_market_value_huf": (
            prop.underwriting_market_value_huf
            if prop.underwriting_market_value_huf is not None
            else (best_tier["exit_price_huf"] if best_tier else None)
        ),
        "renovation_cost_huf": (
            prop.underwriting_renovation_cost_huf
            if prop.underwriting_renovation_cost_huf is not None
            else (best_tier["renovation_cost_huf"] if best_tier else None)
        ),
        "total_investment_huf": (
            prop.underwriting_total_investment_huf
            if prop.underwriting_total_investment_huf is not None
            else (best_tier["total_investment_huf"] if best_tier else None)
        ),
        "net_profit_huf": (
            prop.underwriting_net_profit_huf
            if prop.underwriting_net_profit_huf is not None
            else (best_tier["net_profit_huf"] if best_tier else None)
        ),
        "flip_roi_percent": (
            prop.underwriting_flip_roi_percent
            if prop.underwriting_flip_roi_percent is not None
            else (best_tier["roi_percent"] if best_tier else None)
        ),
        "rental_yield_percent": (
            prop.underwriting_rental_yield_percent
            if prop.underwriting_rental_yield_percent is not None
            else (best_tier["net_yield_percent"] if best_tier else None)
        ),
        "deal_score": prop.underwriting_deal_score if prop.underwriting_deal_score is not None else score,
        "status": prop.underwriting_status,
        "confidence_tag": prop.underwriting_confidence_tag,
        "updated_at": prop.underwriting_updated_at.isoformat() if prop.underwriting_updated_at else None,
    }


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


# Sort keys, most-recently-used first. Each maps a deal dict to a sort key;
# entries with a None underlying value always sort last, regardless of
# direction, so "missing data" never masquerades as "worst" or "best".
SORT_OPTIONS = ("newest", "price_desc", "price_asc", "score_desc", "roi_desc", "sqm_asc", "roi_score_desc")

# Default sort: highest persisted Net ROI first, Deal Score as the tiebreaker
# for equal/missing ROI — surfaces the best underwritten opportunities first
# instead of just the most-recently-scraped ones.
DEFAULT_SORT = "roi_score_desc"


def _sort_deals(deals: List[dict], sort_by: str) -> List[dict]:
    if sort_by == "price_desc":
        return sorted(deals, key=lambda d: (d["price_huf"] is None, -(d["price_huf"] or 0)))
    if sort_by == "price_asc":
        return sorted(deals, key=lambda d: (d["price_huf"] is None, d["price_huf"] or 0))
    if sort_by == "score_desc":
        return sorted(deals, key=lambda d: (d["deal_score"] is None, -(d["deal_score"] or 0)))
    if sort_by == "roi_desc":
        return sorted(
            deals,
            key=lambda d: (
                d["best_tier"] is None or d["best_tier"]["roi_percent"] is None,
                -((d["best_tier"] or {}).get("roi_percent") or 0),
            ),
        )
    if sort_by == "roi_score_desc":
        return sorted(
            deals,
            key=lambda d: (
                d["underwriting"] is None or d["underwriting"]["flip_roi_percent"] is None,
                -((d["underwriting"] or {}).get("flip_roi_percent") or 0),
                d["deal_score"] is None,
                -(d["deal_score"] or 0),
            ),
        )
    if sort_by == "sqm_asc":
        return sorted(deals, key=lambda d: (d["price_per_sqm"] is None, d["price_per_sqm"] or 0))
    # "newest" (default / unrecognized) — created_at desc, matching the DB's own ordering.
    return sorted(deals, key=lambda d: d["created_at"] or "", reverse=True)


def list_deals(
    db: Session,
    district: Optional[str] = None,
    districts: Optional[List[str]] = None,
    min_roi: Optional[float] = None,
    min_flip_roi: Optional[float] = DEFAULT_MIN_FLIP_ROI_PERCENT,
    min_size_sqm: Optional[float] = None,
    max_size_sqm: Optional[float] = None,
    min_price_huf: Optional[float] = None,
    max_price_huf: Optional[float] = None,
    min_price_per_sqm: Optional[float] = None,
    max_price_per_sqm: Optional[float] = None,
    portals: Optional[List[str]] = None,
    favorites_only: bool = False,
    pipeline_status: Optional[str] = None,
    eur_huf_rate: float = analyzer.DEFAULT_EUR_HUF_RATE,
    sort_by: str = DEFAULT_SORT,
    skip: int = 0,
    limit: Optional[int] = None,
) -> List[dict]:
    """
    Property rows (DB-level filtered by district/size/price/portal/favorite/
    pipeline status) enriched with their full renovation analysis and a
    0-100 Deal Score, then optionally filtered by min_roi (best tier's ROI%
    >= min_roi) and by min_flip_roi (the strict, persisted underwriting Net
    ROI hurdle — see DEFAULT_MIN_FLIP_ROI_PERCENT), sorted by `sort_by` (see
    SORT_OPTIONS), and finally paged with skip/limit. A property with no
    district benchmark yet gets analysis=None and is excluded whenever
    min_roi is set, since there's nothing to compare it against.

    Sorting and paging both happen in Python, after the full matching set is
    enriched — several sort keys (deal_score, ROI) only exist post-analysis,
    so they can't be pushed down to the DB query. `limit=None` (the default)
    returns every relevant listing, unslicing what used to be a hard 200-row
    cap.
    """
    properties = crud.list_properties(
        db,
        skip=0,
        limit=None,
        district=district,
        districts=districts,
        min_price_huf=min_price_huf,
        max_price_huf=max_price_huf,
        min_price_per_sqm=min_price_per_sqm,
        max_price_per_sqm=max_price_per_sqm,
        min_size_sqm=min_size_sqm,
        max_size_sqm=max_size_sqm,
        portals=portals,
        favorites_only=favorites_only,
        pipeline_status=pipeline_status,
    )

    deals = []
    for prop in properties:
        analysis_dict, best_tier, discount_percent, score = compute_live_deal_metrics(db, prop, eur_huf_rate)

        if min_roi is not None:
            if best_tier is None or best_tier["roi_percent"] is None or best_tier["roi_percent"] < min_roi:
                continue

        # The persisted agent verdict (prop.underwriting_*) is the primary
        # source for these four numbers, but it's null until a scan has
        # actually underwritten this row (or if the agent hit "no_benchmark"/
        # "insufficient_data"). See build_underwriting_dict()'s docstring for
        # the null-backfill rule.
        underwriting = build_underwriting_dict(prop, best_tier, score)

        if min_flip_roi is not None and underwriting is not None:
            flip_roi = underwriting["flip_roi_percent"]
            if flip_roi is not None and flip_roi < min_flip_roi:
                continue

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
                "duplicate_source_urls": prop.duplicate_source_urls or [],
                "condition": prop.condition,
                "condition_tag": classify_condition_tag(prop.condition),
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
                # Persisted verdict from app/services/valuation_agent.py, with
                # nulls backfilled from the live analysis above — see comment
                # above `has_underwriting`.
                "underwriting": underwriting,
            }
        )

    deals = _sort_deals(deals, sort_by)
    if limit is not None:
        deals = deals[skip : skip + limit]
    elif skip:
        deals = deals[skip:]
    return deals


# Column order for deals_to_csv() — deliberately flat (no nested objects),
# pulling the underwriting metrics out of the nested `underwriting` dict so
# every row is spreadsheet-ready with no post-processing.
_CSV_COLUMNS = [
    "id", "title", "district", "address", "size_sqm", "rooms", "balcony_sqm",
    "price_huf", "price_eur", "price_per_sqm", "condition", "condition_tag",
    "portal", "url", "duplicate_source_urls", "pipeline_status", "is_favorite", "created_at",
    "discount_percent", "deal_score", "deal_score_band",
    "underwriting_estimated_market_value_huf", "underwriting_renovation_cost_huf",
    "underwriting_total_investment_huf", "underwriting_net_profit_huf",
    "underwriting_flip_roi_percent", "underwriting_rental_yield_percent",
    "underwriting_deal_score", "underwriting_status", "underwriting_confidence_tag",
    "underwriting_updated_at",
]


def deals_to_csv(deals: List[dict]) -> str:
    """Flattens list_deals()'s output (including the nested `underwriting` dict) into a CSV string."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=_CSV_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for deal in deals:
        underwriting = deal.get("underwriting") or {}
        row = dict(deal)
        row["duplicate_source_urls"] = ";".join(deal.get("duplicate_source_urls") or [])
        for key, value in underwriting.items():
            row[f"underwriting_{key}"] = value
        writer.writerow(row)
    return buffer.getvalue()
