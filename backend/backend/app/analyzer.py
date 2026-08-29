"""
Flip/renovation financial analysis for a Budapest property.

Given a property's size, district, and asking price, this module estimates —
for each of three renovation tiers — the renovation cost, total investment,
expected exit (resale) price after renovation, net profit, and ROI.

Pure-math functions here take plain numbers (no DB/ORM dependency), so this
module can be imported and unit-tested with nothing but the standard library.
A thin DB-aware wrapper at the bottom (`analyze_property_by_id`) is the
convenience path that pulls a Property + its district's DistrictBenchmark
straight out of the database.

--------------------------------------------------------------------------
ASSUMPTIONS (call these out to the user — they're the levers most likely to
need tuning as real market data comes in):

- EUR/HUF exchange rate: renovation costs are given in EUR/sqm, but Hungarian
  transaction costs and district benchmarks are naturally in HUF. A default
  rate is used (see DEFAULT_EUR_HUF_RATE below) — pass `eur_huf_rate=` to
  override with the day's actual rate.
- Acquisition costs = 4% property transfer tax ("visszterhes vagyonátruházási
  illeték") + 1% legal/notary fee, both applied to the asking price. Does not
  include mortgage/financing costs, since those depend on the buyer.
- Exit price after renovation = district's `avg_price_sqm_renovated` (HUF/sqm)
  x size_sqm. This assumes the property, once renovated to that tier, sells
  at the district's average renovated price/sqm — a simplification; a "Light"
  renovation realistically wouldn't reach the same finish level as "Full",
  but the prompt's spec only gives one renovated benchmark per district, so
  the same exit price is used across all three tiers here. Flag this if you
  want tier-differentiated exit pricing (e.g. Light -> blend of raw/renovated
  benchmarks) instead.
- Net profit does not subtract a resale agent commission or capital gains
  tax, since neither was specified. Both are easy to add as extra rate
  constants if wanted.
- Weighted usable area: when a property has a balcony/terrace size on file,
  renovation cost and exit price are based on `size_sqm + balcony_sqm * 0.5`
  (standard "half-weighted balcony" valuation convention), not raw interior
  size_sqm alone. Falls back to size_sqm alone when balcony_sqm is unknown.
- A 5% safety buffer is included in total investment/ROI (on top of price +
  transfer tax + legal fee + renovation cost), covering unforeseen costs —
  this changed `total_investment_huf`'s formula from an earlier version of
  this module that omitted it; every field name stays the same, only the
  number now includes the buffer.
- Rental yield (gross/net) is only computed when a district's
  avg_rent_huf_sqm benchmark is available; otherwise those fields are None
  rather than a fabricated estimate. Net yield assumes a flat 20% of gross
  rent goes to management/maintenance/vacancy (RENTAL_OPEX_RATE) — a
  simplification, not a verified operating-cost model.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Constants (tune these as real numbers come in)
# ---------------------------------------------------------------------------

# EUR -> HUF. Update to the current rate, or pass eur_huf_rate= explicitly
# per call. (~390-410 has been a typical recent range; this is a placeholder,
# not a live rate.)
DEFAULT_EUR_HUF_RATE = 400.0

# EUR / sqm renovation cost, by tier.
RENOVATION_TIERS_EUR_PER_SQM: Dict[str, float] = {
    "light": 250.0,
    "medium": 450.0,
    "full": 700.0,
}

PROPERTY_TRANSFER_TAX_RATE = 0.04  # Hungarian "illeték"
LEGAL_NOTARY_FEE_RATE = 0.01
ACQUISITION_COST_RATE = PROPERTY_TRANSFER_TAX_RATE + LEGAL_NOTARY_FEE_RATE  # 5%

# Applied to (price + transfer tax + legal fee + renovation cost), covers
# unforeseen costs on top of the itemized ones above.
SAFETY_BUFFER_RATE = 0.05

# Weighted-balcony valuation: usable_area_sqm = size_sqm + balcony_sqm * BALCONY_WEIGHT.
BALCONY_WEIGHT = 0.5

# Flat assumption for rental-yield "net" figures: management/maintenance/vacancy.
RENTAL_OPEX_RATE = 0.20

# Budapest districts I-XXIII, for parsing Property.district values like "VII"
# into the integer district_number DistrictBenchmark is keyed on.
_ROMAN_NUMERALS = [
    "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X",
    "XI", "XII", "XIII", "XIV", "XV", "XVI", "XVII", "XVIII", "XIX", "XX",
    "XXI", "XXII", "XXIII",
]
_ROMAN_TO_INT = {roman: i + 1 for i, roman in enumerate(_ROMAN_NUMERALS)}


def parse_district_number(district: str) -> int:
    """
    Convert a Property.district value ("VII", "13", "13.", "XIII kerület", ...)
    into the plain int DistrictBenchmark.district_number is keyed on.

    Raises ValueError if it can't be parsed into 1-23.
    """
    text = district.strip().upper()
    # Strip common Hungarian suffix/noise, e.g. "XIII. KERÜLET" -> "XIII"
    text = text.replace("KERÜLET", "").replace("KERULET", "").strip(" .")

    if text in _ROMAN_TO_INT:
        return _ROMAN_TO_INT[text]

    try:
        number = int(text)
    except ValueError:
        raise ValueError(f"Could not parse district_number from district={district!r}")

    if not 1 <= number <= 23:
        raise ValueError(f"district_number {number} out of range 1-23 (parsed from {district!r})")
    return number


def district_number_to_roman(district_number: int) -> str:
    """Inverse of parse_district_number's roman-numeral side: 7 -> 'VII'."""
    if not 1 <= district_number <= 23:
        raise ValueError(f"district_number {district_number} out of range 1-23")
    return _ROMAN_NUMERALS[district_number - 1]


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class RenovationTierResult:
    tier: str  # "light" | "medium" | "full" | "custom"
    cost_eur_per_sqm: float
    renovation_cost_huf: float
    safety_buffer_huf: float
    total_investment_huf: float
    exit_price_huf: float
    net_profit_huf: float
    roi_percent: Optional[float]  # None if total_investment_huf is 0 (can't divide)
    gross_annual_rent_huf: Optional[float] = None
    gross_yield_percent: Optional[float] = None
    net_yield_percent: Optional[float] = None

    @property
    def break_even_price_huf(self) -> float:
        """
        The sale price at which net_profit_huf would be exactly 0 — i.e. the
        minimum exit price that recoups the full total investment. Since
        net_profit_huf = exit_price_huf - total_investment_huf, that's just
        total_investment_huf itself; kept as its own named field so the
        underwriting UI can label it distinctly from "total investment".
        """
        return self.total_investment_huf

    def to_dict(self) -> dict:
        return {
            "tier": self.tier,
            "cost_eur_per_sqm": self.cost_eur_per_sqm,
            "renovation_cost_huf": round(self.renovation_cost_huf, 2),
            "safety_buffer_huf": round(self.safety_buffer_huf, 2),
            "total_investment_huf": round(self.total_investment_huf, 2),
            "break_even_price_huf": round(self.break_even_price_huf, 2),
            "exit_price_huf": round(self.exit_price_huf, 2),
            "net_profit_huf": round(self.net_profit_huf, 2),
            "roi_percent": round(self.roi_percent, 2) if self.roi_percent is not None else None,
            "gross_annual_rent_huf": round(self.gross_annual_rent_huf, 2)
            if self.gross_annual_rent_huf is not None
            else None,
            "gross_yield_percent": round(self.gross_yield_percent, 2)
            if self.gross_yield_percent is not None
            else None,
            "net_yield_percent": round(self.net_yield_percent, 2)
            if self.net_yield_percent is not None
            else None,
        }


