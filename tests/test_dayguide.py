"""dayGuide section: conversions, generated map links, validation, and the renderer (run under node)."""
import copy
import json
import pathlib
import shutil
import subprocess

import pytest

import tripforge.site.sections as S
from tripforge.site.dayguide import maps_url, process

FX = {"from": "AAA", "to": "BBB", "rate": 2.5, "date": "1 Jan 2030", "source": "https://example.com/rate"}


def guide():
    return copy.deepcopy({
        "fx": FX,
        "days": [{
            "id": "d1", "tab": "Mon 1", "date": "2030-01-01", "title": "Day one",
            "timeline": [
                {"time": "09:00", "end": "09:30", "title": "Breakfast", "name": "Cafe <b>", "area": "Old Town", "cost": [100, 200], "kind": "eat"},
                {"time": "23:30", "title": "Bar", "name": "Roof", "area": "Hill", "maps": "https://maps.example.com/x", "verified": True, "cost": 300},
                {"time": "00:45", "title": "Walk home"},
            ],
            "eat": [{"meal": "Lunch", "name": "Noodle Shop", "area": "Market", "order": [{"dish": "Noodles", "cost": 60}, "Tea"], "how": {"text": "Bus", "mins": 20, "cost": 30}}],
            "nightlife": [{"time": "22:00", "name": "Club", "entry": [300, 500], "dress": "smart"}],
            "do": [{"name": "Beach", "kind": "beach", "url": "https://example.com/book"}],
            "backup": {"title": "If it rains", "items": [{"name": "Museum", "area": "Centre", "cost": 150}]},
            "budget": {"rows": [{"item": "Food", "cost": [400, 600]}, {"item": "Taxi", "home": 500}]},
            "book": [{"t": "Boat", "u": "https://example.com/boat", "d": "refundable"}],
            "notes": ["a note"],
        }, {"id": "d2", "tab": "Tue 2", "date": "2030-01-02", "title": "Day two", "timeline": [{"time": "08:00", "title": "Fly"}]}],
    })


def test_conversion_and_generated_maps_link():
    out = process(guide())
    row = out["days"][0]["timeline"][0]
    assert row["cost_p"]["label"] == "AAA 100-200 (≈BBB 250-500)"
    assert row["maps"] == "https://www.google.com/maps/search/?api=1&query=Cafe+%3Cb%3E+Old+Town" == maps_url("Cafe <b>", "Old Town")
    assert out["days"][0]["timeline"][1]["maps"] == "https://maps.example.com/x"      # an author-given pin wins
    assert "maps" not in out["days"][0]["timeline"][2]                                 # no name, no map link
    assert out["days"][0]["eat"][0]["how"]["cost_p"]["home_lo"] == 75 and out["days"][0]["eat"][0]["order"][0]["cost_p"]["home_hi"] == 150


def test_verified_flag_defaults_to_false():
    tl = process(guide())["days"][0]["timeline"]
    assert [r["verified"] for r in tl] == [False, True, False]


def test_day_budget_sums_local_and_home_rows():
    b = process(guide())["days"][0]["budget"]
    assert (b["total"]["lo"], b["total"]["hi"]) == (1000 + 500, 1500 + 500) and b["total"]["label"] == "BBB 1,500-2,000"


def test_next_day_small_hours_are_allowed_but_backwards_is_not():
    process(guide())   # 23:30 then 00:45 is fine
    g = guide(); g["days"][0]["timeline"][1]["time"] = "08:00"
    with pytest.raises(ValueError, match="before the row above"):
        process(g)


@pytest.mark.parametrize("edit, msg", [
    (lambda g: g["fx"].pop("date"), "fx.date"),
    (lambda g: g["fx"].update(rate=-1), "positive"),
    (lambda g: g["days"][0]["timeline"][0].update(time="9am"), "HH:MM"),
    (lambda g: g["days"][0]["timeline"][0].update(maps="javascript:alert(1)"), "https"),
    (lambda g: g["days"][0]["book"][0].update(u="http://example.com"), "https"),
    (lambda g: g["days"][0]["timeline"][0].update(cost=[300, 100]), "cost must be"),
    (lambda g: g["days"][0].update(timeline=[]), "needs a timeline"),
    (lambda g: g["days"][0]["budget"]["rows"][0].pop("cost"), "needs cost"),
])
def test_bad_input_is_refused(edit, msg):
    g = guide(); edit(g)
    with pytest.raises(ValueError, match=msg):
        process(g)


def test_section_sync_runs_the_processor(tmp_path):
    from test_sections import _trip
    dst = _trip(tmp_path, [{"id": "days", "src": "days.json", "kind": "dayGuide"}])
    (dst / "days.json").write_text(json.dumps(guide()))
    assert S.sync(dst)[0]["state"] == "updated"
    assert json.loads((dst / "site" / "data" / "days.json").read_text())["days"][0]["timeline"][0]["maps"].startswith("https://www.google.com/maps/")
    bad = guide(); bad["days"][0]["timeline"][0]["time"] = "x"
    (dst / "days.json").write_text(json.dumps(bad))
    assert S.sync(dst)[0]["state"] == "error" and S.gate_problems(dst)


def _render(data, today=None):
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    js = (pathlib.Path(S.__file__).parent / "js" / "20-sections.js").read_text()
    pre = ("const esc=s=>String(s??'').replace(/[&<>\"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c]));"
           "const TRIP={sym:'X',tz:'UTC'};const DATA={sections:[]};globalThis.window=globalThis;"
           "const document={getElementById:()=>null,querySelectorAll:()=>[],addEventListener(){}};"
           + (f"Date.prototype.toLocaleDateString=()=>{json.dumps(today)};" if today else ""))
    r = subprocess.run([node, "-e", pre + js + f"\nconsole.log(SEC_RENDER.dayGuide({json.dumps(data)}))"], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    return r.stdout


def test_renderer_shows_selector_links_pills_and_escapes():
    out = _render(process(guide()))
    assert out.count("data-dg-day=") == 2 and 'aria-pressed="true"' in out
    assert out.count("<div class=\"dg-day\" data-d=\"d2\" hidden>") == 1 and "data-d=\"d1\" hidden" not in out   # first day selected
    assert 'href="https://www.google.com/maps/search/?api=1&amp;query=Cafe+%3Cb%3E+Old+Town"' in out
    assert "Cafe <b>" not in out and "&lt;b&gt;" in out                                 # names are escaped
    assert out.count(">unverified</span>") == 7 and "est AAA 100-200 (≈BBB 250-500)" in out   # every item except the one marked verified
    assert "est AAA 300 (≈BBB 750)" in out                                                  # a verified row still says est: prices are never quotes
    assert 'href="https://example.com/boat"' in out and "Book ahead" in out and "Day total" in out
    assert "javascript:" not in out


def test_renderer_opens_on_today_when_it_is_a_trip_day():
    out = _render(process(guide()), today="2030-01-02")
    assert 'data-d="d1" hidden' in out and "data-d=\"d2\" hidden" not in out and "<small>today</small>" in out


def test_renderer_never_links_a_non_https_url():
    d = process(guide()); d["days"][0]["do"][0]["url"] = "javascript:alert(1)"; d["days"][0]["do"][0]["src"] = "http://x.example"
    out = _render(d)
    assert "javascript:alert" not in out and "http://x.example" not in out
