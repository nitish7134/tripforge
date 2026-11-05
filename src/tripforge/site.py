"""`tripforge site`: scaffold, build and check a phone trip page from site_template/.

init  copies site_template/ to a directory and writes the two trip modules (js/03-data-trip.js,
      js/04-data-kit.js) from brief.yaml plus trips/<slug>/out/plan.json when it exists. Whatever the inputs do
      not say is written as a visible TODO, never guessed.
build runs the site's tools/build.py.
check runs build --check, then greps the built page and data/*.json for the brief's private_patterns.
Nothing here names a destination, currency or airport: every value comes from the brief or the plan.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from . import cache
from .stops import split_spec

TODO = "TODO"
ALWAYS_PRIVATE = [r"\b[A-Z][0-9]{7}\b", r"passport (no|number)"]
SKIP_ROOT = {"index.html", "README.md", "build.check.js"}


class SiteError(ValueError):
    pass


def template_dir() -> Path:
    env = os.environ.get("TRIPFORGE_SITE_TEMPLATE")
    d = Path(env).expanduser() if env else cache.repo_root() / "site_template"
    if not (d / "src" / "ORDER.txt").exists():
        raise SiteError(f"site template not found at {d} (set TRIPFORGE_SITE_TEMPLATE)")
    return d


def key_of(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())[:16] or "stop"


def _js(v) -> str:
    return json.dumps(v, ensure_ascii=False)


def _offset(tz: str | None, day: str, hm: str = "12:00") -> str:
    """'+05:30' for tz at that local time, or '+00:00' when tz is unknown."""
    if not tz:
        return "+00:00"
    t = dt.datetime.fromisoformat(f"{day}T{hm}").replace(tzinfo=ZoneInfo(tz))
    off = t.utcoffset() or dt.timedelta(0)
    m = int(off.total_seconds() // 60)
    return f"{'+' if m >= 0 else '-'}{abs(m) // 60:02d}:{abs(m) % 60:02d}"


def _tz(v) -> str | None:
    if not v:
        return None
    try:
        ZoneInfo(str(v))
        return str(v)
    except (ZoneInfoNotFoundError, ValueError):
        raise SiteError(f"unknown time zone {v!r}; use an IANA name like Region/City")


def load_plan(plan_path: Path | None) -> dict:
    if plan_path and plan_path.exists():
        return json.loads(plan_path.read_text())
    return {}


def gather(brief: dict, plan: dict) -> dict:
    """Merge brief + plan into one neutral trip description; missing values stay None."""
    site = brief.get("site") or {}
    opt = (plan.get("options") or [{}])[0]
    meta = plan.get("meta") or {}
    stops = opt.get("stops") or []
    if not stops and brief.get("stops"):
        d = dt.date.fromisoformat(str(brief["start"])) if brief.get("start") else None
        for p in split_spec(str(brief["stops"])):
            s = {"name": p["name"], "nights": p["nights"], "iata": p["iata"], "stay_area": p["area"]}
            if d:
                s["checkin"], d = d.isoformat(), d + dt.timedelta(days=p["nights"])
                s["checkout"] = d.isoformat()
            stops.append(s)
    start = opt.get("start") or (str(brief["start"]) if brief.get("start") else None)
    end = opt.get("end") or (stops[-1].get("checkout") if stops else None)
    home_cur = meta.get("currency") or brief.get("currency")
    fx = plan.get("fx") or {}
    here = site.get("local_currency") or (next(iter(fx)) if len(fx) == 1 else None)
    rate = (fx.get(here) or {}).get("rate") if here else None
    people = site.get("travellers") or []
    n = int(meta.get("people") or brief.get("people") or len(people) or 0)
    return {
        "title": site.get("title") or meta.get("title") or brief.get("destination"),
        "base": site.get("base"), "start": start, "end": end, "stops": stops, "legs": opt.get("legs") or [],
        "home": meta.get("home") or brief.get("from"), "home_city": brief.get("home_city") or meta.get("home_name"),
        "tz": _tz(site.get("tz")), "home_tz": _tz(site.get("home_tz")),
        "cur_home": home_cur, "cur_here": here or home_cur, "rate": rate if here else 1,
        "people": people, "n_people": n, "voice": site.get("voice") or {}, "theme": site.get("theme") or "plain",
    }


def _initials(names: list[str], n: int) -> dict:
    out = {}
    for i, nm in enumerate(names or [f"{TODO} person {i + 1}" for i in range(max(n, 1))]):
        k = next((c for c in nm.upper() if c.isalpha() and c not in out), chr(65 + i))
        out[k] = nm
    return out


def _flight_rows(g: dict) -> list[dict]:
    """One row per leg with a picked flight: {date, from, to, name, dep, arr, home_out}."""
    out = []
    for lg in g["legs"]:
        if lg.get("kind") != "flight":
            continue
        r = (lg.get("rows") or [{}])[0]
        out.append({"date": lg["date"], "from": r.get("from") or lg.get("orig"), "to": r.get("to") or lg.get("dest"),
                    "fc": lg.get("from_name") or "", "tc": lg.get("to_name") or "",
                    "name": " ".join(x for x in (r.get("airline"), r.get("flight")) if x) or f"{TODO} flight",
                    "dep": r.get("dep") or "00:00", "arr": r.get("arr") or "00:00", "to_idx": lg.get("to_idx")})
    return out


def trip_js(g: dict) -> str:
    if not g["start"] or not g["end"]:
        raise SiteError("need start and stops (brief) or a plan.json to know the dates")
    d0, d1 = dt.date.fromisoformat(g["start"]), dt.date.fromisoformat(g["end"])
    tz, htz = g["tz"], g["home_tz"]
    home = g["home"] or TODO
    flights = _flight_rows(g)
    stops = g["stops"]
    keys = {}
    for s in stops:
        k = key_of(s["name"])
        while k in keys.values():
            k += "x"
        keys[s["name"]] = k
    first, last = (flights[0] if flights else None), (flights[-1] if flights else None)
    depart = f"{d0}T{first['dep'] if first else '00:00'}:00{_offset(htz, str(d0))}"
    back = f"{d1}T{last['arr'] if last and last['to'] == home else '23:59'}:00{_offset(htz, str(d1))}"
    stays = {}
    for s in stops:
        cand = (s.get("stays") or [{}])[0]
        stays[keys[s["name"]]] = {
            "name": cand.get("name") or f"{TODO} stay in {s['name']}", "sub": f"{s['name']} · {s.get('nights', '?')} nights",
            "st": "open", "ref": "", "book": cand.get("url") or "", "site": "Listing" if cand.get("url") else "",
            "pics": 0, "addr": "", "q": s.get("stay_area") or s["name"], "th": f"{TODO} address in the local script",
            "cap": f"{s['name']}, {s.get('checkin', '')} to {s.get('checkout', '')}"}
    events, days = [], []
    for f in flights:
        ftz = htz if f["from"] == home else tz
        events.append({"t": f"{f['date']}T{f['dep']}:00{_offset(ftz, f['date'], f['dep'])}", "kind": "fly",
                       "from": f["from"], "to": f["to"], "fc": f["fc"], "tc": f["tc"], "name": f["name"],
                       "dep": f["dep"], "arr": f["arr"], "st": "open", "note": f"{TODO} terminal, baggage, be-there-by"})
    for s in stops:
        if s.get("checkin"):
            events.append({"t": f"{s['checkin']}T14:00:00{_offset(tz, s['checkin'])}", "kind": "stay", "place": s["name"],
                           "until": f"{s.get('checkout')}T11:00:00{_offset(tz, s.get('checkout') or s['checkin'])}",
                           "name": stays[keys[s["name"]]]["name"], "st": "open", "note": f"{TODO} check-in and out times"})
    events.sort(key=lambda e: e["t"])
    day = d0
    while day <= d1:
        ds = day.isoformat()
        here = next((s for s in stops if s.get("checkin") and s["checkin"] <= ds < s["checkout"]), None)
        d = {"go": [], "d": str(day.day), "w": day.strftime("%a"), "where": here["name"] if here else
             f"{stops[-1]['name'] if stops else TODO} → {g['home_city'] or home}",
             "h": f"{TODO} headline", "p": f"{TODO} one paragraph: when to leave, what it costs, where to eat"}
        if here:
            d["sleep"] = keys[here["name"]]
        else:
            d["city"] = stops[-1]["name"] if stops else ""
            d["sleepNote"] = "Home"
        mv = [{"kind": "fly", "from": f["from"], "to": f["to"], "dep": f["dep"], "arr": f["arr"], "name": f["name"],
               "st": "open", "ref": "", "sub": f"{TODO} terminal · be there by", "q": f"{f['from']} airport"}
              for f in flights if f["date"] == ds]
        for lg in g["legs"]:
            if lg.get("kind") == "ground" and lg.get("date") == ds and not lg.get("alt"):
                gr = lg.get("ground") or {}
                hrs = gr.get("hours") or []
                mv.append({"kind": "taxi", "name": f"{gr.get('mode', 'road').title()}, {lg.get('orig')} to {lg.get('dest')}",
                           "sub": (f"about {hrs[0]}–{hrs[1]} h · " if len(hrs) == 2 else "") + f"{TODO} fare and how to book",
                           "st": "open", "q": str(lg.get("dest") or "")})
        if mv:
            d["move"] = mv
        days.append(d)
        day += dt.timedelta(days=1)
    tagline = f"{stops[0]['name']} first. {stops[-1]['name']} last." if len(stops) > 1 else (stops[0]["name"] if stops else TODO)
    airports = {f[k]: f"{f[k]} airport" for f in flights for k in ("from", "to")}
    trip = {
        "title": g["title"] or f"{TODO} title", "dates": f"{d0.day} {d0:%b} – {d1.day} {d1:%b}",
        "tagline": tagline, "hello": "Hello",
        "tz": tz or "UTC", "tzLabel": (tz.split("/")[-1][:3].upper() if tz else f"{TODO} label"),
        "homeTz": htz or "UTC", "homeLabel": "HOME", "day0": str(d0), "depart": depart, "back": back,
        "planned": dt.date.today().isoformat(), "home": {"code": home, "city": g["home_city"] or home},
        "airports": airports,
        "cur": {"here": g["cur_here"] or TODO, "home": g["cur_home"] or TODO, "symHere": (g["cur_here"] or "") + " ",
                "symHome": (g["cur_home"] or "") + " ", "locale": "en-GB", "rate": g["rate"] or 1, "quick": [10, 20, 50, 100, 200]},
        "people": _initials(g["people"], g["n_people"]),
        "voice": {"lang": g["voice"].get("lang") or "en", "name": g["voice"].get("name") or f"{TODO} language"},
        "cities": [{"n": s["name"], "la": s.get("lat", 0.0), "lo": s.get("lon", 0.0),
                    "typ": f"{TODO} typical weather" + ("" if "lat" in s else "; TODO coordinates")} for s in stops],
        "cover": "", "budget": {"each": 0, "lines": [], "note": f"{TODO} expected spend per person"},
        "defaultTheme": g["theme"], "ledgerKey": f"{key_of(g['title'] or 'trip')}-ledger-cache"}
    head = ("/* ---------- trip data, written by `tripforge site init` from brief.yaml + plan.json ----------\n"
            "   Edit by hand from here on. Values the inputs did not give are marked as todos; refs stay empty until booked.\n"
            "   Field reference: site_template/README.md */\n")
    ex = (template_dir() / "src/js/03-data-trip.example.js").read_text()
    helpers = ex[ex.index("const I="):ex.index("const EVENTS=")]
    helpers = re.sub(r"const ICAO=\{[^}]*\};", "const ICAO={};  // 2-letter airline -> FlightAware 3-letter, add as needed", helpers)
    return (head + f"const TRIP={_js(trip)};\n\n" + helpers + f"const EVENTS={_js(events)};\nconst CRED={{}};\n"
            f"const STAYS={_js(stays)};\nconst DAYS={_js(days)};\n")


def kit_js() -> str:
    kit = {"airportCard": {"cap": "Airports", "say": []}, "sos": [[f"{TODO} police", "", "000"]], "hospitals": [],
           "fares": {"unit": "", "rows": [], "note": ""}, "bookings": [], "tips": [], "foot": ""}
    return ("/* ---------- kit data, written by `tripforge site init`. Fill from the destination's guides. ---------- */\n"
            f"const PHRASES=[];\nconst TODO=[{_js(TODO + ' entry rules and deadlines for this trip')}];\n"
            f"const PACK=[];\nconst KIT={_js(kit)};\n")


def fill_tokens(root: Path, g: dict, trip_dates: str) -> None:
    base = "/" + (g["base"] or key_of(g["title"] or "trip")).strip("/") + "/"
    cities = " · ".join(s["name"] for s in g["stops"])
    for rel in ("src/index.html", "lock/index.html", "manifest.webmanifest"):
        p = root / rel
        if p.exists():
            p.write_text(p.read_text().replace("__BASE__", base).replace("__TITLE__", g["title"] or TODO)
                         .replace("__DATES__", trip_dates).replace("__CITIES__", cities))


def init(dst: Path, brief: dict, plan: dict, force: bool = False) -> list[str]:
    """Copy the template to dst and write the trip modules. Returns the TODO lines left to fill."""
    tpl = template_dir()
    if dst.exists() and any(dst.iterdir()) and not force:
        raise SiteError(f"{dst} is not empty (use --force to overwrite the template files)")
    shutil.copytree(tpl, dst, dirs_exist_ok=True, ignore=lambda d, names: [n for n in names if n == "__pycache__"
                                                                             or (Path(d) == tpl and n in SKIP_ROOT)])
    g = gather(brief, plan)
    js = dst / "src" / "js"
    trip = trip_js(g)
    (js / "03-data-trip.js").write_text(trip)
    (js / "04-data-kit.js").write_text(kit_js())
    m = re.search(r'"dates":\s*"([^"]*)"', trip)
    fill_tokens(dst, g, m.group(1) if m else "")
    (dst / "data").mkdir(exist_ok=True)
    return todos(dst)


def todos(root: Path) -> list[str]:
    out = []
    for n in ("03-data-trip.js", "04-data-kit.js"):
        p = root / "src" / "js" / n
        if p.exists():
            out += [f"{n}: {m}" for m in re.findall(r"TODO[ :][^\"',;]*", p.read_text())]
    return out


def run_build(root: Path, check: bool = False) -> tuple[int, str]:
    tool = root / "tools" / "build.py"
    if not tool.exists():
        raise SiteError(f"{tool} not found; is {root} a site made by `tripforge site init`?")
    r = subprocess.run([sys.executable, str(tool), "--site", str(root), *(["--check"] if check else [])],
                       capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip()


def privacy_hits(root: Path, patterns: list[str]) -> list[str]:
    hits = []
    files = [root / "index.html", *sorted((root / "data").glob("*.json"))]
    rx = [re.compile(p, re.I) for p in [*ALWAYS_PRIVATE, *patterns]]
    for f in files:
        if not f.exists():
            continue
        for i, line in enumerate(f.read_text(errors="ignore").splitlines(), 1):
            for r in rx:
                m = r.search(line)
                if m:
                    hits.append(f"{f.relative_to(root)}:{i}: {m.group(0)!r} (pattern {r.pattern!r})")
    return hits


def find_brief(root: Path, given: Path | None) -> Path | None:
    for p in ([given] if given else [root / "brief.yaml", root.parent / "brief.yaml"]):
        if p and p.exists():
            return p
    return None
