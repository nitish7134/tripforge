from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any

import httpx

HEADERS = {"User-Agent": "tripforge/0.1 (personal trip planner; https://github.com/nitish7134/tripforge)"}


@dataclass
class Result:
    ok: bool
    data: Any = None
    source_url: str = ""
    fetched_at: float = field(default_factory=time.time)
    screenshot_path: str | None = None
    error: str | None = None

    def to_dict(self):
        return asdict(self)


def fail(msg: str, url: str = "") -> Result:
    return Result(ok=False, data=None, source_url=url, error=msg)


def client(timeout: float = 25.0) -> httpx.Client:
    return httpx.Client(headers=HEADERS, timeout=timeout, follow_redirects=True)


def save_json(path, obj):
    import json
    from pathlib import Path
    Path(path).write_text(json.dumps(obj, indent=1, ensure_ascii=False, default=str))
    return str(path)
