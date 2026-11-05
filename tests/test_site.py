"""`tripforge site`: scaffold from site_template/ with a mocked plan.json, build, check, merge_plans."""
import importlib.util
import json
import os
import shutil
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from tripforge import site
from tripforge.cli import app

ROOT = Path(__file__).resolve().parents[1]
TPL = ROOT / "site_template"

BRIEF = {"from": "ZZH", "home_city": "Homeport", "people": 2, "start": "2031-05-10", "currency": "USD",
         "stops": "Alpha Town:2,Beta Bay/Old Port:2",
         "site": {"title": "Test Isles", "tz": "Europe/Paris", "home_tz": "America/New_York",
                  "travellers": ["Alex", "Sam"], "local_currency": "EUR", "voice": {"lang": "fr", "name": "French"}},
         "private_patterns": ["SECRETREF\\d+"]}

PLAN = {"meta": {"home": "ZZH", "home_name": "Homeport Intl", "people": 2, "currency": "USD", "title": "Alpha + Beta"},
        "fx": {"EUR": {"rate": 1.1}},
        "options": [{"start": "2031-05-10", "end": "2031-05-14",
                     "stops": [{"name": "Alpha Town", "nights": 2, "checkin": "2031-05-10", "checkout": "2031-05-12",
                                "stays": [{"name": "Harbour Flat", "url": "https://example.com/1"}]},
                               {"name": "Beta Bay", "nights": 2, "checkin": "2031-05-12", "checkout": "2031-05-14", "stays": []}],
                     "legs": [{"kind": "flight", "date": "2031-05-10", "orig": "ZZH", "dest": "ZZA", "from_name": "Homeport",
                               "to_name": "Alpha Town", "rows": [{"airline": "Zephyr", "flight": "ZV 101", "from": "ZZH",
                                                                  "to": "ZZA", "dep": "08:00", "arr": "11:30"}]},
                              {"kind": "ground", "date": "2031-05-12", "orig": "Alpha Town", "dest": "Beta Bay",
                               "ground": {"mode": "ferry", "hours": [2, 3]}},
                              {"kind": "flight", "date": "2031-05-14", "orig": "ZZB", "dest": "ZZH", "from_name": "Beta Bay",
                               "to_name": "home", "rows": [{"airline": "Zephyr", "flight": "ZV 202", "from": "ZZB",
                                                            "to": "ZZH", "dep": "15:00", "arr": "21:00"}]}]}]}


@pytest.fixture(autouse=True)
def _template(monkeypatch):
    monkeypatch.setenv("TRIPFORGE_SITE_TEMPLATE", str(TPL))
    if not (os.environ.get("NODE") or shutil.which("node")):
        monkeypatch.setenv("TRIPFORGE_SKIP_NODE", "1")


def _data(js: str, name: str):
    """Pull `const NAME=<json>;` out of a generated module."""
    start = js.index(f"const {name}=") + len(f"const {name}=")
    return json.JSONDecoder().raw_decode(js[start:])[0]


def test_init_fills_trip_from_plan(tmp_path):
    left = site.init(tmp_path / "s", BRIEF, PLAN)
    js = (tmp_path / "s/src/js/03-data-trip.js").read_text()
    trip, days, stays, events = (_data(js, n) for n in ("TRIP", "DAYS", "STAYS", "EVENTS"))
    assert trip["title"] == "Test Isles" and trip["day0"] == "2031-05-10" and len(days) == 5
    assert trip["cur"]["here"] == "EUR" and trip["cur"]["home"] == "USD" and trip["cur"]["rate"] == 1.1
    assert list(trip["people"].values()) == ["Alex", "Sam"] and trip["home"]["code"] == "ZZH"
    assert trip["depart"] == "2031-05-10T08:00:00-04:00"  # home tz offset in May
    assert [c["n"] for c in trip["cities"]] == ["Alpha Town", "Beta Bay"]
    assert days[0]["sleep"] == "alphatown" and days[2]["sleep"] == "betabay" and "sleep" not in days[4]
    assert days[0]["move"][0]["name"] == "Zephyr ZV 101" and days[2]["move"][0]["kind"] == "taxi"
    assert stays["alphatown"]["name"] == "Harbour Flat" and stays["betabay"]["name"].startswith("TODO")
    assert all(s["ref"] == "" for s in stays.values())  # refs are never invented
    flights = [e for e in events if e["kind"] == "fly"]
    assert flights[0]["t"].endswith("-04:00") and flights[1]["t"].endswith("+02:00")
    assert any("coordinates" in t for t in left) and any("headline" in t for t in left)
    shell = (tmp_path / "s/src/index.html").read_text()
    assert '<base href="/testisles/">' in shell and "__" not in shell.replace("__proto__", "")
    assert "__TITLE__" not in (tmp_path / "s/lock/index.html").read_text()
    assert not (tmp_path / "s/index.html").exists() and not (tmp_path / "s/README.md").exists()


