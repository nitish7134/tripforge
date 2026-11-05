#!/usr/bin/env python3
"""tripledger: PIN gate + shared expense ledger for the trip page. Loopback only; Caddy fronts it at <COOKIE_PATH>/api/.

Auth model
  POST /unlock {"pin": "...."}  -> compares against TRIP_PIN (constant time). On success sets an HttpOnly cookie
                                   trip=<TRIP_TOKEN> for COOKIE_PATH, valid a year. Wrong PIN -> 403. More than
                                   MAX_TRIES wrong answers from one IP in WINDOW seconds -> 429 for LOCKOUT seconds.
  everything else               -> requires cookie trip=<TRIP_TOKEN> (or header X-Trip-Key: <TRIP_TOKEN> for curl).
Caddy also checks the same cookie before serving any static file, so without the PIN nothing is visible.
Fail closed: if TRIP_PIN or TRIP_TOKEN is unset, every request is refused.
Ledger: GET /ledger, POST /ledger, PATCH /ledger/<id>, DELETE /ledger/<id>. JSON file, atomic writes,
initials + amounts only. Ids are any [A-Za-z0-9_-]{4,40}, so entries seeded by hand ("seed-flight-1") stay editable.

Configuration (env only; put it in an EnvironmentFile readable by root, never in the repo):
  TRIP_PIN, TRIP_TOKEN          member PIN and its cookie token (required)
  TRIP_PIN_RO, TRIP_TOKEN_RO    visitor PIN and token (optional; visitors cannot read or write the ledger)
  COOKIE_PATH                   URL prefix the page lives under, e.g. /my-trip (default /)
  LEDGER_PEOPLE                 payer initials, e.g. ASK (required for writes)
  LEDGER_CURRENCIES             comma list, e.g. EUR,USD (required for writes)
  LEDGER_PATH                   JSON file (default /var/lib/tripledger/ledger.json)
  LEDGER_PORT                   loopback port (default 8765)
"""
import hmac, json, os, re, time, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PIN = os.environ.get("TRIP_PIN", "").strip()
TOKEN = os.environ.get("TRIP_TOKEN", "").strip()
PIN_RO = os.environ.get("TRIP_PIN_RO", "").strip()      # visitor: read-only
TOKEN_RO = os.environ.get("TRIP_TOKEN_RO", "").strip()
PATH = os.environ.get("LEDGER_PATH", "/var/lib/tripledger/ledger.json")
COOKIE_PATH = "/" + os.environ.get("COOKIE_PATH", "/").strip("/")
PEOPLE = os.environ.get("LEDGER_PEOPLE", "").strip().upper()
CURRENCIES = tuple(c.strip().upper() for c in os.environ.get("LEDGER_CURRENCIES", "").split(",") if c.strip())
PORT = int(os.environ.get("LEDGER_PORT", "8765"))
MAX_BODY = 4096
MAX_TRIES, WINDOW, LOCKOUT = 6, 600, 600
tries = {}  # ip -> [timestamps]
CATS = ("travel", "stay", "food", "party", "leisure", "shopping", "other")
COOKIE_RE = re.compile(r"(?:^|;\s*)trip=([A-Za-z0-9_-]+)")


def load():
    try:
        return json.load(open(PATH))
    except Exception:
        return {"entries": []}


def save(d):
    tmp = PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(d, f, indent=1)
    os.replace(tmp, PATH)


def _fields(e, partial=None):
    """Validate an entry body. With partial (the stored entry), missing keys keep their old value."""
    g = lambda k, d=None: e[k] if k in e else (partial or {}).get(k, d)  # noqa: E731
    amt = float(g("amt")); who = str(g("who"))[:1].upper(); cur = str(g("cur", CURRENCIES[0] if CURRENCIES else "")).upper()
    what = re.sub(r"[^\w\s.,/&()+-]", "", str(g("what", "")))[:60]
    cat = str(g("cat", "other")).lower()
    if amt <= 0 or not who or who not in PEOPLE or cur not in CURRENCIES or cat not in CATS:
        raise ValueError("bad fields")
    return what, amt, cur, who, cat


