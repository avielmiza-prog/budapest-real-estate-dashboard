"""Name -> scraper class, so run.py (and anything else) can look portals up by string."""
from scraper.portals.ingatlanbazar import IngatlanbazarScraper
from scraper.portals.jofogas import JofogasScraper
from scraper.portals.otthonterkep import OtthonterkepScraper

PORTALS = {
    "ingatlanbazar": IngatlanbazarScraper,
    "jofogas": JofogasScraper,
    "otthonterkep": OtthonterkepScraper,
}


def get_scraper(portal_name: str):
    try:
        return PORTALS[portal_name]()
    except KeyError:
        valid = ", ".join(PORTALS)
        raise ValueError(f"Unknown portal {portal_name!r}. Valid options: {valid}")
