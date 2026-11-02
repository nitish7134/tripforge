import datetime as dt

from tripforge import ground
from tripforge.events import full_moons


def test_ground_table_beats_heuristic():
    a = {"name": "Koh Phangan", "lat": 9.73, "lon": 100.03}
    b = {"name": "Krabi", "lat": 8.09, "lon": 98.91}
    g = ground.estimate(a, b)
    assert g["source"] == "table" and g["inr"] == [1800, 3000]


def test_ground_heuristic_any_destination():
    a = {"name": "Lisbon", "lat": 38.72, "lon": -9.14}
    b = {"name": "Porto", "lat": 41.15, "lon": -8.61}
    g = ground.estimate(a, b)
    assert g["source"] == "heuristic" and g["mode"] == "road or rail"
    assert 250 < g["km"] < 400 and g["inr"][0] < g["inr"][1]
    assert ground.needs_ground(a, b)


def test_island_gets_ferry():
    g = ground.estimate({"name": "Isla Mujeres", "lat": 21.23, "lon": -86.73},
                        {"name": "Tulum", "lat": 20.21, "lon": -87.46})
    assert "ferry" in g["mode"]


def test_full_moon_dec_2026():
    # Astronomical full moon 24 Dec 2026 (+/- 1 day tolerance in the product).
    d = full_moons(dt.date(2026, 12, 15), dt.date(2027, 1, 5))
    assert len(d) == 1 and abs((d[0] - dt.date(2026, 12, 24)).days) <= 1
