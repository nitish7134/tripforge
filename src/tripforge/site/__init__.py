"""tripforge site: build a phone-first, PIN-gated trip web app from one trip.json.

Everything destination- or traveller-specific lives in trips/<slug>/site/trip.json (see SCHEMA.md).
This package holds only the reusable template: shell, CSS modules, JS modules, lock page, service worker,
and the server pieces (PIN gate + shared ledger API, flight-status fetcher, Caddy snippet).

    tripforge site init  trips/<slug>            # write a trip.json skeleton from brief.yaml / plan.json
    tripforge site build trips/<slug>            # trip.json -> trips/<slug>/site/dist/ (index.html, sw.js, manifest, lock/, icon)
    tripforge site host  trips/<slug>            # print the exact server steps (Caddy block, systemd units, env) for this trip
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from datetime import date, datetime, timedelta
from pathlib import Path

from jinja2 import ChainableUndefined, Environment, FileSystemLoader

HERE = Path(__file__).resolve().parent
SHIP = ["index.html", "sw.js", "manifest.webmanifest", "icon.svg", "lock/index.html", "lock/bg.jpg", "data/plans.json"]


def order() -> dict[str, list[str]]:
    sec, out = None, {"css": [], "js": []}
    for line in (HERE / "ORDER.txt").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line in ("[css]", "[js]"):
            sec = line[1:-1]
            continue
        out[sec].append(line)
    return out


def _derive(trip: dict, events: list | None = None) -> dict:
    """Fill the fields the templates need from the few the author writes."""
    t = dict(trip); events = events or []
    start, end = date.fromisoformat(t["start"]), date.fromisoformat(t["end"])
    t.setdefault("ndays", (end - start).days + 1)
    t.setdefault("nights", (end - start).days)
    t.setdefault("tzOffset", t.get("tzOffset") or _tz_offset(t["tz"], start))
    t.setdefault("homeTz", t["tz"])
    t.setdefault("tzLabel", _tz_label(t["tz"]))
    t.setdefault("homeTzLabel", _tz_label(t["homeTz"]))
    t.setdefault("homeCur", t["cur"])
    t.setdefault("homeSym", t["sym"])
    t.setdefault("split", "equal" if len(t.get("people", [])) > 1 and t.get("split") != "none" else "none")
    t.setdefault("features", {})
    t["features"].setdefault("fx", t["homeCur"] != t["cur"])
    t["features"].setdefault("visitorRole", False)
    t.setdefault("defaultTheme", "plain")
    t.setdefault("built", date.today().isoformat())
    t.setdefault("locale", "en")
    t.setdefault("dates", f"{start.day} {start.strftime('%b')} – {end.day} {end.strftime('%b')}")
    flights = [e for e in events if e.get("kind") == "fly"]
    t.setdefault("t0", flights[0]["t"] if flights else f"{t['start']}T00:00:00{t['tzOffset']}")
    t.setdefault("t1", flights[-1]["t"] if flights else f"{t['end']}T23:59:00{t['tzOffset']}")
    t.setdefault("t0Label", datetime.fromisoformat(t["t0"]).strftime("%a %-d %b, %H:%M"))
    return t


def _tz_offset(tz: str, on: date) -> str:
    from zoneinfo import ZoneInfo
    off = datetime(on.year, on.month, on.day, 12, tzinfo=ZoneInfo(tz)).utcoffset() or timedelta()
    s = int(off.total_seconds()); sign = "+" if s >= 0 else "-"; s = abs(s)
    return f"{sign}{s // 3600:02d}:{(s % 3600) // 60:02d}"


def _tz_label(tz: str) -> str:
    """Short zone label for the header clock (e.g. GMT+5:30 -> the zone's own abbreviation when it has one)."""
    from zoneinfo import ZoneInfo
    abbr = datetime.now(ZoneInfo(tz)).strftime("%Z")
    return abbr if abbr and not abbr.startswith(("+", "-")) else tz.split("/")[-1].replace("_", " ")[:6]



def _data_defaults(d: dict, t: dict) -> dict:
    d = dict(d)
    d.setdefault("runway", {})
    r = d["runway"]
    stays = d.get("stays", {})
    r.setdefault("booked", sum(1 for s in stays.values() if s.get("st") == "ok") + sum(1 for e in d.get("events", []) if e.get("kind") == "fly" and e.get("st") == "ok"))
    r.setdefault("open", sum(1 for s in stays.values() if s.get("st") == "open") + sum(1 for e in d.get("events", []) if e.get("kind") == "fly" and e.get("st") == "open"))
    r.setdefault("img", next((x["img"] for x in d.get("days", []) if x.get("img")), "lockbg"))
    d.setdefault("cred", {})
    d.setdefault("quick", [100, 300, 500, 1000, 2500])
    d.setdefault("spendExample", "dinner")
    d.setdefault("kit", [])
    d.setdefault("templates", [])
    d.setdefault("foot", "Prices marked as ranges are estimates from operator and guide pages, not quotes. Weather, flight status and the ledger update whenever the page is online.")
    return d


def build(trip_dir: Path, bump: bool = True) -> Path:
    site = trip_dir / "site"
    cfg = json.loads((site / "trip.json").read_text())
    t = _derive(cfg["trip"], cfg.get("data", {}).get("events")); d = _data_defaults(cfg.get("data", {}), t)
    dist = site / "dist"; dist.mkdir(parents=True, exist_ok=True)
    env = Environment(loader=FileSystemLoader(str(HERE)), undefined=ChainableUndefined, autoescape=False)
    env.filters["urlencode"] = lambda s: __import__("urllib.parse").parse.quote(str(s))
    shell = env.get_template("shell.html.j2").render(t=t, d=d)
    o = order()
    css = "".join((HERE / "styles" / f"{n}.css").read_text() for n in o["css"])
    # trip-specific theme accents and extra styles may be appended from trip.json
    css += "".join(f'[data-theme="{k}"]{{--mari:{v["accent"]};--mari-ink:{v.get("ink", "#1a1200")}}}\n' for k, v in d.get("themeAccents", {}).items())
    css += d.get("extraCss", "")
    js = "".join((HERE / "js" / f"{n}.js").read_text() for n in o["js"])
    js = js.replace("/*@TRIP*/{}/*@/TRIP*/", json.dumps(t, ensure_ascii=False)).replace("/*@DATA*/{}/*@/DATA*/", json.dumps(d, ensure_ascii=False))
    html = shell.replace("<!-- @css -->", "<style>\n" + css.rstrip("\n") + "\n</style>").replace("<!-- @js -->", "<script>\n" + js.rstrip("\n") + "\n</script>")
    _syntax_check(js)
    _privacy_check(html, cfg.get("private_patterns", []))
    (dist / "index.html").write_text(html)
    # service worker: version from the previous build + 1
    prev = dist / "sw.js"; v = 1
    if prev.exists():
        m = re.search(rf"{re.escape(t['slug'])}-v(\d+)", prev.read_text()); v = (int(m.group(1)) + (1 if bump else 0)) if m else 1
    imgs = sorted({f"./img/{x['img']}.jpg" for x in d.get("days", []) if x.get("img")})
    (dist / "sw.js").write_text(env.get_template("sw.js.j2").render(slug=t["slug"], version=v, files=["./", "./index.html", "./manifest.webmanifest", "./icon.svg", "./data/plans.json", *imgs]))
    (dist / "manifest.webmanifest").write_text(json.dumps({"name": f"{t['name']} {t['dates']}", "short_name": t["name"], "start_url": "./", "scope": "./", "display": "standalone",
        "background_color": "#0b1220", "theme_color": "#0b1220", "icons": [{"src": "icon.svg", "sizes": "any", "type": "image/svg+xml"}, {"src": "icon-180.png", "sizes": "180x180", "type": "image/png"}]}, ensure_ascii=False))
    (dist / "lock").mkdir(exist_ok=True)
    lock = (HERE / "lock" / "index.html").read_text()
    lock = lock.replace("<title>Goa</title>", f"<title>{t['name']}</title>").replace("<small>22 – 30 NOV</small><h1>Goa</h1><p>Morjim · Baga</p>", f"<small>{t['dates'].upper()}</small><h1>{t['name']}</h1><p>{d.get('lockSub', '')}</p>")
    accent = d.get("themeAccents", {}).get(t["defaultTheme"], {}).get("accent")
    if accent:
        lock = lock.replace("--mari:#1fb6a6", f"--mari:{accent}")
    (dist / "lock" / "index.html").write_text(lock)
    for name in ("icon.svg",):
        src = site / name if (site / name).exists() else HERE / name
        shutil.copy(src, dist / name)
    for extra in ("icon-180.png", "lock/bg.jpg", "lock/icon.svg", "lock/icon-180.png"):
        if (site / extra).exists():
            (dist / extra).parent.mkdir(exist_ok=True); shutil.copy(site / extra, dist / extra)
    if (site / "img").exists():
        shutil.copytree(site / "img", dist / "img", dirs_exist_ok=True)
    if (site / "data").exists():
        shutil.copytree(site / "data", dist / "data", dirs_exist_ok=True)
    return dist


def _syntax_check(js: str) -> None:
    node = shutil.which("node")
    if not node:
        return  # best effort; the browser check in `site verify` catches it otherwise
    tmp = Path(os.environ.get("TMPDIR", "/tmp")) / "tripforge-site-check.js"
    tmp.write_text(js)
    r = subprocess.run([node, "--check", str(tmp)], capture_output=True, text=True)
    tmp.unlink(missing_ok=True)
    if r.returncode:
        raise SystemExit("JS syntax error in the generated page:\n" + r.stderr)


def _privacy_check(html: str, extra: list[str]) -> None:
    pats = [r"\b[A-Z][0-9]{7}\b", r"passport (no|number)", r"\bIFSC\b", r"Account No", *extra]
    hits = [p for p in pats if re.search(p, html)]
    if hits:
        raise SystemExit(f"private data pattern(s) found in the page, not building: {hits}")


def init(trip_dir: Path) -> Path:
    """Write a trip.json skeleton next to brief.yaml, pre-filled from brief.yaml and out/plan.json when present."""
    import yaml
    site = trip_dir / "site"; site.mkdir(parents=True, exist_ok=True)
    out = site / "trip.json"
    if out.exists():
        return out
    brief = yaml.safe_load((trip_dir / "brief.yaml").read_text()) if (trip_dir / "brief.yaml").exists() else {}
    start = str(brief.get("start", date.today().isoformat()))
    nights = int(brief.get("nights", 7))
    end = (date.fromisoformat(start) + timedelta(days=nights)).isoformat()
    people = brief.get("names") or [f"P{i+1}" for i in range(int(brief.get("people", 2)))]
    skel = {
        "trip": {"slug": trip_dir.name, "name": str(brief.get("destination", "Trip")).split(",")[0], "home": str(brief.get("from", "FILL")),
                 "start": start, "end": end, "tz": "FILL/Region_City", "homeTz": "Asia/Kolkata",
                 "cur": str(brief.get("currency", "FILL")), "sym": "FILL", "homeCur": str(brief.get("home_currency", brief.get("currency", "FILL"))), "homeSym": "FILL",
                 "people": [{"k": n[:2].upper(), "n": n} for n in people], "split": "equal", "budget": 0,
                 "defaultTheme": "plain", "visitorTheme": "pg13", "features": {"visitorRole": False}, "speakLang": "en", "roadKmh": 25},
        "data": {"events": [], "stays": {}, "days": [], "tix": {}, "cred": {}, "cities": [], "typical": {}, "todo": [], "pack": [],
                 "driver": [], "kit": [], "smarts": [], "phrases": [], "quick": [100, 300, 500, 1000, 2500], "spendExample": "dinner",
                 "fares": None, "budget": None, "runway": {"headsup": []}, "lockSub": ""},
        "private_patterns": [],
        "_help": "See src/tripforge/site/SCHEMA.md. Fill from out/plan.json + bookings; never put passport numbers or bank details here.",
    }
    out.write_text(json.dumps(skel, indent=1, ensure_ascii=False))
    return out


def host_notes(trip_dir: Path) -> str:
    cfg = json.loads((trip_dir / "site" / "trip.json").read_text()); t = _derive(cfg["trip"], cfg.get("data", {}).get("events")); slug = t["slug"]
    port = cfg.get("hosting", {}).get("port", 8765)
    return (HERE / "HOSTING.md").read_text().replace("<slug>", slug).replace("<port>", str(port)).replace("<pin>", str(cfg.get("hosting", {}).get("pin", "CHOOSE"))) \
        .replace("<who>", ",".join(p["k"] for p in t["people"])).replace("<curs>", ",".join(sorted({t["cur"], t["homeCur"]})))
