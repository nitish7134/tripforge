"""sqlite TTL cache for fetcher Results, keyed by (fetcher, params-hash).

Every cached row keeps the original `fetched_at`, so a plan built from cache still prints when the
price was actually read ("fetched 2 Nov 15:40"). Failed results are never cached.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Callable

from .fetchers.common import Result

HOUR = 3600
TTL = {"flights": 8 * HOUR, "stays": 24 * HOUR, "places": 7 * 24 * HOUR, "climate": 7 * 24 * HOUR,
       "fx": 24 * HOUR, "ground": 7 * 24 * HOUR, "geo": 30 * 24 * HOUR, "visa": 30 * 24 * HOUR, "community": 24 * HOUR}

_lock = threading.Lock()
_state = {"enabled": True, "path": None, "hits": 0, "misses": 0}


def repo_root() -> Path:
    """Directory holding trips/ and cache/: $TRIPFORGE_HOME, else the nearest ancestor of CWD with a
    pyproject.toml naming tripforge, else the source checkout this package was installed from, else CWD."""
    env = os.environ.get("TRIPFORGE_HOME")
    if env:
        return Path(env).expanduser().resolve()
    for d in [Path.cwd(), *Path.cwd().parents]:
        pp = d / "pyproject.toml"
        if pp.exists() and 'name = "tripforge"' in pp.read_text(errors="ignore"):
            return d
    src = Path(__file__).resolve().parents[2]
    if (src / "pyproject.toml").exists():
        return src
    return Path.cwd()


def configure(enabled: bool = True, path: Path | None = None) -> None:
    _state["enabled"] = enabled
    _state["path"] = path


def _db() -> sqlite3.Connection:
    p = _state["path"] or (repo_root() / "cache" / "tripforge.db")
    p.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(p, timeout=30)
    c.execute("CREATE TABLE IF NOT EXISTS results (fetcher TEXT, key TEXT, params TEXT, fetched_at REAL,"
              " payload TEXT, PRIMARY KEY (fetcher, key))")
    return c


def key_of(params: dict) -> str:
    return hashlib.sha256(json.dumps(params, sort_keys=True, default=str).encode()).hexdigest()[:24]


def get(fetcher: str, params: dict, ttl: int | None = None) -> Result | None:
    if not _state["enabled"]:
        return None
    ttl = TTL.get(fetcher.split(":")[0], 24 * HOUR) if ttl is None else ttl
    with _lock, _db() as c:
        row = c.execute("SELECT fetched_at, payload FROM results WHERE fetcher=? AND key=?",
                        (fetcher, key_of(params))).fetchone()
    if not row or time.time() - row[0] > ttl:
        return None
    d = json.loads(row[1])
    r = Result(**{k: d.get(k) for k in ("ok", "data", "source_url", "fetched_at", "screenshot_path", "error")})
    r.cached = True  # type: ignore[attr-defined]
    return r


def put(fetcher: str, params: dict, r: Result) -> None:
    if not r.ok:
        return
    with _lock, _db() as c:
        c.execute("INSERT OR REPLACE INTO results VALUES (?,?,?,?,?)",
                  (fetcher, key_of(params), json.dumps(params, sort_keys=True, default=str), r.fetched_at,
                   json.dumps(r.to_dict(), default=str, ensure_ascii=False)))


def cached(fetcher: str, params: dict, fn: Callable[[], Result], ttl: int | None = None) -> Result:
    """Return a fresh-enough cached Result or call fn(), caching it when ok."""
    hit = get(fetcher, params, ttl)
    if hit is not None:
        _state["hits"] += 1
        return hit
    _state["misses"] += 1
    r = fn()
    if _state["enabled"]:
        put(fetcher, params, r)
    return r


def stats() -> dict:
    return {"hits": _state["hits"], "misses": _state["misses"], "enabled": _state["enabled"]}
