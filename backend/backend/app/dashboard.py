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
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app import analyzer, crud, deal_score as deal_score_module, flip_model, models
from app.condition_classifier import classify_condition_tag
from app.services import scenario_analysis

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
# No default hurdle: the list shows every active listing, best first, and
# the UI filters by verdict. Hiding sub-10% deals by default made the
# dashboard look empty and hid listings that become deals after negotiation.
DEFAULT_MIN_FLIP_ROI_PERCENT = None


STALE_AFTER_DAYS = 21  # not seen on any portal for this long -> treated as sold/withdrawn


def _last_seen(prop: models.Property) -> Optional[datetime.datetime]:
    return prop.last_seen_at or prop.created_at


def is_stale(prop: models.Property, now: Optional[datetime.datetime] = None) -> bool:
    seen = _last_seen(prop)
    if seen is None:
        return False
    now = now or datetime.datetime.utcnow()
    return (now - seen).days > STALE_AFTER_DAYS


class BenchmarkCache:
    """
    Every DistrictBenchmark/BuildingTypeBenchmark row, loaded once per
    request. The old code ran 4 DB queries per listing (property re-fetch +
    3 benchmark lookups); against a cloud Postgres that is minutes for a
    few thousand listings, which is what made the dashboard hang.
    """

    def __init__(self, db: Session):
        self.districts: Dict[int, models.DistrictBenchmark] = {
            b.district_number: b for b in db.query(models.DistrictBenchmark).all()
        }
        self.building_types: Dict[tuple, models.BuildingTypeBenchmark] = {
            (b.district_number, b.building_type): b for b in db.query(models.BuildingTypeBenchmark).all()
        }
        self._district_all: Dict[int, Optional[float]] = {}
        self._parsed: Dict[str, Optional[int]] = {}

    def district_number(self, district: Optional[str]) -> Optional[int]:
        key = district or ""
        if key not in self._parsed:
            try:
                self._parsed[key] = analyzer.parse_district_number(key)
            except ValueError:
                self._parsed[key] = None
        return self._parsed[key]

    def district(self, district: Optional[str]) -> Optional[models.DistrictBenchmark]:
        number = self.district_number(district)
        return self.districts.get(number) if number is not None else None

    def building_type(self, district: Optional[str], building_type: Optional[str]):
        number = self.district_number(district)
        if number is None or not building_type:
            return None
        return self.building_types.get((number, building_type))

    def district_all_median(self, district: Optional[str]) -> Optional[float]:
        """Sample-weighted median HUF/sqm across all building types in the district."""
        number = self.district_number(district)
        if number is None:
            return None
        if number not in self._district_all:
            rows = [b for (n, _), b in self.building_types.items() if n == number and b.avg_price_sqm and b.sample_count]
            total = sum(b.sample_count for b in rows)
            self._district_all[number] = (
                sum(b.avg_price_sqm * b.sample_count for b in rows) / total if total else None
            )
        return self._district_all[number]


def _district_benchmark_or_none(db: Session, district: str) -> Optional[models.DistrictBenchmark]:
    try:
        district_number = analyzer.parse_district_number(district)
    except ValueError:
        return None
    return crud.get_district_benchmark(db, district_number)


def _reference_price_sqm(prop: models.Property, benchmark: models.DistrictBenchmark) -> Optional[float]:
    """
    Same-condition benchmark: renovated listings vs. the renovated median,
    everything else vs. the raw median. Uses the shared condition
    classifier (the old substring check treated any text containing "új"
    as renovated).
    """
    tag = classify_condition_tag(prop.condition)
    looks_renovated = tag in ("Renovated", "New Construction")
    if looks_renovated and benchmark.avg_price_sqm_renovated is not None:
        return benchmark.avg_price_sqm_renovated
    if not looks_renovated and benchmark.avg_price_sqm_raw is not None:
        return benchmark.avg_price_sqm_raw
    return benchmark.avg_price_sqm_raw if benchmark.avg_price_sqm_raw is not None else benchmark.avg_price_sqm_renovated


