"""
Condition-text classification: raw scraped Hungarian condition text ->
(standardized English tag, point-estimate HUF/sqm renovation cost).

Kept as its own leaf module (no app.* imports) so it can be safely imported
from anywhere — app/services/valuation_agent.py (renovation-cost math),
app/dashboard.py and app/schemas.py (the `condition_tag` field powering the
frontend's color-coded condition badges), and app/investment_memo.py (the
Deal Memo PDF) — without risking a circular import through app.crud/
app.schemas (valuation_agent.py imports app.crud, which imports
app.schemas; if schemas.py had imported classify_condition_tag straight
from valuation_agent.py, that would cycle back on itself).
"""
from typing import Optional

CONDITION_NEEDS_RENOVATION = "Needs Renovation"
CONDITION_AVERAGE = "Average"
CONDITION_RENOVATED = "Renovated"
CONDITION_NEW_CONSTRUCTION = "New Construction"

# Condition-keyword (Hungarian, case-insensitive substring match) -> (English
# tag, point-estimate HUF/sqm renovation cost). Checked in this order
# (most-work-implied first), first match wins. Point estimates, not ranges.
_CONDITION_CATEGORIES = [
    (
        CONDITION_NEEDS_RENOVATION,
        220_000,
        ("felújítandó", "felujitando", "rossz állapotú", "rossz allapotu", "lakhatatlan",
         "bontásra", "bontasra", "vályog", "valyog", "romos"),
    ),
    (
        CONDITION_AVERAGE,
        120_000,
        ("átlagos", "atlagos", "jó állapotú", "jo allapotu", "lakható", "lakhato",
         "közepes", "kozepes", "részben felújított", "reszben felujitott",
         "jó állapotban", "jo allapotban"),
    ),
    (
        CONDITION_RENOVATED,
        0,
        ("felújított", "felujitott", "újszerű", "ujszeru", "turnkey", "kulcsrakész", "kulcsrakesz"),
    ),
    (
        CONDITION_NEW_CONSTRUCTION,
        0,
        ("új építésű", "uj epitesu", "újépítésű", "ujepitesu", "vadonatúj", "vadonatuj"),
    ),
]
_DEFAULT_CONDITION_CATEGORY = (CONDITION_AVERAGE, 120_000)  # unknown/missing condition text: assume average, never assume free


def classify_condition(condition_text: Optional[str]) -> tuple:
    """(English condition tag, point-estimate HUF/sqm renovation cost) — see table above."""
    text = (condition_text or "").lower()
    for tag, cost, keywords in _CONDITION_CATEGORIES:
        if any(keyword in text for keyword in keywords):
            return tag, cost
    return _DEFAULT_CONDITION_CATEGORY


def classify_condition_tag(condition_text: Optional[str]) -> str:
    """Standardized English condition tag for badges/PDF — see classify_condition()."""
    return classify_condition(condition_text)[0]


def estimate_renovation_cost_huf_per_sqm(condition_text: Optional[str]) -> float:
    """Point-estimate HUF/sqm for the matched condition category — see classify_condition()."""
    return classify_condition(condition_text)[1]
