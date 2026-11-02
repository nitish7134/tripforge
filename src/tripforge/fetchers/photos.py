"""Wikimedia Commons photo fetcher (keyless). Resized, cached to disk, attribution kept."""
from __future__ import annotations

import base64
import hashlib
import io
import re
from pathlib import Path

from PIL import Image

from .common import Result, client, fail

API = "https://commons.wikimedia.org/w/api.php"
BAD = re.compile(r"map|flag|logo|coat|diagram|locator|panorama of the|svg|screenshot|poster", re.I)


def fetch_photos(query: str, n: int, cache: Path) -> Result:
    params = {"action": "query", "generator": "search", "gsrsearch": f"{query} filetype:bitmap",
              "gsrnamespace": 6, "gsrlimit": 30, "prop": "imageinfo", "iiprop": "url|size|extmetadata",
              "iiurlwidth": 1200, "format": "json"}
    try:
        with client(30) as c:
            j = c.get(API, params=params).json()
            pages = sorted(j.get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 99))
            got = []
            for p in pages:
                ii = (p.get("imageinfo") or [{}])[0]
                title = p.get("title", "")
                if BAD.search(title) or not title.lower().endswith((".jpg", ".jpeg")):
                    continue
                if ii.get("width", 0) < 1400 or ii.get("width", 0) < ii.get("height", 1) * 1.2:
                    continue
                thumb = ii.get("thumburl")
                if not thumb:
                    continue
                key = hashlib.md5(thumb.encode()).hexdigest()[:12]
                f = cache / f"{key}.jpg"
                if not f.exists():
                    raw = c.get(thumb).content
                    im = Image.open(io.BytesIO(raw)).convert("RGB")
                    im.thumbnail((1200, 1200))
                    im.save(f, "JPEG", quality=76)
                md = ii.get("extmetadata", {})
                artist = re.sub(r"<[^>]+>", "", md.get("Artist", {}).get("value", "unknown")).strip()
                lic = md.get("LicenseShortName", {}).get("value", "")
                got.append({"b64": base64.b64encode(f.read_bytes()).decode(), "title": title,
                            "credit": f"{artist}, {lic}".strip(", "), "page": ii.get("descriptionurl", "")})
                if len(got) >= n:
                    break
        return Result(ok=bool(got), data=got, source_url=f"{API}?gsrsearch={query}",
                      error=None if got else "no suitable photos found")
    except Exception as e:  # noqa: BLE001
        return fail(str(e), API)