def _discount_percent(prop: models.Property, benchmark: models.DistrictBenchmark) -> Optional[float]:
    reference = _reference_price_sqm(prop, benchmark)
    if not reference or not prop.price_per_sqm:
        return None
    return round((reference - prop.price_per_sqm) / reference * 100, 2)


def compute_flip(prop: models.Property, cache: BenchmarkCache) -> Optional[flip_model.FlipResult]:
    """The realistic flip verdict (app.flip_model), or None when size/price/benchmark are missing."""
    benchmark = cache.district(prop.district)
    if benchmark is None or not benchmark.avg_price_sqm_renovated or not prop.size_sqm or not prop.price_huf:
        return None
    bt = cache.building_type(prop.district, prop.building_type)
    try:
        return flip_model.evaluate_flip(
            size_sqm=prop.size_sqm,
            price_huf=prop.price_huf,
            condition=prop.condition,
            district_renovated_median_sqm=benchmark.avg_price_sqm_renovated,
            district_raw_median_sqm=benchmark.avg_price_sqm_raw,
            balcony_sqm=prop.balcony_sqm,
            building_type=prop.building_type,
            ceiling_height_m=prop.ceiling_height_m,
            building_type_median_sqm=bt.avg_price_sqm if bt else None,
            building_type_samples=bt.sample_count if bt else 0,
            district_all_median_sqm=cache.district_all_median(prop.district),
            renovated_sample_count=benchmark.sample_count_renovated,
            renovated_source=benchmark.source_renovated,
            description=prop.description,
            floor=prop.floor,
            has_elevator=prop.has_elevator,
        )
    except ValueError:
        return None


def compute_live_deal_metrics(
    db: Session, prop: models.Property, eur_huf_rate: float, cache: Optional[BenchmarkCache] = None
) -> tuple:
    """
    (analysis_dict, best_tier, discount_percent, score) for one property.
    `analysis_dict` is the interactive Light/Medium/Full breakdown the
    detail modal's slider uses. `best_tier` is now the tier matching the
    listing's condition (not the cheapest one), with its ROI replaced by
    the realistic after-tax flip ROI, so every "ROI" in the app is the
    same number.
    """
    cache = cache or BenchmarkCache(db)
    benchmark = cache.district(prop.district)
    analysis_dict = None
    best_tier = None
    if benchmark is not None and benchmark.avg_price_sqm_renovated and prop.size_sqm and prop.price_huf:
        try:
            analysis = analyzer.analyze_property(
                size_sqm=prop.size_sqm,
                asking_price_huf=prop.price_huf,
                avg_price_sqm_renovated_huf=benchmark.avg_price_sqm_renovated,
                district=prop.district,
                eur_huf_rate=eur_huf_rate,
                balcony_sqm=prop.balcony_sqm,
                avg_rent_huf_sqm=benchmark.avg_rent_huf_sqm,
                district_median_sample_count=benchmark.sample_count_renovated,
                district_median_source=benchmark.source_renovated,
            )
            analysis_dict = analysis.to_dict()
        except ValueError:
            analysis_dict = None

    flip = compute_flip(prop, cache)
    if analysis_dict and flip is not None:
        tier_name = {"full": "full", "medium": "medium"}.get(flip.scope, "light")
        tier = next((t for t in analysis_dict["tiers"] if t["tier"] == tier_name), None)
        if tier is not None:
            best_tier = dict(tier)
            best_tier.update(
                {
                    "renovation_cost_huf": round(flip.renovation_cost_huf + flip.contingency_huf, 2),
                    "total_investment_huf": round(flip.total_cash_needed_huf, 2),
                    "exit_price_huf": round(flip.exit_price_huf, 2),
                    "net_profit_huf": round(flip.net_profit_huf, 2),
                    "roi_percent": round(flip.roi_percent, 2),
                }
            )

    discount_percent = (
        round(flip.discount_vs_market_percent, 2)
        if flip is not None and flip.discount_vs_market_percent is not None
        else (_discount_percent(prop, benchmark) if benchmark else None)
    )
    usable_area_sqm = analysis_dict["usable_area_sqm"] if analysis_dict else prop.size_sqm
    score = deal_score_module.compute_deal_score(
        discount_percent=discount_percent,
        roi_percent=flip.roi_percent if flip else None,
        usable_area_sqm=usable_area_sqm,
        rooms=prop.rooms,
    )
    return analysis_dict, best_tier, discount_percent, score


