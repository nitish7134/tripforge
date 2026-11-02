from pathlib import Path

import tripforge.fetchers.visa as V
from tripforge.plan import visa_targets
from tripforge.render import build_env

FX = Path(__file__).parent / "fixtures"
IN = (FX / "visa_wikitext_indian.txt").read_text()
PT = (FX / "visa_wikitext_portuguese.txt").read_text()


def test_indian_thailand_visa_free_30_days():
    r = V.find_row(IN, {"thailand"}, "TH")
    assert V.normalise_status(r["status_raw"]) == "visa not required"
    assert r["stay"] == "30 days"
    assert "TDAC" in r["notes"] and "<ref" not in r["notes"] and "{{" not in r["notes"]


def test_indian_vietnam_evisa():
    r = V.find_row(IN, {"vietnam"}, "VN")
    assert V.normalise_status(r["status_raw"]) == "eVisa"
    assert "90 days" in r["notes"]


def test_indian_portugal_visa_required():
    r = V.find_row(IN, {"portugal"}, "PT")
    assert V.normalise_status(r["status_raw"]) == "visa required"


def test_portuguese_passport_not_india_specific():
    r = V.find_row(PT, {"brazil"}, "BR")
    assert V.normalise_status(r["status_raw"]) == "visa not required" and r["stay"] == "90 days"
    n = V.find_row(PT, {"namibia"}, "NA")
    assert V.normalise_status(n["status_raw"]) == "eVisa"


def test_unknown_destination_is_none():
    assert V.find_row(IN, {"atlantis"}, "XX") is None


def test_domestic_has_no_visa_targets_or_section():
    assert visa_targets("IN", "IN", ["IN"]) == []          # BLR -> Goa
    assert V.visa_requirement("IN", "IN").ok is False       # never hits the network
    assert visa_targets("IN", "IN", ["IN", "TH"]) == ["TH"]  # mixed trip: only the foreign stop
    html = build_env().from_string(
        "{% if plan.visa %}VISA-SECTION{% endif %}").render(plan={"visa": {}})
    assert "VISA-SECTION" not in html