class H(BaseHTTPRequestHandler):
    server_version = "tripledger/2"

    def _send(self, code, obj=None, extra=None):
        body = json.dumps(obj).encode() if obj is not None else b""
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _ip(self):
        return self.headers.get("X-Real-IP") or self.headers.get("X-Forwarded-For", "").split(",")[0].strip() or self.client_address[0]

    def _presented(self):
        m = COOKIE_RE.search(self.headers.get("Cookie", ""))
        return (m.group(1) if m else "") or self.headers.get("X-Trip-Key", "")

    def _role(self):
        t = self._presented().encode()
        if TOKEN and hmac.compare_digest(t, TOKEN.encode()):
            return "member"
        if TOKEN_RO and hmac.compare_digest(t, TOKEN_RO.encode()):
            return "visitor"
        return None

    def _auth(self, write=False):
        r = self._role()
        if r is None:
            self._send(403, {"error": "locked"})
            return False
        if write and r != "member":
            self._send(403, {"error": "read only"})
            return False
        return True

    def _body(self):
        n = int(self.headers.get("Content-Length", "0") or 0)
        if n <= 0 or n > MAX_BODY:
            raise ValueError("body size")
        return json.loads(self.rfile.read(n))

    def do_GET(self):
        p = self.path.rstrip("/")
        if p == "/me":
            r = self._role()
            return self._send(200, {"role": r}) if r else self._send(403, {"error": "locked"})
        if p != "/ledger":
            return self._send(404, {"error": "not found"})
        if not self._auth(write=True):
            return
        self._send(200, load())

    def do_POST(self):
        p = self.path.rstrip("/")
        if p == "/unlock":
            return self._unlock()
        if p == "/logout":
            return self._send(204, None, {"Set-Cookie": f"trip=; Path={COOKIE_PATH}; Max-Age=0; HttpOnly; Secure; SameSite=Lax"})
        if p != "/ledger":
            return self._send(404, {"error": "not found"})
        if not self._auth(write=True):
            return
        try:
            what, amt, cur, who, cat = _fields(self._body())
        except Exception as ex:  # noqa: BLE001
            return self._send(400, {"error": f"bad entry: {ex}"})
        d = load()
        entry = {"id": uuid.uuid4().hex[:10], "what": what, "amt": amt, "cur": cur, "who": who, "cat": cat, "ts": int(time.time() * 1000)}
        d["entries"].insert(0, entry)
        save(d)
        self._send(201, entry)

    def _unlock(self):
        ip, now = self._ip(), time.time()
        recent = [t for t in tries.get(ip, []) if now - t < WINDOW]
        tries[ip] = recent
        if len(recent) >= MAX_TRIES:
            wait = int(LOCKOUT - (now - recent[-1]))
            if wait > 0:
                return self._send(429, {"error": "too many tries", "retry": wait}, {"Retry-After": str(wait)})
            tries[ip] = []
        try:
            pin = str(self._body().get("pin", ""))[:12]
        except Exception:
            pin = ""
        time.sleep(0.4)  # slow down guessing
        tok = None
        if PIN and TOKEN and hmac.compare_digest(pin.encode(), PIN.encode()):
            tok = TOKEN
        elif PIN_RO and TOKEN_RO and hmac.compare_digest(pin.encode(), PIN_RO.encode()):
            tok = TOKEN_RO
        if tok is None:
            tries.setdefault(ip, []).append(now)
            left = MAX_TRIES - len(tries[ip])
            return self._send(403, {"error": "wrong pin", "left": max(left, 0)})
        tries.pop(ip, None)
        cookie = f"trip={tok}; Path={COOKIE_PATH}; Max-Age=31536000; HttpOnly; Secure; SameSite=Lax"
        self._send(204, None, {"Set-Cookie": cookie})

    def do_PATCH(self):
        m = re.fullmatch(r"/ledger/([A-Za-z0-9_-]{4,40})", self.path)
        if not m:
            return self._send(404, {"error": "not found"})
        if not self._auth(write=True):
            return
        d = load()
        cur = next((x for x in d["entries"] if x["id"] == m.group(1)), None)
        if not cur:
            return self._send(404, {"error": "no such entry"})
        try:
            what, amt, ccy, who, cat = _fields(self._body(), cur)
        except Exception as ex:  # noqa: BLE001
            return self._send(400, {"error": f"bad entry: {ex}"})
        cur.update({"what": what, "amt": amt, "cur": ccy, "who": who, "cat": cat, "edited": int(time.time() * 1000)})
        cur.pop("est", None)
        save(d)
        self._send(200, cur)

    def do_DELETE(self):
        m = re.fullmatch(r"/ledger/([A-Za-z0-9_-]{4,40})", self.path)
        if not m:
            return self._send(404, {"error": "not found"})
        if not self._auth(write=True):
            return
        d = load()
        before = len(d["entries"])
        d["entries"] = [x for x in d["entries"] if x["id"] != m.group(1)]
        if len(d["entries"]) != before:
            save(d)
        self._send(200, {"removed": before - len(d["entries"])})

    def log_message(self, fmt, *args):  # quiet; Caddy logs the edge
        pass


if __name__ == "__main__":
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    if not os.path.exists(PATH):
        save({"entries": []})
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