def build_underwriting_dict(
    prop: models.Property,
    best_tier: Optional[dict],
    score: Optional[int],
    flip: Optional[flip_model.FlipResult] = None,
) -> Optional[dict]:
    """
    Deal verdict numbers for the cards/table/PDF. Computed live from
    app.flip_model whenever possible, so a benchmark update shows up
    immediately instead of waiting for the next scan to re-underwrite the
    row. Falls back to the persisted scan-time verdict otherwise.
    """
    if flip is not None:
        return {
            "estimated_market_value_huf": round(flip.exit_price_huf, 2),
            "renovation_cost_huf": round(flip.renovation_cost_huf + flip.contingency_huf, 2),
            "total_investment_huf": round(flip.total_cash_needed_huf, 2),
            "net_profit_huf": round(flip.net_profit_huf, 2),
            "flip_roi_percent": round(flip.roi_percent, 2),
            "rental_yield_percent": prop.underwriting_rental_yield_percent,
            "deal_score": score,
            "status": "validated" if flip.verdict == "buy" else ("risk:below_hurdle_roi" if flip.verdict == "skip" else "consider"),
            "confidence_tag": "High Potential Flip" if flip.verdict == "buy" else None,
            "updated_at": prop.underwriting_updated_at.isoformat() if prop.underwriting_updated_at else None,
        }
    has_underwriting = prop.underwriting_updated_at is not None
    if not has_underwriting and best_tier is None:
        return None
    return {
        "estimated_market_value_huf": prop.underwriting_market_value_huf
        if prop.underwriting_market_value_huf is not None
        else (best_tier["exit_price_huf"] if best_tier else None),
        "renovation_cost_huf": prop.underwriting_renovation_cost_huf
        if prop.underwriting_renovation_cost_huf is not None
        else (best_tier["renovation_cost_huf"] if best_tier else None),
        "total_investment_huf": prop.underwriting_total_investment_huf
        if prop.underwriting_total_investment_huf is not None
        else (best_tier["total_investment_huf"] if best_tier else None),
        "net_profit_huf": prop.underwriting_net_profit_huf
        if prop.underwriting_net_profit_huf is not None
        else (best_tier["net_profit_huf"] if best_tier else None),
        "flip_roi_percent": prop.underwriting_flip_roi_percent
        if prop.underwriting_flip_roi_percent is not None
        else (best_tier["roi_percent"] if best_tier else None),
        "rental_yield_percent": prop.underwriting_rental_yield_percent
        if prop.underwriting_rental_yield_percent is not None
        else (best_tier["net_yield_percent"] if best_tier else None),
        "deal_score": prop.underwriting_deal_score if prop.underwriting_deal_score is not None else score,
        "status": prop.underwriting_status,
        "confidence_tag": prop.underwriting_confidence_tag,
        "updated_at": prop.underwriting_updated_at.isoformat() if prop.underwriting_updated_at else None,
    }