@dataclass
class PropertyAnalysis:
    size_sqm: float
    district: Optional[str]
    asking_price_huf: float
    eur_huf_rate: float
    acquisition_cost_huf: float
    property_transfer_tax_huf: float
    legal_notary_fee_huf: float
    avg_price_sqm_renovated_huf: float
    exit_price_huf: float
    balcony_sqm: Optional[float] = None
    usable_area_sqm: float = 0.0
    avg_rent_huf_sqm: Optional[float] = None
    tiers: List[RenovationTierResult] = field(default_factory=list)
    # Transparency on avg_price_sqm_renovated_huf's origin — see
    # app.services.stats_service.update_district_benchmarks(). None when the
    # caller didn't supply it (e.g. analyze_property() called directly, off
    # a hand-built number rather than a DB benchmark row).
    district_median_sample_count: Optional[int] = None
    district_median_source: Optional[str] = None  # "live" | "fallback" | None

    def to_dict(self) -> dict:
        return {
            "size_sqm": self.size_sqm,
            "district": self.district,
            "asking_price_huf": self.asking_price_huf,
            "eur_huf_rate": self.eur_huf_rate,
            "acquisition_cost_huf": round(self.acquisition_cost_huf, 2),
            "property_transfer_tax_huf": round(self.property_transfer_tax_huf, 2),
            "legal_notary_fee_huf": round(self.legal_notary_fee_huf, 2),
            "avg_price_sqm_renovated_huf": self.avg_price_sqm_renovated_huf,
            "exit_price_huf": round(self.exit_price_huf, 2),
            "balcony_sqm": self.balcony_sqm,
            "usable_area_sqm": round(self.usable_area_sqm, 2),
            "avg_rent_huf_sqm": self.avg_rent_huf_sqm,
            "tiers": [t.to_dict() for t in self.tiers],
            "district_median_sample_count": self.district_median_sample_count,
            "district_median_source": self.district_median_source,
        }

    def best_tier(self) -> Optional[RenovationTierResult]:
        """Tier with the highest ROI (None-ROI tiers are ignored)."""
        scored = [t for t in self.tiers if t.roi_percent is not None]
        if not scored:
            return None
        return max(scored, key=lambda t: t.roi_percent)


