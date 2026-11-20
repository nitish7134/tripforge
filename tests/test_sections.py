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
