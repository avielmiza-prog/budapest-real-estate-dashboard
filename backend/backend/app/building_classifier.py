"""
Building-construction-type classification and ceiling-height extraction from
raw scraped Hungarian listing text — a distinct axis from
app.condition_classifier (which is about a unit's finish/condition, not the
building it's in).

Three recognized types, in the order Hungarian listings usually distinguish
them:
  - Brick Classical ("Polgári"): pre-WWII masonry buildings, typically with
    high ceilings (3m+) and period detailing. Renovations here cost more per
    sqm — plaster/molding restoration, higher walls to paint/re-wire, often
    heritage-protection constraints.
  - Panel Block ("Panelház"): prefab concrete panel buildings (1960s-80s
    Soviet-era mass housing). Standardized layouts, low ceilings, cheaper to
    renovate per sqm — no period features to preserve, simpler wall/floor
    plans.
  - New Build ("Új építés"): modern (post-2000s) construction, usually
    already move-in ready — renovation is rarely needed at all.

Kept as its own leaf module (no app.* imports besides nothing) for the same
reason as app.condition_classifier: safely importable from anywhere
(app/renovation_estimator.py, scraper/normalize.py, app/schemas.py) without
risking a circular import.
"""
import re
from typing import Optional

BUILDING_TYPE_BRICK_CLASSICAL = "Brick Classical (Polgári)"
BUILDING_TYPE_PANEL_BLOCK = "Panel Block (Panelház)"
BUILDING_TYPE_NEW_BUILD = "New Build (Új építés)"

# Keyword (Hungarian, case-insensitive substring match) -> building type.
# Checked in this order, first match wins. "Új építés" is checked first since
# a listing describing a brand-new brick building should be classified by
# its age/finish (new build), not its wall material.
_BUILDING_TYPE_KEYWORDS = [
    (
        BUILDING_TYPE_NEW_BUILD,
        ("új építésű", "uj epitesu", "újépítésű", "ujepitesu", "újépítés", "ujepites", "new build"),
    ),
    (
        BUILDING_TYPE_PANEL_BLOCK,
        ("panelház", "panelhaz", "panel lakás", "panel lakas", "paneles", "panel program"),
    ),
    (
        BUILDING_TYPE_BRICK_CLASSICAL,
        (
            "polgári", "polgari", "polgári lakás", "téglaépítésű", "teglaepitesu", "tégla építésű",
            "tegla epitesu", "eklektikus", "historizáló", "historizalo", "századforduló", "szazadfordulo",
        ),
    ),
]

_DEFAULT_RENOVATION_MULTIPLIER = 1.0

# Multiplier applied on top of app.condition_classifier's condition-based
# per-sqm renovation estimate — see app/renovation_estimator.py. Polgári
# buildings cost more to renovate per sqm (period features, higher walls,
# often heritage constraints); Panelház costs less (standardized, no
# features to preserve); New Build is a neutral 1.0 (renovation is rarely
# needed there at all, so the condition-based estimate already reflects
# that via a "Renovated"/"New Construction" tag most of the time).
_RENOVATION_MULTIPLIER_BY_TYPE = {
    BUILDING_TYPE_BRICK_CLASSICAL: 1.25,
    BUILDING_TYPE_PANEL_BLOCK: 0.85,
    BUILDING_TYPE_NEW_BUILD: 1.0,
}

# Additional multiplier for a high-ceiling Polgári unit specifically — more
# wall/ceiling area to plaster, paint, and rewire per sqm of floor space than
# the ceiling-height-agnostic base multiplier above already accounts for.
_HIGH_CEILING_THRESHOLD_M = 3.0
_HIGH_CEILING_EXTRA_MULTIPLIER = 1.10

# The unit token (m/méter/meter) is mandatory and nothing but whitespace may
# sit between it and "belmagas" — earlier drafts allowed an arbitrary \w*
# run there (to catch suffixes like "belmagasságú"), but that also let an
# unrelated number+word ("70 m2 lakas belmagassaga...") false-match. Requiring
# the unit directly, with no intervening word, keeps this specific to an
# actual "<number> m belmagasság..." mention.
_CEILING_HEIGHT_RE = re.compile(
    r"(\d[.,]?\d?)\s*(?:m|méter|meter)\.?\s*belmagas", re.IGNORECASE
)

# Sanity bounds for a real residential ceiling height — anything the regex
# matches outside this range is almost certainly a false positive (a stray
# number from elsewhere in the text landing next to "belmagas...") rather
# than a real measurement, so it's discarded instead of surfaced as garbage
# in the UI (e.g. "70.0 m").
_PLAUSIBLE_CEILING_HEIGHT_RANGE_M = (2.0, 6.0)


def classify_building_type(text: Optional[str]) -> Optional[str]:
    """Best-effort building type from free-text listing content, or None if no keyword matched."""
    lowered = (text or "").lower()
    if not lowered:
        return None
    for building_type, keywords in _BUILDING_TYPE_KEYWORDS:
        if any(keyword in lowered for keyword in keywords):
            return building_type
    return None


def extract_ceiling_height_m(text: Optional[str]) -> Optional[float]:
    """
    "3,2 m belmagasság" / "magas belmagasságú" -> 3.2 / None (no number).
    Returns None when no ceiling-height mention is found at all.
    """
    if not text:
        return None
    match = _CEILING_HEIGHT_RE.search(text)
    if not match:
        return None
    try:
        value = float(match.group(1).replace(",", "."))
    except ValueError:
        return None
    low, high = _PLAUSIBLE_CEILING_HEIGHT_RANGE_M
    return value if low <= value <= high else None


def renovation_cost_multiplier(building_type: Optional[str], ceiling_height_m: Optional[float]) -> float:
    """
    Multiplier applied to the condition-based baseline HUF/sqm renovation
    estimate (see app/renovation_estimator.py) — how much more/less a
    renovation costs per sqm for this building type and ceiling height.
    Unknown building type -> neutral 1.0 (never assume a discount or premium
    with no evidence).
    """
    multiplier = _RENOVATION_MULTIPLIER_BY_TYPE.get(building_type, _DEFAULT_RENOVATION_MULTIPLIER)
    if (
        building_type == BUILDING_TYPE_BRICK_CLASSICAL
        and ceiling_height_m is not None
        and ceiling_height_m >= _HIGH_CEILING_THRESHOLD_M
    ):
        multiplier *= _HIGH_CEILING_EXTRA_MULTIPLIER
    return multiplier
