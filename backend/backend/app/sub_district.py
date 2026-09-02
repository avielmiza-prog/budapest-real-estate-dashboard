"""
Micro-neighborhood ("sub-district") extraction from raw scraped Hungarian
listing text — Budapest districts are large enough that price/character
varies a lot within one district (e.g. District XIII's riverside
Újlipótváros commands a real premium over its inland Angyalföld half).

Keyword-matched directly against listing text rather than derived from
postal code: a postal code is frequently absent from scraped listing text,
while investors and listings themselves almost always name the
micro-neighborhood explicitly (it's a real selling point), making a direct
keyword match both simpler and more reliable here.

Deliberately not exhaustive — covers the two pairs named in the platform
spec (XIII, VII) plus a handful of other well-known, commonly-referenced
Budapest micro-neighborhoods. A district with no match here isn't wrong,
just not yet broken down finer than the district level.

Kept as its own leaf module (no app.* imports) — same rationale as
app.condition_classifier / app.building_classifier.
"""
from typing import Dict, List, Optional, Tuple

# district (roman numeral) -> [(micro-neighborhood name, keywords), ...],
# checked in order, first match wins.
_NEIGHBORHOODS: Dict[str, List[Tuple[str, Tuple[str, ...]]]] = {
    "XIII": [
        ("Újlipótváros", ("újlipótváros", "ujlipotvaros")),
        ("Angyalföld", ("angyalföld", "angyalfold")),
    ],
    "VII": [
        ("Belső-Erzsébetváros", ("belső-erzsébetváros", "belso-erzsebetvaros", "belső erzsébetváros", "belso erzsebetvaros")),
        ("Külső-Erzsébetváros", ("külső-erzsébetváros", "kulso-erzsebetvaros", "külső erzsébetváros", "kulso erzsebetvaros")),
    ],
    "II": [
        ("Rózsadomb", ("rózsadomb", "rozsadomb")),
        ("Pasarét", ("pasarét", "pasaret")),
    ],
    "VI": [
        ("Terézváros", ("terézváros", "terezvaros")),
    ],
    "VIII": [
        ("Palotanegyed", ("palotanegyed",)),
        ("Józsefváros", ("józsefváros", "jozsefvaros")),
    ],
    "IX": [
        ("Ferencváros", ("ferencváros", "ferencvaros")),
    ],
}


def extract_sub_district(text: Optional[str], district_roman: Optional[str]) -> Optional[str]:
    """
    Best-effort micro-neighborhood name from free-text listing content,
    scoped to the neighborhoods known for `district_roman` (so a mention of
    "Angyalföld" elsewhere in a description can't misattribute a District
    VII listing). Returns None if the district isn't covered here or no
    keyword matched.
    """
    if not text or not district_roman:
        return None
    candidates = _NEIGHBORHOODS.get(district_roman.upper())
    if not candidates:
        return None
    lowered = text.lower()
    for name, keywords in candidates:
        if any(keyword in lowered for keyword in keywords):
            return name
    return None
