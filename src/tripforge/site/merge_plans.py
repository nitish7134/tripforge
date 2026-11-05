#!/usr/bin/env python3
"""Merge research JSONs (agents/RESEARCH_BRIEF.md schema) into site/data/plans.json keyed by ISO date.

Usage: tripforge site merge-plans trips/<slug>   (reads trips/<slug>/research/*.json)
Validates every option, drops anything without coordinates inside the trip's bounding box or without an https link,
and refuses private data. The bounding box comes from trip.json data.cities (padded) or from trip.bbox.
"""
import datetime
import json
import pathlib
import re

KINDS = {'party', 'food', 'sea', 'sight', 'market', 'chill', 'move'}
WHEN = ['morning', 'afternoon', 'sunset', 'dinner', 'night', 'late']
PRIVATE = re.compile(r'\b([A-Z][0-9]{7}|passport (no|number))\b')


def clip(s, n=170):
    s = (s or '').strip()
    return s if len(s) <= n else s[:n - 1].rstrip() + '…'


def bbox_from(cfg):
    t = cfg['trip']
    if t.get('bbox'):
        return t['bbox']
    pts = cfg.get('data', {}).get('cities') or []
    if not pts:
        return None
    las = [p[1] for p in pts]; los = [p[2] for p in pts]
    return [min(las) - 1.5, max(las) + 1.5, min(los) - 1.5, max(los) + 1.5]


def clean_opt(o, warn, bbox, extra_private):
    if o.get('kind') not in KINDS:
        o['kind'] = 'sight'
    try:
        la, lo = float(o['lat']), float(o['lon'])
    except (KeyError, TypeError, ValueError):
        warn.append(f"drop (no coords): {o.get('name')}")
        return None
    if bbox and not (bbox[0] < la < bbox[1] and bbox[2] < lo < bbox[3]):
        warn.append(f"drop (coords outside trip area): {o.get('name')}")
        return None
    links = [{'t': l.get('t', 'Link'), 'u': l['u']} for l in o.get('links', []) if isinstance(l, dict) and str(l.get('u', '')).startswith('https://')]
    seen, uniq = set(), []
    for l in links:
        if l['u'] not in seen:
            seen.add(l['u']); uniq.append(l)
    out = {'n': clip(o.get('name'), 80), 'k': o['kind'], 'why': clip(o.get('why')), 'cost': clip(o.get('cost'), 90), 'hrs': clip(o.get('hours'), 70),
           'la': round(la, 4), 'lo': round(lo, 4), 'links': uniq[:4]}
    if o.get('veg'):
        out['veg'] = clip(o['veg'])
    blob = json.dumps(out, ensure_ascii=False)
    if PRIVATE.search(blob) or any(re.search(p, blob) for p in extra_private):
        raise SystemExit(f'private data in research option {out["n"]!r}; fix the source file')
    return out


def merge(trip_dir: pathlib.Path) -> pathlib.Path:
    cfg = json.loads((trip_dir / 'site' / 'trip.json').read_text())
    bbox = bbox_from(cfg); extra = cfg.get('private_patterns', [])
    days, sources, warn, places = {}, [], [], []
    for p in sorted((trip_dir / 'research').glob('*.json')):
        d = json.loads(p.read_text())
        if 'days' not in d:
            continue
        places.append(d.get('place', p.stem)); sources += d.get('sources', [])
        for day in d['days']:
            date = day['date']; datetime.date.fromisoformat(date)
            dst = days.setdefault(date, {'title': clip(day.get('title'), 60), 'slots': [], 'tips': []})
            for s in day.get('slots', []):
                opts = [x for x in (clean_opt(o, warn, bbox, extra) for o in s.get('options', [])) if x]
                if opts:
                    dst['slots'].append({'w': s.get('when') if s.get('when') in WHEN else 'anytime', 'l': clip(s.get('label'), 60), 'o': opts})
            dst['tips'] += [clip(t, 200) for t in day.get('tips', [])][:5]
    for d in days.values():
        d['slots'].sort(key=lambda s: WHEN.index(s['w']) if s['w'] in WHEN else 9)
    out = trip_dir / 'site' / 'data' / 'plans.json'; out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({'updated': datetime.date.today().isoformat(), 'cities': places, 'days': days}, ensure_ascii=False, separators=(',', ':')))
    n = sum(len(s['o']) for d in days.values() for s in d['slots'])
    print(f'wrote {out}: {len(days)} days, {n} options, {out.stat().st_size // 1024} KB')
    for w in warn:
        print('  ', w)
    return out