# ---------------------------------------------------------------------------
# Core (pure) calculation
# ---------------------------------------------------------------------------

def calculate_property_transfer_tax_huf(asking_price_huf: float) -> float:
    """Hungarian 4% property transfer tax ("visszterhes vagyonátruházási illeték")."""
    if asking_price_huf < 0:
        raise ValueError("asking_price_huf must be >= 0")
    return asking_price_huf * PROPERTY_TRANSFER_TAX_RATE


def calculate_legal_notary_fee_huf(asking_price_huf: float) -> float:
    """1% legal/notary fee, applied to the asking price."""
    if asking_price_huf < 0:
        raise ValueError("asking_price_huf must be >= 0")
    return asking_price_huf * LEGAL_NOTARY_FEE_RATE


def calculate_acquisition_costs(asking_price_huf: float) -> float:
    """4% transfer tax + 1% legal/notary fee, applied to the asking price."""
    return calculate_property_transfer_tax_huf(asking_price_huf) + calculate_legal_notary_fee_huf(
        asking_price_huf
    )


def calculate_renovation_cost_huf(
    size_sqm: float, tier: str, eur_huf_rate: float = DEFAULT_EUR_HUF_RATE
) -> float:
    if size_sqm < 0:
        raise ValueError("size_sqm must be >= 0")
    tier_key = tier.lower()
    if tier_key not in RENOVATION_TIERS_EUR_PER_SQM:
        valid = ", ".join(RENOVATION_TIERS_EUR_PER_SQM)
        raise ValueError(f"Unknown renovation tier {tier!r}. Valid tiers: {valid}")
    return size_sqm * RENOVATION_TIERS_EUR_PER_SQM[tier_key] * eur_huf_rate


def calculate_exit_price_huf(size_sqm: float, avg_price_sqm_renovated_huf: float) -> float:
    if avg_price_sqm_renovated_huf < 0:
        raise ValueError("avg_price_sqm_renovated_huf must be >= 0")
    return size_sqm * avg_price_sqm_renovated_huf


def calculate_usable_area_sqm(size_sqm: float, balcony_sqm: Optional[float] = None) -> float:
    """Interior size_sqm plus balcony/terrace counted at BALCONY_WEIGHT (50%)."""
    return size_sqm + (balcony_sqm or 0) * BALCONY_WEIGHT


