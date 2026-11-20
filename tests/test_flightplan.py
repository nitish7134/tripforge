"""Flight plan: per-person legs, rule checks, best pick, deploy gate, and the rendered section."""
import json, pathlib, shutil
from tripforge.site import build, check
from tripforge.site.flightplan import evaluate, problems

EX = pathlib.Path(__file__).resolve().parents[1] / "trips" / "example-vela-islands"


def leg(role, dep, arr, price=1000, who="A", dir="Out"):
    return {"role": role, "who": who, "dir": dir, "flight": "XX 1", "from": "AAA", "to": "BBB", "dep": dep, "arr": arr, "price": price}


RULES = [
    {"type": "not_earlier", "leg": "b", "than": "a", "label": "B not before A"},
    {"type": "within", "legs": ["a", "b"], "minutes": 30, "soft": True, "label": "Land together"},
    {"type": "arrive_before", "leg": "r", "time": "19:00", "label": "Return before 19:00"},
    {"type": "arrive_on", "leg": "r", "date": "2026-11-24", "label": "Same day"},
]


def opt(id, a_arr, b_arr, r_arr="2026-11-24T14:40+05:30", price=1000):
    return {"id": id, "label": id, "legs": [leg("a", "2026-11-21T12:00+05:30", a_arr), leg("b", "2026-11-21T13:00+05:30", b_arr),
                                           leg("r", "2026-11-24T12:00+07:00", r_arr, price)]}


def test_rules_pass_and_fail():
    p = evaluate({"rules": RULES, "options": [
        opt("ok", "2026-11-21T18:10+07:00", "2026-11-21T18:30+07:00"),
        opt("early", "2026-11-21T19:00+07:00", "2026-11-21T18:30+07:00"),
        opt("late", "2026-11-21T18:10+07:00", "2026-11-21T18:30+07:00", "2026-11-24T19:10+05:30"),
        opt("nextday", "2026-11-21T18:10+07:00", "2026-11-21T18:30+07:00", "2026-11-25T00:20+05:30")]})
    by = {o["id"]: o for o in p["options"]}
    assert by["ok"]["ok"] and by["ok"]["fails"] == 0 and by["ok"]["warns"] == 0
    assert by["early"]["fails"] == 1 and "BEFORE" in by["early"]["results"][0]["detail"]
    assert by["late"]["fails"] == 1
    assert by["nextday"]["fails"] == 2          # 00:20 next day is neither before 19:00 same day nor on the 24th
    assert p["best"] == "ok"


def test_soft_rule_warns_but_does_not_fail():
    p = evaluate({"rules": RULES, "options": [opt("far", "2026-11-21T18:10+07:00", "2026-11-21T19:40+07:00")]})
    o = p["options"][0]
    assert o["ok"] and o["warns"] == 1 and o["results"][1]["detail"] == "1h 30m apart"


def test_timezones_compare_as_instants():
    # 18:30 at +07:00 is 17:00 at +05:30, so B (17:30 IST) is after A (18:30+07:00 = 17:00 IST)
    p = evaluate({"rules": RULES[:1], "options": [opt("tz", "2026-11-21T18:30+07:00", "2026-11-21T17:30+05:30")]})
    assert p["options"][0]["ok"]


def test_rule_with_missing_role_is_skipped_and_unknown_type_raises():
    p = evaluate({"rules": [{"type": "not_earlier", "leg": "zz", "than": "a"}], "options": [opt("x", "2026-11-21T18:10+07:00", "2026-11-21T18:30+07:00")]})
    assert p["options"][0]["results"] == []
    import pytest
    with pytest.raises(ValueError):
        evaluate({"rules": [{"type": "nope", "leg": "a"}], "options": [opt("x", "2026-11-21T18:10+07:00", "2026-11-21T18:30+07:00")]})


def test_gate_only_blocks_recommended_options():
    bad = opt("early", "2026-11-21T19:00+07:00", "2026-11-21T18:30+07:00")
    assert problems({"rules": RULES, "options": [bad]}) == []
    bad["recommended"] = True
    assert len(problems({"rules": RULES, "options": [bad]})) == 1


def _trip_with_section(tmp_path, options):
    dst = tmp_path / "t"; shutil.copytree(EX, dst); shutil.rmtree(dst / "site" / "dist", ignore_errors=True)
    cfg = json.loads((dst / "site" / "trip.json").read_text())
    cfg["data"]["sections"] = [{"id": "flights", "title": "Flights", "kind": "flightPlan", "src": "flights.json"}]
    (dst / "site" / "trip.json").write_text(json.dumps(cfg))
    (dst / "flights.json").write_text(json.dumps({"rules": RULES, "options": options}))
    return dst


def test_sync_writes_evaluated_section_and_gate_blocks_recommended(tmp_path):
    from tripforge.site.sections import sync
    dst = _trip_with_section(tmp_path, [opt("early", "2026-11-21T19:00+07:00", "2026-11-21T18:30+07:00")])
    assert [r["state"] for r in sync(dst)] == ["updated"]
    assert [r["state"] for r in sync(dst)] == ["unchanged"]
    out = json.loads((dst / "site" / "data" / "flights.json").read_text())
    assert out["best"] == "early" and out["options"][0]["fails"] == 1
    html = (build(dst) / "index.html").read_text()
    assert 'id="sections"' in html and "startSections" in html
    assert check(dst) == []
    (dst / "flights.json").write_text(json.dumps({"rules": RULES, "options": [{**opt("early", "2026-11-21T19:00+07:00", "2026-11-21T18:30+07:00"), "recommended": True}]}))
    assert any("B not before A" in x for x in check(dst))


def test_author_chosen_best_wins():
    p = evaluate({"rules": RULES, "best": "dear", "options": [opt("cheap", "2026-11-21T18:10+07:00", "2026-11-21T18:30+07:00", price=1), opt("dear", "2026-11-21T18:10+07:00", "2026-11-21T18:30+07:00", price=9)]})
    assert p["best"] == "dear"
    assert evaluate({"rules": RULES, "options": p["options"]})["best"] == "cheap"


def test_max_fare_cap_per_person_headroom_and_over_budget():
    cap = [{"type": "max_fare", "max": 25000, "label": "cap"}]
    ok = {"id": "ok", "legs": [leg("a", "2026-11-21T12:00+05:30", "2026-11-21T18:10+07:00", 24287), {**leg("d", "2026-11-22T07:45+07:00", "2026-11-22T09:30+07:00", 11026), "pax": 2}]}
    bad = {"id": "bad", "legs": [leg("a", "2026-11-21T03:30+05:30", "2026-11-21T09:00+07:00", 26804)]}
    p = evaluate({"rules": cap, "options": [bad, ok]})
    by = {o["id"]: o for o in p["options"]}
    assert by["ok"]["legs"][0]["cap"] == {"ok": True, "headroom": 713} and by["ok"]["legs"][1]["cap"]["headroom"] == 25000 - 5513
    assert not by["ok"]["over"] and by["ok"]["results"][0]["detail"].startswith("tightest")
    assert by["bad"]["over"] and by["bad"]["fails"] == 1 and "26,804" in by["bad"]["results"][0]["detail"]
    assert p["best"] == "ok"
    assert evaluate({"rules": cap, "best": "bad", "options": [bad, ok]})["best"] == "ok"   # an over-budget option is never the pick
    assert problems({"rules": cap, "chosen": "bad", "options": [bad, ok]})                   # nor can it be the chosen plan