def compute_stats(db: Session, eur_huf_rate: float, top_n: int = 5) -> dict:
    """
    KPIs over ACTIVE listings only (seen within STALE_AFTER_DAYS).
    top_undervalued ranks by realistic flip ROI, newest-today first,
    falling back to all active listings on a quiet day.
    """
    now = datetime.datetime.utcnow()
    properties: List[models.Property] = [p for p in db.query(models.Property).all() if not is_stale(p, now)]
    total_listings = len(properties)
    cache = BenchmarkCache(db)

    priced = [p.price_per_sqm for p in properties if p.price_per_sqm]
    avg_price_sqm_huf = round(sum(priced) / len(priced), 2) if priced else None
    avg_price_sqm_eur = round(avg_price_sqm_huf / eur_huf_rate, 2) if avg_price_sqm_huf else None

    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    todays_properties = [p for p in properties if p.created_at and p.created_at >= today_start]

    is_today_only = True
    pool = todays_properties
    if not pool:
        is_today_only = False
        pool = properties

    scored = []
    verdict_counts = {"buy": 0, "consider": 0, "skip": 0}
    for prop in properties:
        flip = compute_flip(prop, cache)
        if flip is not None:
            verdict_counts[flip.verdict] += 1
    for prop in pool:
        benchmark = cache.district(prop.district)
        flip = compute_flip(prop, cache)
        if benchmark is None or flip is None:
            continue
        scored.append((flip.roi_percent, prop, benchmark, flip))

    scored.sort(key=lambda t: t[0], reverse=True)
    top_undervalued = [
        {
            "property_id": prop.id,
            "title": prop.title,
            "district": prop.district,
            "price_huf": prop.price_huf,
            "price_per_sqm": prop.price_per_sqm,
            "benchmark_price_per_sqm": _reference_price_sqm(prop, benchmark),
            "discount_percent": round(flip.discount_vs_market_percent, 2)
            if flip.discount_vs_market_percent is not None
            else None,
            "roi_percent": round(flip.roi_percent, 2),
            "verdict": flip.verdict,
        }
        for _roi, prop, benchmark, flip in scored[:top_n]
    ]

    last_seen_values = [p.last_seen_at for p in properties if p.last_seen_at]
    return {
        "total_listings": total_listings,
        "avg_price_sqm_huf": avg_price_sqm_huf,
        "avg_price_sqm_eur": avg_price_sqm_eur,
        "eur_huf_rate": eur_huf_rate,
        "top_undervalued": top_undervalued,
        "is_today_only": is_today_only,
        "today_new_listings": len(todays_properties),
        "verdict_counts": verdict_counts,
        "last_scan_at": max(last_seen_values).isoformat() + "Z" if last_seen_values else None,
        "computed_at": now.isoformat() + "Z",
    }


SORT_OPTIONS = ("newest", "price_desc", "price_asc", "score_desc", "roi_desc", "sqm_asc", "roi_score_desc", "profit_desc")

DEFAULT_SORT = "roi_score_desc"


def _roi_key(d: dict):
    flip = d.get("flip")
    roi = flip["roi_percent"] if flip else None
    return (roi is None, -(roi or 0))


