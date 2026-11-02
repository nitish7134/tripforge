"""Domestic / rail-friendly trips: destination normalisation, rail parsing and limits, one-stop rows, guests,
pace-aware day plan, nightlife gating, events parsing, domestic holidays. All offline."""
import datetime as dt
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from tripforge import events, plan
from tripforge.fetchers import destination, places, rail
from tripforge.fetchers import flights_fli as FL
from tripforge.fetchers import stays_pyairbnb as SP
from tripforge.fetchers.common import Result, fail

FIX = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------- 1. destination normalisation
@pytest.fixture
def wv(monkeypatch):
    """A fake Wikivoyage with the given page titles; nothing else is reachable."""
    def make(pages, opensearch=(), geo_name=None, searched=()):
        monkeypatch.setattr(destination.cache, "cached", lambda _n, _p, fn: fn())
        monkeypatch.setattr(destination, "_exists", lambda t: t if t in pages else None)
        monkeypatch.setattr(destination, "_opensearch", lambda q: list(opensearch))
        monkeypatch.setattr(destination, "_search", lambda q: list(searched))
        monkeypatch.setattr(destination, "geocode", lambda q: Result(ok=bool(geo_name), data={"name": geo_name},
                                                                     error=None if geo_name else "none"))
    return make


@pytest.mark.parametrize("text,page", [("Rajasthan, India", "Rajasthan"), ("Rajasthan", "Rajasthan"),
                                       ("Kerala", "Kerala"), ("Andalusia, Spain", "Andalusia")])
def test_destination_strips_trailing_country(wv, text, page):
    wv({page})
    r = destination.resolve(text)
    assert r.ok and r.data["title"] == page


def test_destination_falls_back_to_opensearch_then_nominatim(wv):
    wv({"Nowhere Region"}, opensearch=["Nowhere Region"])
    assert destination.resolve("Nowhere, Land").data["title"] == "Nowhere Region"
    wv({"Real Name"}, geo_name="Real Name")
    assert destination.resolve("Odd Spelling, Land").data["title"] == "Real Name"


def test_destination_failure_lists_every_attempt(wv):
    wv(set(), geo_name="Zed")
    r = destination.resolve("Zed, Land")
    assert not r.ok and "no article found for 'Zed, Land'" in r.error and "tried" in r.error and "Zed" in r.error


def test_missing_wikivoyage_page_is_a_clear_failure_not_a_keyerror(monkeypatch):
    monkeypatch.setattr(places.cache, "cached", lambda _n, _p, fn: fn())
    monkeypatch.setattr(places.httpx, "get", lambda *a, **k: NS(json=lambda: {"error": {"code": "missingtitle"}}))
    r = places.wikivoyage("Nope")
    assert not r.ok and "no Wikivoyage article" in r.error


# ---------------------------------------------------------------- destinations(): multi-line markers
def test_destinations_reads_multiline_markers_and_entities():
    text = """== Cities ==
{{Regionlist
|regionmap=x.png
}}
* {{marker|type=city|name=[[Alpha]]
|lat=1|long=2|wikidata=Q1}} &ndash; the &quot;big&quot; one
[[File:Pic.jpg|thumb|caption with [[Link]]]]
* [[Beta]] &mdash; small
== Other destinations ==
* {{marker|type=city
|name=[[Gamma|Gamma Town]]|lat=3}} a park
== Understand =="""
    ds = places.destinations(text)
    assert [(d["page"], d["kind"]) for d in ds] == [("Alpha", "city"), ("Beta", "city"), ("Gamma", "destination")]
    assert "File" not in str(ds) and "&quot;" not in str(ds)


# ---------------------------------------------------------------- 2. rail
def test_parse_erail_fixture():
    rows = rail.parse_erail((FIX / "erail_pair.txt").read_text())
    assert [r["train"] for r in rows] == ["74844", "15014"]
    r = rows[1]
    assert (r["dep"], r["arr"], r["duration_min"]) == ("17:00", "23:30", 390)
    assert r["classes"] == ["1A", "2A", "2S", "3A", "SL"] and r["fare"] is None  # a fare is never guessed


