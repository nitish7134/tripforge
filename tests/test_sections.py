"""Sections load independently: a missing, broken or slow source never blocks the others."""
import json, pathlib, shutil, time
import tripforge.site.sections as S

EX = pathlib.Path(__file__).resolve().parents[1] / "trips" / "example-vela-islands"


def _trip(tmp_path, secs):
    dst = tmp_path / "t"; shutil.copytree(EX, dst); shutil.rmtree(dst / "site" / "dist", ignore_errors=True)
    cfg = json.loads((dst / "site" / "trip.json").read_text()); cfg["data"]["sections"] = secs
    (dst / "site" / "trip.json").write_text(json.dumps(cfg)); return dst


def test_failures_are_isolated(tmp_path):
    dst = _trip(tmp_path, [{"id": "a", "src": "a.json"}, {"id": "b", "src": "b.json"}, {"id": "c", "src": "c.json", "kind": "flightPlan"}])
    (dst / "a.json").write_text('{"days": []}')
    (dst / "c.json").write_text('{"rules": [{"type": "bogus", "leg": "x"}], "options": [{"id": "o", "legs": [{"role": "x", "dep": "2026-01-01T00:00+00:00", "arr": "2026-01-01T01:00+00:00"}]}]}')
    rows = {r["id"]: r for r in S.sync(dst)}
    assert rows["a"]["state"] == "updated" and rows["b"]["state"] == "waiting" and rows["c"]["state"] == "error"
    assert (dst / "site" / "data" / "a.json").exists() and not (dst / "site" / "data" / "b.json").exists()


def test_sections_run_concurrently(tmp_path, monkeypatch):
    dst = _trip(tmp_path, [{"id": f"s{i}", "src": f"s{i}.json", "kind": "slow"} for i in range(4)])
    for i in range(4):
        (dst / f"s{i}.json").write_text("{}")
    def slow(x):
        time.sleep(0.3); return x
    monkeypatch.setitem(S.PROCESSORS, "slow", slow)
    t0 = time.monotonic(); rows = S.sync(dst)
    assert all(r["state"] == "updated" for r in rows) and time.monotonic() - t0 < 0.9   # 4 x 0.3 s serial would be 1.2 s


def test_no_sections_is_a_noop(tmp_path):
    assert S.sync(_trip(tmp_path, [])) == []


