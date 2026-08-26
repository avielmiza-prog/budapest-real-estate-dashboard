"""
Pure text-parsing helpers for turning the messy Hungarian text on a real
estate listing page into clean numeric/string fields.

Deliberately dependency-free (re + stdlib only, plus app.analyzer which is
itself dependency-free) so these can be unit-tested without Playwright,
SQLAlchemy, or a network connection — see tests/test_text_parsing.py.
"""
import re
from typing import Optional

from app.analyzer import district_number_to_roman

# ---------------------------------------------------------------------------
# Price
# ---------------------------------------------------------------------------

# Matches "89 900 000", "89.900.000", "89,900,000", "89900000" as one number,
# with optional thousand separators (space, dot, comma, non-breaking space).
_NUMBER_RE = re.compile(r"(\d[\d\s., ]*\d|\d)")


def _parse_number(text: str) -> Optional[float]:
    match = _NUMBER_RE.search(text)
    if not match:
        return None
    raw = match.group(1)
    cleaned = re.sub(r"[\s., ]", "", raw)
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_price_huf(text: str) -> Optional[float]:
    """
    "89 900 000 Ft" -> 89900000.0
    "45,5 M Ft" / "45.5 millió Ft" -> 45_500_000.0  (M/millió shorthand)
    Returns None if no HUF price is found in the text.
    """
    if not text:
        return None
    lowered = text.lower()
    if "ft" not in lowered and "huf" not in lowered:
        return None

    # "45.5 M Ft" / "45,5 millió Ft" shorthand
    million_match = re.search(r"(\d+[.,]?\d*)\s*(m|millió)\s*ft", lowered)
    if million_match:
        value = float(million_match.group(1).replace(",", "."))
        return value * 1_000_000

    return _parse_number(text)


def parse_price_eur(text: str) -> Optional[float]:
    """"289 000 €" / "289,000 EUR" -> 289000.0. Returns None if not present."""
    if not text:
        return None
    lowered = text.lower()
    if "€" not in text and "eur" not in lowered:
        return None
    return _parse_number(text)


# ---------------------------------------------------------------------------
# Size
# ---------------------------------------------------------------------------

_SIZE_RE = re.compile(r"(\d+[.,]?\d*)\s*(?:m2|m²|nm|sqm)", re.IGNORECASE)


def parse_size_sqm(text: str) -> Optional[float]:
    """"55 m²" / "55m2" / "55 nm" -> 55.0"""
    if not text:
        return None
    match = _SIZE_RE.search(text)
    if not match:
        return None
    return float(match.group(1).replace(",", "."))


# ---------------------------------------------------------------------------
# Rooms
# ---------------------------------------------------------------------------

# Hungarian listings often express room counts as "whole + half", where a
# "half room" (fél szoba) is a small room (~<12sqm), traditionally counted
# as 0.5 of a full room, e.g. "2+1" = 2 full + 1 half = 2.5 total.
_ROOMS_COMBO_RE = re.compile(r"(\d+)\s*\+\s*(\d+)\s*(?:fél)?")
_ROOMS_PLAIN_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*szob")


def parse_rooms(text: str) -> Optional[float]:
    """
    "2+1 fél szoba" -> 2.5
    "4+2" -> 5.0
    "3 szoba" -> 3.0
    "2.5 szoba" -> 2.5
    """
    if not text:
        return None
    combo = _ROOMS_COMBO_RE.search(text)
    if combo:
        whole, half = int(combo.group(1)), int(combo.group(2))
        return whole + half * 0.5
    plain = _ROOMS_PLAIN_RE.search(text)
    if plain:
        return float(plain.group(1).replace(",", "."))
    # Bare number with no other qualifier, e.g. just "3"
    bare = re.fullmatch(r"\s*(\d+(?:[.,]\d+)?)\s*", text)
    if bare:
        return float(bare.group(1).replace(",", "."))
    return None


# ---------------------------------------------------------------------------
# District
# ---------------------------------------------------------------------------

_KERULET_ROMAN_RE = re.compile(
    r"\b(X{0,2}(?:IX|IV|V?I{0,3}))\s*\.?\s*ker(?:ület|\.)?", re.IGNORECASE
)
_KERULET_ARABIC_RE = re.compile(r"\b(\d{1,2})\s*\.?\s*ker(?:ület|\.)?", re.IGNORECASE)
# Budapest postal codes are 1XY0-1XY9, where XY is (almost always) the district number.
_POSTCODE_RE = re.compile(r"\b1(\d{2})\d\b")

_VALID_ROMANS = {district_number_to_roman(n) for n in range(1, 24)}


def extract_district_roman(text: str) -> Optional[str]:
    """
    Best-effort extraction of the Budapest district (as a roman numeral, e.g.
    "VII") from a free-text address/title/description string. Tries, in
    order: "<roman>. kerület", "<arabic>. kerület", then falls back to the
    Budapest postal-code convention (postcode 1XY0-1XY9 -> district XY).

    Returns None if nothing matching a valid district (1-23) is found.
    """
    if not text:
        return None

    roman_match = _KERULET_ROMAN_RE.search(text)
    if roman_match:
        candidate = roman_match.group(1).upper()
        if candidate in _VALID_ROMANS:
            return candidate

    arabic_match = _KERULET_ARABIC_RE.search(text)
    if arabic_match:
        number = int(arabic_match.group(1))
        if 1 <= number <= 23:
            return district_number_to_roman(number)

    postcode_match = _POSTCODE_RE.search(text)
    if postcode_match:
        number = int(postcode_match.group(1))
        if 1 <= number <= 23:
            return district_number_to_roman(number)

    return None