def test_night_and_limits():
    assert rail.is_night(23 * 60, 120) and rail.is_night(20 * 60, 600) and not rail.is_night(9 * 60, 300)
    rows = [{"train": "a", "dep_min": 9 * 60, "duration_min": 5 * 60}, {"train": "b", "dep_min": 20 * 60, "duration_min": 9 * 60},
            {"train": "c", "dep_min": 8 * 60, "duration_min": 20 * 60}]
    assert [r["train"] for r in rail.filter_rows(rows, 18, True)] == ["a", "b"]
    assert [r["train"] for r in rail.filter_rows(rows, 18, False)] == ["a"]  # no night travel
    assert [r["train"] for r in rail.filter_rows(rows, None, True)] == ["a", "b", "c"]


def test_quote_uses_country_adapter_and_never_invents(monkeypatch):
    rows = rail.parse_erail((FIX / "erail_pair.txt").read_text())
    monkeypatch.setitem(rail.ADAPTERS, "IN", lambda a, b, d: Result(ok=True, data=rows, source_url="u"))
    q = rail.quote("A", "B", "IN", "2027-01-01")
    assert q["ok"] and q["rows"][0]["fare"] is None and q["adapter"]
    q = rail.quote("A", "B", "ZZ", "2027-01-01")  # no adapter for this country
    assert not q["ok"] and "no rail-quote adapter" in q["error"]
    monkeypatch.setitem(rail.ADAPTERS, "IN", lambda a, b, d: fail("blocked", "https://x/y"))
    q = rail.quote("A", "B", "IN", "2027-01-01")
    assert not q["ok"] and q["url"] == "https://x/y" and q["rows"] == []


def test_by_train_note_quotes_the_guide_section(monkeypatch):
    txt = "== Get in ==\n=== By train ===\n[[File:a.jpg|thumb|x]]The [[Main Station|main station]] has daily trains. Takes 5 hours.\n=== By bus ===\nbuses"
    monkeypatch.setattr(rail, "wikivoyage", lambda n: Result(ok=True, data={"text": txt}, source_url="http://w"))
    n = rail.by_train_note("X")
    assert "main station has daily trains" in n["text"] and "buses" not in n["text"] and "thumb" not in n["text"]


# ---------------------------------------------------------------- 3. one-stop flights
def _leg(code, no, dep, arr, a, b):
    return NS(airline=NS(name=code, value=code), flight_number=no, departure_datetime=dep, arrival_datetime=arr,
              departure_airport=NS(name=a), arrival_airport=NS(name=b), aircraft="")


def test_one_stop_rows_respect_total_time_and_price():
    d = dt.datetime(2027, 1, 10, 8, 0)
    ok = NS(legs=[_leg("AA", 1, d, d + dt.timedelta(hours=2), "NAG", "DEL"),
                  _leg("BB", 2, d + dt.timedelta(hours=4), d + dt.timedelta(hours=6), "DEL", "JAI")],
            price=7000.0, currency="INR", duration=360, stops=1)
    slow = NS(legs=ok.legs, price=5000.0, currency="INR", duration=900, stops=1)
    nonstop = NS(legs=ok.legs[:1], price=9000.0, currency="INR", duration=120, stops=0)
    rows = FL.to_rows_connecting([slow, ok, nonstop], "NAG", "JAI", "INR", 12 * 60)
    assert len(rows) == 1 and rows[0]["via"] == "DEL" and rows[0]["flight"] == "AA 1 + BB 2" and rows[0]["price"] == 7000


# ---------------------------------------------------------------- 4. groups of 3+
def test_stay_cards_too_small_for_the_party_are_dropped():
    def card(rid, beds):
        return {"room_id": rid, "name": f"n{rid}", "title": "Home in X", "badges": [], "rating": {"value": 4.9, "reviewCount": 50},
                "price": {"unit": {"amount": 1000, "qualifier": "for 2 nights"}}, "structuredContent": {"p": f"{beds}"}}
    raw = [card(1, "1 bed"), card(2, "2 beds"), card(3, "3 beds"), {**card(4, ""), "structuredContent": {}}]
    got = SP.to_rows(raw, 2, "2027-01-10", "2027-01-12", 3, "INR")
    assert sorted(int(r["url"].split("/rooms/")[1].split("?")[0]) for r in got) == [2, 3, 4]  # 1 bed cannot sleep 3
    assert "adults=3" in got[0]["url"]