def _render(kind, data):
    """Run js/20-sections.js under node with a stub DOM and return SEC_RENDER[kind](data)."""
    import shutil as sh, subprocess
    node = sh.which("node")
    if not node:
        import pytest; pytest.skip("node not installed")
    js = (pathlib.Path(S.__file__).parent / "js" / "20-sections.js").read_text()
    pre = ("const esc=s=>String(s??'').replace(/[&<>\"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c]));"
           "const TRIP={sym:'X'};const DATA={sections:[]};globalThis.window=globalThis;"
           "const document={getElementById:()=>null,querySelectorAll:()=>[],addEventListener(){}};")
    r = subprocess.run([node, "-e", pre + js + f"\nconsole.log(SEC_RENDER[{json.dumps(kind)}]({json.dumps(data)}))"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout


def test_stays_renderer_links_listings_and_flags_unverified():
    out = _render("stays", {"places": [{"place": "P", "top_pick": {"name": "Alpha", "url": "https://example.com/a", "est_inr": "9000", "verified": True},
                                         "runner_up": {"name": "Beta<script>", "url": "javascript:alert(1)"}}]})
    assert 'href="https://example.com/a"' in out and "INR 9000" in out
    assert out.count("unverified") == 1                   # only the unverified runner-up
    assert "javascript:" not in out.split("href=")[-1] and "<script>" not in out   # unsafe URL is not linked, names are escaped


def test_flight_renderer_marks_unverified_legs():
    plan = {"options": [{"id": "o", "label": "O", "legs": [{"who": "A", "dir": "Out", "flight": "XX 1", "from": "A", "to": "B", "depL": "10:00", "arrL": "12:00"}], "results": [], "total": 0}]}
    assert "unverified" in _render("flightPlan", plan)
    plan["verified"] = True
    assert "unverified" not in _render("flightPlan", plan)


def test_stays_options_order_gives_top_pick_and_runner_up():
    out = _render("stays", {"places": [{"name": "P", "options": [
        {"title": "First", "url": "https://example.com/1", "price_night_inr": 6000, "rating": 4.8, "verified": "partial: price estimated"},
        {"title": "Second", "url": "https://example.com/2"}, {"title": "Third", "url": "https://example.com/3"}]}]})
    assert "Top pick" in out and "Runner-up" in out and "More options (1)" in out
    assert "INR 6,000 a night" in out and "price unverified" in out and 'target="_blank"' in out and "Checked: partial" in out


def test_flight_renderer_proxy_schedule_pill():
    plan = {"options": [{"id": "o", "label": "O", "legs": [{"who": "A", "dir": "Out", "flight": "XX 1", "from": "A", "to": "B", "depL": "10:00", "arrL": "12:00", "verified": "proxy"}], "results": [], "total": 0}]}
    out = _render("flightPlan", plan)
    assert "proxy schedule" in out and "unverified" not in out


def test_build_without_photos_or_checklists_requests_no_missing_image(tmp_path):
    from tripforge.site import build
    dst = _trip(tmp_path, [])
    cfg = json.loads((dst / "site" / "trip.json").read_text()); cfg["data"]["todo"] = []; cfg["data"]["pack"] = []
    (dst / "site" / "trip.json").write_text(json.dumps(cfg))
    html = (build(dst) / "index.html").read_text()
    assert "lockbg.jpg" not in html and "if(!document.getElementById(id))return" in html


def test_stays_string_picks_become_the_reason_for_the_first_two_options():
    out = _render("stays", {"places": [{"name": "P", "top_pick": "most reviews", "runner_up": "pricier", "area_comparison": "Area note",
                                         "options": [{"title": "One", "url": "https://e.com/1"}, {"title": "Two", "url": "https://e.com/2"}, {"title": "Three"}]}]})
    assert "Top pick" in out and "most reviews" in out and "Runner-up" in out and "pricier" in out and "Area note" in out
    assert "More options (1)" in out and out.count("One") == 1


def test_section_classes_do_not_collide_with_page_header_class():
    """`.top` is the page header (flex row); a section element using it renders as squeezed columns."""
    out = _render("stays", {"places": [{"name": "P", "options": [{"title": "One"}]}]})
    assert 'class="fl top"' not in out and "fl pick" in out


def test_chosen_flight_option_on_top_rest_folded():
    mk = lambda i: {"id": i, "label": "Opt " + i, "legs": [], "results": [], "total": 1}
    out = _render("flightPlan", {"chosen": "b", "options": [mk("a"), mk("b"), mk("c")]})
    assert "chosen plan" in out and "Other options (2)" in out
    assert out.index("Opt b") < out.index("Other options") < out.index("Opt a")
    assert "Other options" not in _render("flightPlan", {"options": [mk("a"), mk("b")]})


def test_book_renderer_rows_badges_links_total():
    out = _render("book", {"checked_at": "22:10 IST", "total_inr": 93000, "legs": [
        {"who": "Delhi", "flight": "XX 1", "price_inr": 27000, "available": True, "url": "https://air.example/b"},
        {"who": "Mumbai", "flight": "YY 2", "price_inr": 18000, "availability": "sold out"},
        {"who": "Home", "flight": "ZZ 3", "price": 5}]})
    assert "INR 27,000" in out and "pill ok" in out and "pill bad" in out and "not checked" in out
    assert 'href="https://air.example/b"' in out and 'target="_blank"' in out and "INR 93,000" in out and "Not booked" in out


def test_book_renderer_booking_links_and_unchanged_price():
    out = _render("book", {"new_total_inr": 5, "legs": [{"flight_no": "XX 1", "price_inr": 10, "old_price_inr": 10, "status": "listed",
        "booking_links": {"google_flights": "https://g.example/f", "airline": "javascript:x"}},
        {"flight_no": "YY 2", "price_inr": 30, "old_price_inr": 20, "status": "changed"}]})
    assert 'href="https://g.example/f"' in out and "google flights" in out and "javascript:" not in out
    assert "(was 10)" not in out and "(was 20)" in out and "price changed" in out and "pill ok" in out


def test_brief_renderer():
    out = _render("brief", {"assumptions": [{"t": "Flights", "d": "C2"}, "Nothing booked"], "changes": [{"t": "If X", "d": "do Y"}],
                            "budget": {"rows": [["Flights", "100", "two people"]], "total": "150"}})
    assert "Assumptions" in out and "Nothing booked" in out and "What changes if" in out and "two people" in out and ">150<" in out


def test_flight_renderer_cap_pills_and_over_budget():
    leg = lambda f, cap: {"who": "A", "dir": "Out", "flight": f, "from": "A", "to": "B", "depL": "1", "arrL": "2", "price": 1, "cap": cap}
    out = _render("flightPlan", {"options": [{"id": "o", "label": "O", "over": True, "legs": [leg("X1", {"ok": True, "headroom": 713}), leg("X2", {"ok": False, "headroom": -1804})], "results": [], "total": 0}]})
    assert "Over budget" in out and "fp over" in out and "713 under cap" in out and "over cap by X1,804" in out


def test_brief_summary_block():
    out = _render("brief", {"summary": {"who": "A and B", "dates": "1-4", "route": "X to Y", "total": "100",
        "book_first": [{"t": "Flights", "u": "https://e.com/f", "d": "first"}, {"t": "Bad", "u": "javascript:1"}], "checks": [{"t": "rule", "ok": True}, {"t": "rule2", "ok": False}, {"t": "soft", "ok": "warn"}]}})
    assert "A and B" in out and 'href="https://e.com/f"' in out and "javascript:" not in out and "1. " in out and "2. Bad" in out
    assert "fr ok" in out and "fr bad" in out and "fr warn" in out
