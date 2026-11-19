"""
Listing-level red flags and adjustments: what an experienced Budapest
investor would spot in the ad before running any numbers.

Each check reads only what the ad actually says (floor, elevator,
description text). A flag either:
  - adjusts the expected sale price (exit_factor < 1.0): ground floor,
    basement, high floor without elevator — these sell for less, or
  - blocks a confident "buy" (blocker=True): legal/ownership problems
    that make the standard flip math meaningless until checked (usufruct,
    municipal rental rights, auction, undivided co-ownership...).

Pure functions, no DB. Used by app.flip_model.
"""
import re
from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class Flag:
    code: str
    exit_factor: float = 1.0
    blocker: bool = False
    positive: bool = False


def _floor_number(floor: Optional[str]) -> Optional[int]:
    if not floor:
        return None
    f = floor.strip().lower()
    if "szuterén" in f or "pince" in f:
        return -1
    if "földszint" in f or "fsz" in f:
        return 0
    if "félemelet" in f or "magasföldszint" in f:
        return 0
    m = re.search(r"\d+", f)
    return int(m.group(0)) if m else None


# (code, regex, exit_factor, blocker)
_TEXT_CHECKS = [
    ("usufruct", r"haszonélvez", 1.0, True),  # lifetime usufruct: someone has the right to live there
    ("municipal_rights", r"önkormányzati\s+(bérlakás|tulajdon)|bérleti\s+jog|bérlőkijelölési", 1.0, True),
    ("auction", r"árverés|végrehajt|licit", 1.0, True),
    ("co_ownership", r"osztatlan\s+közös|résztulajdon|tulajdoni\s+hányad\s+eladó", 1.0, True),
    ("tenant_inside", r"bérlővel\s+együtt|bérlővel\s+terhelt|jelenleg\s+bérbe\s+van\s+adva", 0.97, False),
    ("not_registered", r"nincs\s+(feltüntetve|bejegyezve)|engedély\s+nélkül|fennmaradási", 1.0, True),
    ("loft_unbuilt", r"tetőtér\s+beépítés|beépíthető\s+tetőtér", 1.0, False),
    ("needs_structural", r"födém|statikai|vizesedik|nedves\s+fal|salakos", 0.97, False),
    ("ground_floor_text", r"\bföldszinti\b", 0.95, False),
    ("semi_basement_text", r"félszuterén|szuterén", 0.85, False),
    ("street_noise", r"forgalmas\s+út|villamos\s+(zaj|mellett)", 0.98, False),
    ("panel_program", r"panelprogram", 1.02, False),
    ("unencumbered", r"tehermentes", 1.0, False),
]


def assess_listing(
    description: Optional[str],
    floor: Optional[str],
    has_elevator: Optional[bool],
    building_type: Optional[str] = None,
) -> List[Flag]:
    text = (description or "").lower()
    flags: List[Flag] = []
    floor_no = _floor_number(floor)

    if floor_no == -1:
        flags.append(Flag("basement", 0.80))
    elif floor_no == 0:
        flags.append(Flag("ground_floor", 0.95))
    elif floor_no is not None and floor_no >= 3 and has_elevator is False:
        flags.append(Flag("no_elevator_high_floor", 0.93))
    elif floor_no is not None and floor_no >= 2 and has_elevator is True:
        flags.append(Flag("upper_floor_elevator", 1.0, positive=True))

    have = {f.code for f in flags}
    for code, pattern, factor, blocker in _TEXT_CHECKS:
        if not re.search(pattern, text):
            continue
        # Text mentions of the floor only count when the floor field is empty.
        if code == "ground_floor_text" and floor_no is not None:
            continue
        if code == "semi_basement_text" and ("basement" in have or floor_no is not None):
            continue
        positive = code in ("panel_program", "unencumbered")
        flags.append(Flag(code, factor, blocker, positive))
    return flags


def exit_factor(flags: List[Flag]) -> float:
    factor = 1.0
    for f in flags:
        factor *= f.exit_factor
    return factor
