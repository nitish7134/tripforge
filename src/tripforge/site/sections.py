"""Independent page sections: each one is its own JSON file, prepared and loaded on its own.

trip.json declares `data.sections: [{"id": "flights", "title": "Flights", "kind": "flightPlan", "src": "flights.json", "every": 300}]`.
`sync` turns every `src` (a path relative to the trip folder) into `site/data/<id>.json` concurrently: a missing, slow or
broken source only affects its own section, and the page picks the file up without a rebuild. In the browser
(js/20-sections.js) every section also fetches and refreshes independently, so one slow or failing section never blocks another.
"""
from __future__ import annotations

import json
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def _flight_plan(raw: dict) -> dict:
    from .flightplan import evaluate
    return evaluate(raw)


def _day_guide(raw: dict) -> dict:
    from .dayguide import process
    return process(raw)


PROCESSORS = {"flightPlan": _flight_plan, "dayGuide": _day_guide}   # kind -> raw dict -> page JSON; other kinds are passed through unchanged


def declared(trip_dir: Path) -> list[dict]:
    cfg = json.loads((trip_dir / "site" / "trip.json").read_text())
    return cfg.get("data", {}).get("sections", [])


def _one(trip_dir: Path, sec: dict) -> dict:
    t0 = time.monotonic()
    src = trip_dir / sec["src"]
    if not src.exists():
        return {"id": sec["id"], "state": "waiting", "msg": f"{sec['src']} not written yet", "ms": 0}
    try:
        raw = json.loads(src.read_text())
        out = PROCESSORS.get(sec.get("kind"), lambda x: x)(raw)
        dst = trip_dir / "site" / "data" / f"{sec['id']}.json"
        dst.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(out, ensure_ascii=False)
        if not dst.exists() or dst.read_text() != text:   # only touch the file when it changed
            tmp = dst.with_suffix(".tmp"); tmp.write_text(text); tmp.replace(dst)
            state = "updated"
        else:
            state = "unchanged"
        return {"id": sec["id"], "state": state, "msg": "", "ms": round((time.monotonic() - t0) * 1000)}
    except Exception as ex:   # one bad section must not stop the others
        return {"id": sec["id"], "state": "error", "msg": f"{type(ex).__name__}: {ex}", "ms": round((time.monotonic() - t0) * 1000)}


def sync(trip_dir: Path, workers: int = 8) -> list[dict]:
    """Prepare every declared section concurrently; returns one status row per section (state: updated | unchanged | waiting | error)."""
    secs = declared(trip_dir)
    if not secs:
        return []
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(secs)))) as ex:
        rows = list(ex.map(lambda s: _one(trip_dir, s), secs))
    dist = trip_dir / "site" / "dist" / "data"
    if dist.parent.exists():   # keep a built dist in step so it can be copied to the host as is
        dist.mkdir(exist_ok=True)
        for r in rows:
            f = trip_dir / "site" / "data" / f"{r['id']}.json"
            if r["state"] in ("updated", "unchanged") and f.exists():
                shutil.copy(f, dist / f.name)
    return rows


def gate_problems(trip_dir: Path) -> list[str]:
    """Deploy gate: sections whose source exists must prepare cleanly, and flight options marked `recommended` must pass their hard rules."""
    from .flightplan import problems
    out = []
    for sec in declared(trip_dir):
        src = trip_dir / sec["src"]
        if not src.exists():
            continue
        try:
            raw = json.loads(src.read_text())
            PROCESSORS.get(sec.get("kind"), lambda x: x)(raw)
            if sec.get("kind") == "flightPlan":
                out += problems(raw)
        except Exception as ex:
            out.append(f"section '{sec['id']}': {type(ex).__name__}: {ex}")
    return out