def test_templates_have_no_pair_language():
    src = Path(plan.__file__).parent
    text = (src / "templates" / "plan.html.j2").read_text().lower()
    assert "sharing" not in text and "two friends" not in text and "nonstop flights only" not in text


# ---------------------------------------------------------------- 5. pace + nightlife
def test_nightlife_only_when_asked():
    assert not plan.wants_nightlife(["culture", "veg"], {"party_rate": 0})
    assert not plan.wants_nightlife(["culture"], {})
    assert plan.wants_nightlife(["party"], {}) and plan.wants_nightlife(["nightlife"], {})
    assert plan.wants_nightlife([], {"party_rate": 500})


def _opt():
    stop = {"name": "S", "checkin": "2027-01-10", "checkout": "2027-01-14", "nights": 4,
            "highlights": ["h1", "h2", "h3", "h4", "h5"]}
    legs = [{"kind": "rail", "to_idx": 0, "used": True, "rows": [{"train": "1", "name": "Exp", "arr": "06:10", "dep": "11:15",
                                                                    "next_day": True, "early": False}]},
            {"kind": "rail", "to_idx": None, "used": True, "rows": [{"train": "2", "name": "Back", "arr": "10:00", "dep": "09:00",
                                                                       "next_day": False}]}]
    return {"stops": [stop], "legs": legs, "end": "2027-01-14"}


def test_relaxed_pace_caps_sights_and_hides_nightlife():
    places_ = {"S": {"sights": [], "nightlife": [{"name": "Loud Bar"}], "diet": {}}}
    days = plan.build_days(_opt(), places_, ["culture"], "relaxed", False)
    assert all(d["text"].count(";") + 1 <= 2 for d in days[:-1]) and "Loud Bar" not in str(days)
    assert days[0]["text"].startswith("Arrive 06:10 next day by train 1")
    assert days[-1]["text"].startswith("Train home 2")
    packed = plan.build_days(_opt(), places_, ["culture"], "packed", False)
    assert max(d["text"].count(";") for d in packed[:-1]) > max(d["text"].count(";") for d in days[:-1])


def test_rail_leg_prefers_civilised_departures_when_relaxed():
    q = {"ok": True, "rows": [{"train": "early", "dep_min": 5 * 60, "duration_min": 300},
                             {"train": "late", "dep_min": 10 * 60, "duration_min": 400}], "url": "u", "adapter": "erail"}
    h = {"date": "2027-01-10", "to_idx": 0}
    assert plan.rail_leg(h, "A", "B", q, None, "relaxed")["rows"][0]["train"] == "late"
    assert plan.rail_leg(h, "A", "B", {**q, "rows": list(q["rows"])}, None, "balanced")["rows"][0]["train"] == "early"


# ---------------------------------------------------------------- 6. events
def test_glued_wikipedia_snippet_becomes_separate_events():
    snip = "Camel Festival, Bikaner (January) Nagaur Fair, Nagaur (January\u2013February) Gangaur Festival, Jaipur (March) "
    rows = events.split_snippet(snip, "wikipedia", "u")
    assert [r["text"] for r in rows] == ["Camel Festival in Bikaner (January)", "Nagaur Fair in Nagaur (January\u2013February)",
                                         "Gangaur Festival in Jaipur (March)"]
    s, e = dt.date(2027, 1, 10), dt.date(2027, 1, 18)
    assert [r["text"].split(" in ")[0] for r in rows if events.in_window(r["when"], s, e)] == ["Camel Festival", "Nagaur Fair"]


def test_section_mentions_read_events_section_only():
    txt = ("== Understand ==\n* A January note outside the section\n== Festivals and events ==\n"
           "* '''Kite Day''' on 14 January, all over town\n* Monsoon Fair in July\n== Get in ==\n* January train")
    r = events.section_mentions(txt, dt.date(2027, 1, 10), dt.date(2027, 1, 18), "wv", "u")
    assert [x["text"] for x in r] == ["Kite Day on 14 January, all over town"]


# ---------------------------------------------------------------- 7. domestic holidays
def test_domestic_holiday_row_covers_leave_and_closures():
    res = Result(ok=True, data=[{"date": "2027-01-26", "name": "Republic Day", "local": ""}], source_url="u")
    both = events.holiday_rows(res, "X", "both")[0]["text"]
    assert "plan leave days" in both and "closures and crowds" in both