def calculate_safety_buffer_huf(
    asking_price_huf: float,
    property_transfer_tax_huf: float,
    legal_notary_fee_huf: float,
    renovation_cost_huf: float,
) -> float:
    """5% buffer on top of price + transfer tax + legal fee + renovation cost."""
    return SAFETY_BUFFER_RATE * (
        asking_price_huf + property_transfer_tax_huf + legal_notary_fee_huf + renovation_cost_huf
    )


def calculate_rental_yields(
    usable_area_sqm: float, avg_rent_huf_sqm: Optional[float], total_investment_huf: float
) -> tuple:
    """
    Returns (gross_annual_rent_huf, gross_yield_percent, net_yield_percent),
    all None if avg_rent_huf_sqm isn't known or total_investment_huf is 0.
    """
    if not avg_rent_huf_sqm or total_investment_huf <= 0:
        return None, None, None
    gross_annual_rent_huf = avg_rent_huf_sqm * usable_area_sqm * 12
    gross_yield_percent = gross_annual_rent_huf / total_investment_huf * 100
    net_yield_percent = gross_annual_rent_huf * (1 - RENTAL_OPEX_RATE) / total_investment_huf * 100
    return gross_annual_rent_huf, gross_yield_percent, net_yield_percent


def analyze_property(
    size_sqm: float,
    asking_price_huf: float,
    avg_price_sqm_renovated_huf: float,
    district: Optional[str] = None,
    eur_huf_rate: float = DEFAULT_EUR_HUF_RATE,
    balcony_sqm: Optional[float] = None,
    avg_rent_huf_sqm: Optional[float] = None,
    custom_cost_eur_per_sqm: Optional[float] = None,
    district_median_sample_count: Optional[int] = None,
    district_median_source: Optional[str] = None,
) -> PropertyAnalysis:
    """
    Run the full flip analysis for one property across the Light/Medium/Full
    renovation tiers, plus an optional "custom" tier when
    custom_cost_eur_per_sqm is given. All money in, money out.

    district_median_sample_count/district_median_source are pass-through
    metadata about avg_price_sqm_renovated_huf's origin (see
    PropertyAnalysis) — purely informational, no effect on the math.

    Raises ValueError on invalid (negative) numeric inputs.
    """
    if size_sqm <= 0:
        raise ValueError("size_sqm must be > 0")
    if custom_cost_eur_per_sqm is not None and custom_cost_eur_per_sqm < 0:
        raise ValueError("custom_cost_eur_per_sqm must be >= 0")

    usable_area_sqm = calculate_usable_area_sqm(size_sqm, balcony_sqm)
    property_transfer_tax_huf = calculate_property_transfer_tax_huf(asking_price_huf)
    legal_notary_fee_huf = calculate_legal_notary_fee_huf(asking_price_huf)
    acquisition_cost_huf = property_transfer_tax_huf + legal_notary_fee_huf
    exit_price_huf = calculate_exit_price_huf(usable_area_sqm, avg_price_sqm_renovated_huf)

    tier_costs: List[tuple] = list(RENOVATION_TIERS_EUR_PER_SQM.items())
    if custom_cost_eur_per_sqm is not None:
        tier_costs.append(("custom", custom_cost_eur_per_sqm))

    tier_results: List[RenovationTierResult] = []
    for tier, cost_eur_per_sqm in tier_costs:
        if tier in RENOVATION_TIERS_EUR_PER_SQM:
            renovation_cost_huf = calculate_renovation_cost_huf(usable_area_sqm, tier, eur_huf_rate)
        else:
            renovation_cost_huf = usable_area_sqm * cost_eur_per_sqm * eur_huf_rate

        safety_buffer_huf = calculate_safety_buffer_huf(
            asking_price_huf, property_transfer_tax_huf, legal_notary_fee_huf, renovation_cost_huf
        )
        total_investment_huf = (
            asking_price_huf + acquisition_cost_huf + renovation_cost_huf + safety_buffer_huf
        )
        net_profit_huf = exit_price_huf - total_investment_huf
        roi_percent = (
            (net_profit_huf / total_investment_huf) * 100 if total_investment_huf > 0 else None
        )
        gross_annual_rent_huf, gross_yield_percent, net_yield_percent = calculate_rental_yields(
            usable_area_sqm, avg_rent_huf_sqm, total_investment_huf
        )
        tier_results.append(
            RenovationTierResult(
                tier=tier,
                cost_eur_per_sqm=cost_eur_per_sqm,
                renovation_cost_huf=renovation_cost_huf,
                safety_buffer_huf=safety_buffer_huf,
                total_investment_huf=total_investment_huf,
                exit_price_huf=exit_price_huf,
                net_profit_huf=net_profit_huf,
                roi_percent=roi_percent,
                gross_annual_rent_huf=gross_annual_rent_huf,
                gross_yield_percent=gross_yield_percent,
                net_yield_percent=net_yield_percent,
            )
        )

    return PropertyAnalysis(
        size_sqm=size_sqm,
        district=district,
        asking_price_huf=asking_price_huf,
        eur_huf_rate=eur_huf_rate,
        acquisition_cost_huf=acquisition_cost_huf,
        property_transfer_tax_huf=property_transfer_tax_huf,
        legal_notary_fee_huf=legal_notary_fee_huf,
        avg_price_sqm_renovated_huf=avg_price_sqm_renovated_huf,
        exit_price_huf=exit_price_huf,
        balcony_sqm=balcony_sqm,
        usable_area_sqm=usable_area_sqm,
        avg_rent_huf_sqm=avg_rent_huf_sqm,
        tiers=tier_results,
        district_median_sample_count=district_median_sample_count,
        district_median_source=district_median_source,
    )