def test_init_brief_only_and_refuses_non_empty(tmp_path):
    site.init(tmp_path / "s", BRIEF, {})
    days = _data((tmp_path / "s/src/js/03-data-trip.js").read_text(), "DAYS")
    assert len(days) == 5 and days[2]["where"] == "Beta Bay"
    with pytest.raises(site.SiteError, match="not empty"):
        site.init(tmp_path / "s", BRIEF, {})


def test_bad_time_zone_is_an_error(tmp_path):
    with pytest.raises(site.SiteError, match="time zone"):
        site.init(tmp_path / "s", {**BRIEF, "site": {**BRIEF["site"], "tz": "Nowhere/Land"}}, PLAN)


def test_cli_build_check_and_privacy(tmp_path):
    (tmp_path / "out").mkdir()
    (tmp_path / "out/plan.json").write_text(json.dumps(PLAN))
    (tmp_path / "brief.yaml").write_text(yaml.safe_dump(BRIEF))
    s = tmp_path / "site"
    r = CliRunner()
    assert r.invoke(app, ["site", "init", str(s), "--brief", str(tmp_path / "brief.yaml")]).exit_code == 0
    assert r.invoke(app, ["site", "check", str(s)]).exit_code == 1  # not built yet: index.html is stale
    assert r.invoke(app, ["site", "build", str(s)]).exit_code == 0
    res = r.invoke(app, ["site", "check", str(s)])
    assert res.exit_code == 0, res.output
    (s / "data/plans.json").write_text('{"note":"ref SECRETREF42"}')
    res = r.invoke(app, ["site", "check", str(s)])
    assert res.exit_code == 1 and "SECRETREF42" in res.output


def test_template_example_builds(tmp_path):
    shutil.copytree(TPL, tmp_path / "t")
    code, out = site.run_build(tmp_path / "t")
    assert code == 0, out
    html = (tmp_path / "t/index.html").read_text()
    assert "const TRIP=" in html and "<!-- @js -->" not in html


def _merge():
    spec = importlib.util.spec_from_file_location("merge_plans", TPL / "tools/merge_plans.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_merge_plans_validates_and_blocks_private(tmp_path):
    day = {"date": "2031-05-10", "title": "Day", "slots": [{"when": "night", "label": "Out", "options": [
        {"name": "In", "kind": "party", "lat": 1.0, "lon": 2.0, "links": [{"t": "Web", "u": "https://a.example"},
                                                                         {"t": "Bad", "u": "http://b.example"}], "veg": "salad"},
        {"name": "Far", "kind": "food", "lat": 50.0, "lon": 2.0},
        {"name": "No coords", "kind": "food"}]}]}
    (tmp_path / "alpha.json").write_text(json.dumps({"place": "Alpha", "days": [day], "sources": ["https://a.example"]}))
    plans, warn = _merge().merge(tmp_path, bbox=[0, 0, 10, 10])
    o = plans["days"]["2031-05-10"]["slots"][0]["o"]
    assert [x["n"] for x in o] == ["In"] and o[0]["links"] == [{"t": "Web", "u": "https://a.example"}]
    assert o[0]["diet"] == "salad" and len(warn) == 2
    with pytest.raises(ValueError, match="private"):
        _merge().merge(tmp_path, private=[r"\bIn\b"])
