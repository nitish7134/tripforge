#!/usr/bin/env python3
"""flightwatch: fetch live status for the trip's flights and write data/flights.json for the trip page.

Runs from a systemd timer every 10 min. Only polls a flight from 48 h before its scheduled departure to
6 h after, so the free API quota is spent when it matters. Sources, in order:
  1. AeroDataBox (RapidAPI, free tier) when RAPIDAPI_KEY is set in /etc/flightwatch.env: scheduled/revised
     times, status, terminal, gate, baggage belt.
  2. adsb.lol by callsign (keyless): confirms the aircraft is airborne and its position; no gate/belt.
Nothing personal is read or written. Output is public, like the page.
"""
import json, os, sys, time, urllib.request, urllib.parse
from datetime import datetime, timedelta, timezone

# Config: flightwatch.py /etc/flightwatch/<trip>.json
#   {"out": "/var/www/<trip>/data/flights.json", "flights": [{"id","dep","from","to","icao"}, ...]}
if len(sys.argv) < 2:
    sys.exit("usage: flightwatch.py <config.json>")
_cfg = json.load(open(sys.argv[1]))
OUT, FLIGHTS = _cfg["out"], _cfg["flights"]
KEY = os.environ.get("RAPIDAPI_KEY", "").strip()
NOW = datetime.now(timezone.utc)

def get(url, headers=None, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "tripforge-flightwatch/1", **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)

def hm(iso):
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%H:%M")
    except Exception:
        return None

def aerodatabox(f):
    date = f["dep"][:10]
    url = f"https://aerodatabox.p.rapidapi.com/flights/number/{f['id']}/{date}?withAircraftImage=false&withLocation=false"
    data = get(url, {"X-RapidAPI-Key": KEY, "X-RapidAPI-Host": "aerodatabox.p.rapidapi.com"})
    leg = next((x for x in data if (x.get("departure", {}).get("airport", {}).get("iata") == f["from"])), data[0] if data else None)
    if not leg:
        return None
    d, a = leg.get("departure", {}), leg.get("arrival", {})
    sched = d.get("scheduledTime", {}).get("local"); rev = d.get("revisedTime", {}).get("local") or d.get("runwayTime", {}).get("local")
    delay = None
    if sched and rev:
        delay = int((datetime.fromisoformat(rev) - datetime.fromisoformat(sched)).total_seconds() // 60)
    return {"status": leg.get("status"), "dep_sched": hm(sched), "dep_est": hm(rev or sched), "dep_delay_min": delay,
            "arr_est": hm(a.get("revisedTime", {}).get("local") or a.get("scheduledTime", {}).get("local")),
            "terminal": d.get("terminal"), "gate": d.get("gate"), "belt": a.get("baggageBelt"), "arr_terminal": a.get("terminal"),
            "source": "AeroDataBox"}

def adsb(f):
    data = get(f"https://api.adsb.lol/v2/callsign/{f['icao']}")
    ac = (data.get("ac") or [None])[0]
    if not ac:
        return {"status": "not airborne yet", "source": "adsb.lol"}
    return {"status": "airborne", "alt_ft": ac.get("alt_baro"), "speed_kt": ac.get("gs"), "lat": ac.get("lat"), "lon": ac.get("lon"), "source": "adsb.lol"}

out = {"generated": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"), "flights": {}}
try:
    prev = json.load(open(OUT))
    out["flights"] = prev.get("flights", {})
except Exception:
    pass

for f in FLIGHTS:
    dep = datetime.fromisoformat(f["dep"])
    if not (dep - timedelta(hours=48) <= NOW <= dep + timedelta(hours=6)):
        continue  # outside the window: keep whatever we had, spend no quota
    rec = {"id": f["id"], "updated": datetime.now(timezone(timedelta(hours=7))).strftime("%d %b %H:%M") + " BKK"}
    try:
        if KEY:
            got = aerodatabox(f)
            if got:
                rec.update(got)
        if "status" not in rec or rec.get("status") in (None, "Unknown"):
            rec.update(adsb(f))
    except Exception as e:  # noqa: BLE001
        rec["error"] = f"{type(e).__name__}: {str(e)[:80]}"
        rec.setdefault("status", "status unavailable")
    out["flights"][f["id"]] = rec

os.makedirs(os.path.dirname(OUT), exist_ok=True)
tmp = OUT + ".tmp"
json.dump(out, open(tmp, "w"), indent=1)
os.replace(tmp, OUT)
print("flightwatch wrote", OUT, "flights:", list(out["flights"]))