# ---------------------------------------------------------------------------
# DB-aware convenience wrapper (optional — requires SQLAlchemy + app.crud)
# ---------------------------------------------------------------------------

def analyze_property_by_id(
    db,
    property_id: int,
    district_number: Optional[int] = None,
    eur_huf_rate: float = DEFAULT_EUR_HUF_RATE,
    custom_cost_eur_per_sqm: Optional[float] = None,
) -> PropertyAnalysis:
    """
    Look up a stored Property and its district's DistrictBenchmark, then run
    analyze_property(). Import of app.crud/app.models is deferred to inside
    this function so analyzer.py stays importable even without SQLAlchemy
    installed (e.g. for quick standalone/CLI use or unit tests).

    If district_number is omitted, it's parsed from the property's own
    `district` field (e.g. "VII" -> 7) via parse_district_number().

    Raises LookupError if the property or its district benchmark is missing,
    or if the benchmark has no avg_price_sqm_renovated value yet. Raises
    ValueError if district_number is omitted and prop.district can't be parsed.
    """
    from app import crud  # local import, see docstring

    prop = crud.get_property(db, property_id)
    if prop is None:
        raise LookupError(f"Property {property_id} not found")
    if not prop.size_sqm:
        raise LookupError(f"Property {property_id} has no size_sqm recorded")
    if not prop.price_huf:
        raise LookupError(f"Property {property_id} has no price_huf recorded")

    if district_number is None:
        district_number = parse_district_number(prop.district)

    benchmark = crud.get_district_benchmark(db, district_number)
    if benchmark is None or benchmark.avg_price_sqm_renovated is None:
        raise LookupError(
            f"No avg_price_sqm_renovated benchmark available for district {district_number}"
        )

    return analyze_property(
        size_sqm=prop.size_sqm,
        asking_price_huf=prop.price_huf,
        avg_price_sqm_renovated_huf=benchmark.avg_price_sqm_renovated,
        district=prop.district,
        eur_huf_rate=eur_huf_rate,
        balcony_sqm=prop.balcony_sqm,
        avg_rent_huf_sqm=benchmark.avg_rent_huf_sqm,
        custom_cost_eur_per_sqm=custom_cost_eur_per_sqm,
        district_median_sample_count=benchmark.sample_count_renovated,
        district_median_source=benchmark.source_renovated,
    )


if __name__ == "__main__":
    # Quick manual sanity check / usage example — runs with stdlib only.
    demo = analyze_property(
        size_sqm=55,
        asking_price_huf=45_000_000,
        avg_price_sqm_renovated_huf=1_250_000,
        district="VII",
    )
    import json

    print(json.dumps(demo.to_dict(), indent=2, ensure_ascii=False))
    best = demo.best_tier()
    if best:
        print(f"\nBest ROI tier: {best.tier} ({best.roi_percent:.2f}%)")
