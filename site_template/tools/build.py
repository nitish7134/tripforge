#!/usr/bin/env python3
"""Build index.html from src/: shell + concatenated CSS + concatenated JS, in src/ORDER.txt order.

Usage: tools/build.py [--check] [--site DIR]
  --check  build in memory and fail if index.html differs from a fresh build (no write)
  --site   site root (default: the parent of this tools/ directory)
A name in ORDER.txt resolves to NAME.css / NAME.js, else NAME.example.js (so the bare template builds).
The inlined script must pass `node --check` (node from $NODE, else PATH); without node the build fails
unless TRIPFORGE_SKIP_NODE=1. Single-file output is deliberate: one request, offline through the service
worker on day one, trivial to host. Never hand-edit the built index.html: edit src/ and rebuild.
"""
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile


def order(src):
    sec, out = None, {'css': [], 'js': []}
    for l in (src / 'ORDER.txt').read_text().splitlines():
        l = l.strip()
        if not l or l.startswith('#'):
            continue
        if l in ('[css]', '[js]'):
            sec = l[1:-1]
            continue
        out[sec].append(l)
    return out


def module(src, kind, name):
    sub = 'styles' if kind == 'css' else 'js'
    for cand in (src / sub / f'{name}.{kind}', src / sub / f'{name}.example.{kind}'):
        if cand.exists():
            return cand.read_text()
    raise SystemExit(f'missing module: {sub}/{name}.{kind}')


def build(site):
    src = site / 'src'
    o = order(src)
    css = ''.join(module(src, 'css', n) for n in o['css'])
    js = ''.join(module(src, 'js', n) for n in o['js'])
    shell = (src / 'index.html').read_text()
    if shell.count('<!-- @css -->') != 1 or shell.count('<!-- @js -->') != 1:
        raise SystemExit('src/index.html needs exactly one <!-- @css --> and one <!-- @js --> slot')
    return (shell.replace('<!-- @css -->', '<style>\n' + css.rstrip('\n') + '\n</style>')
            .replace('<!-- @js -->', '<script>\n' + js.rstrip('\n') + '\n</script>'))


def syntax_ok(js_text):
    node = os.environ.get('NODE') or shutil.which('node')
    if not node:
        if os.environ.get('TRIPFORGE_SKIP_NODE') == '1':
            print('warning: node not found, JS syntax not checked')
            return True
        print('node not found: install node or set NODE=/path/to/node (TRIPFORGE_SKIP_NODE=1 to skip)')
        return False
    with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False) as f:
        f.write(js_text)
    try:
        r = subprocess.run([node, '--check', f.name], capture_output=True, text=True)
    finally:
        os.unlink(f.name)
    if r.returncode:
        print(r.stderr)
    return r.returncode == 0


def main(argv):
    site = pathlib.Path(argv[argv.index('--site') + 1]).resolve() if '--site' in argv else pathlib.Path(__file__).resolve().parent.parent
    html = build(site)
    js = '\n'.join(re.findall(r'<script>(.*?)</script>', html, re.S))
    if not syntax_ok(js):
        return 'JS syntax error in src/js; not writing index.html'
    out = site / 'index.html'
    if '--check' in argv:
        cur = out.read_text() if out.exists() else ''
        return 0 if cur == html else 'index.html differs from a fresh build (run tools/build.py)'
    out.write_text(html)
    o = order(site / 'src')
    print(f'built index.html: {len(html)//1024} KB, {len(o["css"])} css + {len(o["js"])} js modules')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
