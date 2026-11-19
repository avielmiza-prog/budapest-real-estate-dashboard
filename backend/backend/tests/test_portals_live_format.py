"""Parsers against markup/JSON captured from the live sites on 2026-11-18."""
from pathlib import Path

from scraper.normalize import infer_condition_from_text, normalize_listing
from scraper.portals import jofogas, otthonterkep

FIXTURES = Path(__file__).parent / "fixtures"


def test_otthonterkep_search_card():
    raws = otthonterkep.parse_search_cards((FIXTURES / "otthonterkep_search_card.html").read_text(encoding="utf-8"))
    assert len(raws) == 1
    n = normalize_listing(raws[0], "otthonterkep")
    assert n["district"] == "VIII"
    assert n["price_huf"] == 26_990_000
    assert n["size_sqm"] == 24
    assert round(n["price_per_sqm"]) == 1_124_583  # same figure the card itself shows
    assert n["floor"] == "szuterén"
    assert n["images"] and n["images"][0].startswith("https://images2.ingatlantajolo.hu/")


def test_jofogas_ad_current_shape():
    ad = {
        "url": "https://ingatlan.jofogas.hu/budapest/Elado_lakas__Budapest_3__ker__162821553.htm",
        "subject": "Eladó lakás, Budapest 3. ker.",
        "body": "Panorámás lakás.<br><br>Tehermentes.",
        "price": {"label": "65 000 000 Ft", "value": 65000000},
        "images": [{"name": "Elado_lakas__Budapest_3__ker__821162883532959.jpg"}],
        "parameters": [
            {"key": "zipcode", "values": [{"value": "1037", "label": "III. kerület"}]},
            {"key": "rooms", "values": [{"value": "2", "label": "2 szoba"}]},
            {"key": "realestate_condition", "values": [{"value": "7", "label": "Felújítandó"}]},
            {"key": "floor", "values": [{"value": "1", "label": "földszint"}]},
            {"key": "elevator", "values": [{"value": "2", "label": "Nincs"}]},
            {"key": "building_type", "values": [{"value": "2", "label": "panel"}]},
            {"key": "size", "values": [{"value": "54", "label": "54 m²"}]},
        ],
        "category_tree": [{"id": "1000", "name": "Ingatlan"}, {"id": "1020", "name": "Lakás"}],
        "type": {"label": "Eladó", "value": "s"},
    }
    assert jofogas._is_residential(ad)
    raw = jofogas.ad_to_raw_listing(ad)
    n = normalize_listing(raw, "jofogas")
    assert n["images"] == ["https://img.jofogas.hu/767x575crop/Elado_lakas__Budapest_3__ker__821162883532959.jpg"]
    assert n["floor"] == "földszint" and n["has_elevator"] is False
    assert n["building_type"] == "Panel Block (Panelház)"
    assert n["condition"] == "Felújítandó"
    assert "<br>" not in n["description"]
    rental = dict(ad, type={"label": "Kiadó", "value": "u"})
    assert not jofogas._is_residential(rental)


def test_condition_from_description_is_conservative():
    assert infer_condition_from_text("Frissen felújított 2 szobás") == "Felújított"
    assert infer_condition_from_text("felújításra szorul") == "Felújítandó"
    assert infer_condition_from_text("felújított fürdőszobával") == ""
