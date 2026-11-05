"""Menu money comes only from live reads: hops, return legs and stays are fetched or 'unavailable'
(docs/FETCH_STRATEGY.md rule 2). All offline: fli, OSRM/12Go and the cache are stubbed."""
import datetime as dt
import re
from pathlib import Path

import pytest

from tripforge import menu
from tripforge.fetchers.common import Result, fail

SRC = Path(__file__).resolve().parents[1] / "src" / "tripforge" / "menu.py"
START = dt.date(2027, 1, 10)


def _stop(name, iata, nights, stay_pn=100, flight=500):
    return {"name": name, "iata": iata, "nights": nights, "stay_pn": stay_pn, "lat": 0.0, "lon": 0.0,
            "flight": {"price": flight} if flight is not None else None}


@pytest.fixture
def offline(monkeypatch):
    """No cache, every hop is an air hop, ground never reached; fli answers from `answers`."""
    calls = []
    monkeypatch.setattr(menu.cache, "cached", lambda _n, _p, fn: fn())
    monkeypatch.setattr(menu.ground, "needs_ground", lambda a, b: False)
    monkeypatch.setattr(menu.ground, "estimate", lambda *a: pytest.fail("ground.estimate on an air hop"))

    def install(answers):
        def leg(o, d, date, ccy, cc):
            calls.append((o, d, date))
            p = answers.get((o, d, date))
            return Result(ok=True, data=[{"price": p}]) if p is not None else fail("no nonstop flights")
        monkeypatch.setattr(menu.FL, "fetch_leg", leg)
        return calls
    return install


def _fares(order, answers):
    hops, back = menu._legs(order, "HOM", START)
    return {k: menu._leg_price(*k, "EUR", "XX") for k in (*hops, back)}


def test_hop_and_return_are_fetched_on_their_own_dates(offline):
    order = [_stop("A", "AAA", 2), _stop("B", "BBB", 3)]
    answers = {("AAA", "BBB", "2027-01-12"): 80, ("BBB", "HOM", "2027-01-15"): 420}
    calls = offline(answers)
    cost = menu._route_cost(order, "HOM", 2, "EUR", START, _fares(order, answers))
    assert set(calls) == set(answers)
    # flights = outbound 500 + live return 420 (not a copy of the outbound); hops = live 80
    assert cost["flights_pp"] == 920 and cost["ground_pp"] == 80
    assert cost["core_pp"] == 920 + 80 + (100 * 2 + 100 * 3) / 2 and cost["tag"] == "live"


def test_failed_hop_fetch_is_unavailable_not_a_fraction_of_the_long_haul(offline):
    order = [_stop("A", "AAA", 2, flight=900), _stop("B", "BBB", 3, flight=600)]
    answers = {("BBB", "HOM", "2027-01-15"): 420}
    offline(answers)
    cost = menu._route_cost(order, "HOM", 2, "EUR", START, _fares(order, answers))
    assert cost["ground_pp"] is None and cost["core_pp"] is None
    assert "hops unavailable" in cost["tag"]


def test_failed_return_fetch_is_unavailable_not_the_outbound(offline):
    order = [_stop("A", "AAA", 2), _stop("B", "BBB", 3)]
    answers = {("AAA", "BBB", "2027-01-12"): 80}
    offline(answers)
    cost = menu._route_cost(order, "HOM", 2, "EUR", START, _fares(order, answers))
    assert cost["flights_pp"] is None and cost["core_pp"] is None and "flights unavailable" in cost["tag"]


def test_missing_stay_never_enters_core(offline):
    order = [_stop("A", "AAA", 2), _stop("B", "BBB", 3, stay_pn=None)]
    answers = {("AAA", "BBB", "2027-01-12"): 80, ("BBB", "HOM", "2027-01-15"): 420}
    offline(answers)
    cost = menu._route_cost(order, "HOM", 2, "EUR", START, _fares(order, answers))
    assert cost["stays_pp"] is None and cost["core_pp"] is None and "stays unavailable" in cost["tag"]


def test_ground_hop_without_a_live_fare_is_unavailable(monkeypatch):
    monkeypatch.setattr(menu.ground, "needs_ground", lambda a, b: True)
    monkeypatch.setattr(menu.ground, "estimate", lambda *a: {"amount": None})
    order = [_stop("A", "AAA", 2), _stop("B", "BBB", 3)]
    cost = menu._route_cost(order, "HOM", 2, "EUR", START, {("BBB", "HOM", "2027-01-15"): 420})
    assert cost["ground_pp"] is None and cost["core_pp"] is None


def test_unavailable_renders_as_unavailable():
    cost = {"core_pp": None, "flights_pp": None, "ground_pp": 80, "stays_pp": 250, "tag": "partial: flights unavailable"}
    d = {"currency": "EUR", "rates": {"meal_rate": None, "party_rate": None}, "destination": "X",
         "window": {"start": "a", "end": "b"}, "prefs": [], "source": "u", "events": [], "spend_pp_est": None,
         "candidates": [dict(_stop("A", "AAA", 2, stay_pn=None, flight=None), kind="city", fit_score=0, blurb="", fit={},
                             access=None, musts=[], worth="w", skip="s", events=[], url="u", stay_tag="unavailable")],
         "combos": [{"stops": ["A"], "nights": [2], "why": "w", "cost": cost, "stops_spec": "A:2"}]}
    md = menu._md(d, "HOM")
    assert "Stay: unavailable" in md and "core unavailable/person = flights unavailable" in md


def test_no_heuristic_money_in_menu_source():
    src = SRC.read_text()
    assert "statistics" not in src and "median" not in src
    assert not re.search(r"/\s*3\b", src), "a hop priced as a fraction of another fare is back"
