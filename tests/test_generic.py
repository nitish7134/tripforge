import datetime as dt

from tripforge import ground
from tripforge.events import full_moons


def _fake(route_data=None, fare_ok=False):
    from tripforge.fetchers.common import Result, fail
    ground.route = lambda a, b: Result(ok=True, data=route_data)
    ground.fare = lambda a, b, c: (Result(ok=True, data={"from": 40, "currency": c}, source_url="u") if fare_ok
                                   else fail("none", "https://12go.asia/en/travel/x/y"))
    ground.rail_note = lambda n: None


def test_ground_road_from_routing_and_fare_unavailable():
    _fake({"duration_h": 3.0, "distance_km": 300.0, "snap_m": [20, 30]})
    a = {"name": "Lisbon", "lat": 38.72, "lon": -9.14}
    b = {"name": "Porto", "lat": 41.15, "lon": -8.61}
    g = ground.estimate(a, b, "EUR")
    assert g["mode"] == "road" and g["source"] == "osrm" and g["amount"] is None  # no invented money
    assert 2.5 < g["hours"][0] < g["hours"][1] and ground.needs_ground(a, b)


def test_ground_no_road_route_is_ferry():
    _fake({"no_route": True})
    g = ground.estimate({"name": "Isla Mujeres", "lat": 21.23, "lon": -86.73},
                        {"name": "Tulum", "lat": 20.21, "lon": -87.46}, "USD")
    assert g["mode"] == "ferry" and "no road route" in g["source"] and g["amount"] is None


def test_ground_far_snap_is_ferry():
    _fake({"duration_h": 5.0, "distance_km": 270.0, "snap_m": [9000, 40]})
    g = ground.estimate({"name": "A", "lat": 9.73, "lon": 100.03}, {"name": "B", "lat": 8.09, "lon": 98.91}, "USD")
    assert g["mode"] == "ferry"


def test_ground_fare_only_from_live_read():
    _fake({"duration_h": 2.0, "distance_km": 150.0, "snap_m": [1, 1]}, fare_ok=True)
    g = ground.estimate({"name": "A", "lat": 1.0, "lon": 1.0}, {"name": "B", "lat": 1.5, "lon": 1.5}, "EUR")
    assert g["amount"] == [40, 40] and g["currency"] == "EUR"


def test_full_moon_dec_2026():
    # Astronomical full moon 24 Dec 2026 (+/- 1 day tolerance in the product).
    d = full_moons(dt.date(2026, 12, 15), dt.date(2027, 1, 5))
    assert len(d) == 1 and abs((d[0] - dt.date(2026, 12, 24)).days) <= 1
