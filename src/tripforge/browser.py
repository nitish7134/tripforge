"""Browser abstraction: headless (python playwright + system Chrome) or attach (playwright-cli + your logged-in Chrome)."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")

NODE_BIN = os.environ.get("TRIPFORGE_NODE_BIN", "/opt/homebrew/opt/node@24/bin")
PWCLI = os.environ.get("TRIPFORGE_PWCLI") or shutil.which("playwright-cli") or str(
    Path.home() / ".kiro/crew/playwright-cli/bin/playwright-cli")
SLUG = os.environ.get("TRIPFORGE_SLUG", "tripforge")


class BrowserError(RuntimeError):
    pass


class HeadlessBrowser:
    mode = "headless"

    def __init__(self):
        self._pw = self._browser = self._ctx = self.page = None

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        last = None
        for kw in ({"channel": "chrome"}, {}):
            try:
                self._browser = self._pw.chromium.launch(headless=True, **kw)
                break
            except Exception as e:  # noqa: BLE001
                last = e
        if not self._browser:
            self._pw.stop()
            raise BrowserError(f"cannot launch Chrome/Chromium headless: {str(last)[:200]}")
        self._ctx = self._browser.new_context(user_agent=UA, locale="en-US",
                                              viewport={"width": 1400, "height": 1000})
        self.page = self._ctx.new_page()
        return self

    def __exit__(self, *a):
        try:
            self._browser.close()
        finally:
            self._pw.stop()

    def goto(self, url: str, wait_ms: int = 4000):
        self.page.goto(url, wait_until="domcontentloaded", timeout=45000)
        self.page.wait_for_timeout(wait_ms)

    def eval(self, js: str):
        return self.page.evaluate(js)

    def screenshot(self, path: Path) -> bool:
        try:
            self.page.screenshot(path=str(path), full_page=False)
            return True
        except Exception:  # noqa: BLE001
            return False


class AttachBrowser:
    """Drives your real Chrome through playwright-cli's extension relay (needs Node 24 on PATH)."""
    mode = "attach"

    def __init__(self):
        self.env = dict(os.environ)
        self.env["PATH"] = NODE_BIN + os.pathsep + self.env.get("PATH", "")
        self.env["PLAYWRIGHT_MCP_ISOLATED"] = "false"
        self._tab_open = False
        self.workdir = Path(os.environ.get("TMPDIR", "/tmp")) / "tripforge-attach"
        self.workdir.mkdir(parents=True, exist_ok=True)

    def _run(self, *args, timeout=90) -> str:
        r = subprocess.run([PWCLI, f"-s={SLUG}", *args], env=self.env, cwd=self.workdir,
                           capture_output=True, text=True, timeout=timeout)
        out = (r.stdout or "") + (r.stderr or "")
        if r.returncode != 0 or "### Error" in out:
            raise BrowserError(f"playwright-cli {args[0]} failed: {out.strip()[:300]}")
        return out

    def __enter__(self):
        out = self._run("attach", "--extension=chrome")
        if "attached" not in out.lower():
            raise BrowserError("could not attach to Chrome: " + out[:300])
        return self

    def __exit__(self, *a):
        try:
            if self._tab_open:
                self._run("tab-close")
            self._run("detach")
        except Exception:  # noqa: BLE001
            pass

    def goto(self, url: str, wait_ms: int = 4000):
        import time
        if not self._tab_open:
            self._run("tab-new", url)
            self._tab_open = True
        else:
            self._run("goto", url)
        time.sleep(wait_ms / 1000)

    def eval(self, js: str):
        wrapped = f"async () => JSON.stringify(await ({js})())"
        out = self._run("eval", wrapped, timeout=180)
        m = re.search(r"### Result\n(.*?)\n### ", out + "\n### ", re.S)
        if not m:
            raise BrowserError("no result from eval: " + out[:300])
        val = json.loads(m.group(1).strip())  # JSON string literal
        return json.loads(val) if isinstance(val, str) else val

    def screenshot(self, path: Path) -> bool:
        try:
            out = self._run("screenshot")
            m = re.search(r"\(([^)\n]+\.(?:png|jpe?g))\)", out)
            if not m:
                return False
            src = Path(m.group(1))
            if not src.is_absolute():
                src = (self.workdir / src).resolve()
            shutil.copyfile(src, path)
            return True
        except Exception:  # noqa: BLE001
            return False


def make_browser(mode: str):
    if mode == "attach":
        return AttachBrowser()
    if mode == "headless":
        return HeadlessBrowser()
    raise BrowserError(f"unknown browser mode {mode!r}")
