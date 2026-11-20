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