def _sort_deals(deals: List[dict], sort_by: str) -> List[dict]:
    if sort_by == "price_desc":
        return sorted(deals, key=lambda d: (d["price_huf"] is None, -(d["price_huf"] or 0)))
    if sort_by == "price_asc":
        return sorted(deals, key=lambda d: (d["price_huf"] is None, d["price_huf"] or 0))
    if sort_by == "score_desc":
        return sorted(deals, key=lambda d: (d["deal_score"] is None, -(d["deal_score"] or 0)))
    if sort_by in ("roi_desc", "roi_score_desc"):
        return sorted(deals, key=lambda d: (*_roi_key(d), d["deal_score"] is None, -(d["deal_score"] or 0)))
    if sort_by == "profit_desc":
        return sorted(
            deals,
            key=lambda d: (d.get("flip") is None, -((d.get("flip") or {}).get("net_profit_huf") or 0)),
        )
    if sort_by == "sqm_asc":
        return sorted(deals, key=lambda d: (d["price_per_sqm"] is None, d["price_per_sqm"] or 0))
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
    verdicts: Optional[List[str]] = None,
    include_stale: bool = False,
    with_total: bool = False,
):
    """
    Active listings (not seen for > STALE_AFTER_DAYS -> hidden unless
    include_stale) enriched with the realistic flip verdict (`flip`), the
    interactive tier analysis, and the Deal Score, filtered, sorted, paged.
    min_roi / min_flip_roi both filter on the realistic after-tax flip ROI.
    with_total=True returns (page, total_matching) for pagination.
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

    cache = BenchmarkCache(db)
    now = datetime.datetime.utcnow()
    deals = []
    for prop in properties:
        stale = is_stale(prop, now)
        if stale and not include_stale and not prop.is_favorite:
            continue  # favorites stay visible even after the ad disappears

        flip = compute_flip(prop, cache)
        roi = flip.roi_percent if flip else None
        if min_roi is not None and (roi is None or roi < min_roi):
            continue
        if min_flip_roi is not None and roi is not None and roi < min_flip_roi:
            continue
        if verdicts and (flip is None or flip.verdict not in verdicts):
            continue

        analysis_dict, best_tier, discount_percent, score = compute_live_deal_metrics(db, prop, eur_huf_rate, cache)
        underwriting = build_underwriting_dict(prop, best_tier, score, flip)
        benchmark = cache.district(prop.district)
        scenarios = scenario_analysis.compute_scenarios(prop, benchmark)

        price_drop_percent = None
        if prop.previous_price_huf and prop.price_huf and prop.previous_price_huf > 0:
            price_drop_percent = round((prop.previous_price_huf - prop.price_huf) / prop.previous_price_huf * 100, 1)

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
                "source_url": prop.url,
                "duplicate_source_urls": prop.duplicate_source_urls or [],
                "condition": prop.condition,
                "condition_tag": classify_condition_tag(prop.condition),
                "images": prop.images or [],
                "portal": prop.portal,
                "latitude": prop.latitude,
                "longitude": prop.longitude,
                "is_favorite": prop.is_favorite,
                "pipeline_status": prop.pipeline_status,
                "notes": prop.notes,
                "building_type": prop.building_type,
                "ceiling_height_m": prop.ceiling_height_m,
                "sub_district": prop.sub_district,
                "created_at": prop.created_at.isoformat() if prop.created_at else None,
                "last_seen_at": _last_seen(prop).isoformat() if _last_seen(prop) else None,
                "is_stale": stale,
                "previous_price_huf": prop.previous_price_huf,
                "price_drop_percent": price_drop_percent,
                "analysis": analysis_dict,
                "best_tier": best_tier,
                "discount_percent": discount_percent,
                "deal_score": score,
                "deal_score_band": deal_score_module.score_band(score),
                "underwriting": underwriting,
                "scenarios": scenarios,
                "flip": flip.to_dict() if flip else None,
            }
        )

    deals = _sort_deals(deals, sort_by)
    total = len(deals)
    if limit is not None:
        deals = deals[skip : skip + limit]
    elif skip:
        deals = deals[skip:]
    return (deals, total) if with_total else deals


# Column order for deals_to_csv() — deliberately flat (no nested objects),
# pulling the underwriting metrics out of the nested `underwriting` dict so
# every row is spreadsheet-ready with no post-processing.
_CSV_COLUMNS = [
    "id", "title", "district", "sub_district", "address", "size_sqm", "rooms", "balcony_sqm",
    "building_type", "ceiling_height_m",
    "price_huf", "price_eur", "price_per_sqm", "condition", "condition_tag",
    "portal", "url", "duplicate_source_urls", "pipeline_status", "is_favorite", "notes", "created_at",
    "last_seen_at", "previous_price_huf", "price_drop_percent",
    "flip_verdict", "flip_roi_percent", "flip_net_profit_huf", "flip_max_offer_price_huf",
    "flip_exit_price_huf", "flip_renovation_cost_huf", "flip_scope", "flip_confidence",
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
        flip = deal.get("flip") or {}
        row["flip_verdict"] = flip.get("verdict")
        row["flip_roi_percent"] = flip.get("roi_percent")
        row["flip_net_profit_huf"] = flip.get("net_profit_huf")
        row["flip_max_offer_price_huf"] = flip.get("max_offer_price_huf")
        row["flip_exit_price_huf"] = flip.get("exit_price_huf")
        row["flip_renovation_cost_huf"] = flip.get("renovation_cost_huf")
        row["flip_scope"] = flip.get("scope")
        row["flip_confidence"] = flip.get("confidence")
        writer.writerow(row)
    return buffer.getvalue()
