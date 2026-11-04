"""Hostelworld parsing and the City/Area stay pin, all offline."""
import json
from pathlib import Path

import pytest

from tripforge.fetchers import hostels as HW
from tripforge.fetchers.geo import PIN_DEG, stay_bbox
from tripforge.stops import StopError, split_spec

FIX = Path(__file__).parent / "fixtures"


def test_parse_rooms_sorts_by_price_and_drops_sold_out():
    av = json.loads((FIX / "hostelworld_availability.json").read_text())
    r = HW.parse_rooms(av)
    assert [d["room"] for d in r["dorms"]] == ["Standard 8 Bed Mixed Dorm Ensuite", "Deluxe 4 Bed Mixed Dorm Ensuite"]
    assert r["dorms"][0] == {"room": "Standard 8 Bed Mixed Dorm Ensuite", "per_night": 2806, "total": 5612,
                             "available": 75, "ensuite": True}
    assert r["privates"][0]["per_night"] == 23660 and r["privates"][0]["available"] == 3


def test_parse_property_scales_rating_to_ten():
    d = HW.parse_property({"id": "322541", "name": "Some Hostel", "rating": {"overall": 98}, "totalRatings": "2388",
                           "type": "HOSTEL", "checkIn": {"startsAt": "14"}})
    assert d["name"] == "Some Hostel" and d["rating"] == 9.8 and d["reviews"] == 2388


def test_pick_orders_by_cheapest_dorm():
    from tripforge.fetchers.common import Result
    a = Result(ok=True, data={"name": "A", "dorms": [{"per_night": 3000}], "privates": []})
    b = Result(ok=True, data={"name": "B", "dorms": [{"per_night": 2500}], "privates": []})
    c = Result(ok=False, data=None)
    assert [d["name"] for d in HW.pick([a, c, b])] == ["B", "A"]


@pytest.mark.parametrize("spec,want", [
    ("CityA:4,City B:2@XYZ", [("CityA", None, 4, None), ("City B", None, 2, "XYZ")]),
    ("Town/Beach Road:2", [("Town", "Beach Road", 2, None)]),
    ("Big City / Old Quarter : 3 @ ABC", [("Big City", "Old Quarter", 3, "ABC")]),
    ("Solo", [("Solo", None, 2, None)]),
])
def test_split_spec_reads_area_nights_iata(spec, want):
    got = [(s["name"], s["area"], s["nights"], s["iata"]) for s in split_spec(spec)]
    assert got == [tuple(w) for w in want]


def test_split_spec_rejects_garbage():
    with pytest.raises(StopError):
        split_spec("City:x:y")


def test_pinned_area_uses_walking_radius():
    ne_lat, ne_lon, sw_lat, sw_lon = stay_bbox("X", "Y", None, 0, 0, center=[10.0, 20.0], radius_deg=PIN_DEG)
    assert ne_lat - sw_lat == pytest.approx(2 * PIN_DEG) and ne_lon - sw_lon == pytest.approx(2 * PIN_DEG)
    ne_lat2, _, sw_lat2, _ = stay_bbox("X", "Y", None, 0, 0, center=[10.0, 20.0])
    assert ne_lat2 - sw_lat2 > 2 * PIN_DEG  # the default city box is wider than a pinned one


def test_geocode_point_skips_admin_polygons_and_retries_with_feature_suffix(monkeypatch):
    """A name that only matches an administrative boundary is re-asked as '<name> beach' etc. and the first point wins."""
    from tripforge.fetchers import geo

    calls = []

    class FakeResp:
        def __init__(self, js):
            self._js = js

        def json(self):
            return self._js

    class FakeClient:
        def __init__(self, *_a, **_k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, _url, params):
            calls.append(params["q"])
            if params["q"].startswith("Somewhere beach"):
                return FakeResp([{"lat": "8.03", "lon": "98.82", "boundingbox": ["8", "8.1", "98.8", "98.9"],
                                  "class": "natural", "type": "beach", "name": "Somewhere Beach", "address": {"country_code": "th"}}])
            return FakeResp([{"lat": "7.72", "lon": "98.76", "boundingbox": ["7", "8", "98", "99"],
                              "class": "boundary", "type": "administrative", "name": "Somewhere", "address": {"country_code": "th"}}])

    monkeypatch.setattr(geo, "client", FakeClient)
    monkeypatch.setattr(geo, "_polite", lambda: None)
    monkeypatch.setattr(geo.cache, "cached", lambda _n, _p, fn: fn())
    r = geo.geocode_point("Somewhere, City, Country")
    assert r.ok and r.data["point"] and r.data["type"] == "beach" and r.data["lat"] == 8.03
    assert calls[:2] == ["Somewhere, City, Country", "Somewhere beach, City, Country"]
