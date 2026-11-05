#!/usr/bin/env python3
"""Merge per-city research JSONs into data/plans.json (the day plans the page fetches without a redeploy).

Usage: merge_plans.py RESEARCH_DIR [--bbox S,W,N,E] [--private FILE] [--diet-label TEXT] [--note TEXT] [--out PATH]

Reads every RESEARCH_DIR/*.json (sorted; one file per city, shape in site_template/README.md), validates each
option, drops anything without coordinates (or outside --bbox when given) and every non-https link, and writes
plans.json keyed by ISO date. --private names a file with one regex per line (the trip's names, refs, PINs); a
match anywhere in the output aborts the write. A passport-number shape is always checked.
"""
import argparse
import datetime
import json
import pathlib
import re
import sys

SITE = pathlib.Path(__file__).resolve().parent.parent
KINDS = {'party', 'food', 'sea', 'sight', 'market', 'chill', 'move'}
WHEN = ['morning', 'afternoon', 'sunset', 'dinner', 'night', 'late']
ALWAYS_PRIVATE = [r'\b[A-Z][0-9]{7}\b', r'passport (no|number)']


def clip(s, n=170):
    s = (s or '').strip()
    return s if len(s) <= n else s[:n - 1].rstrip() + '…'


def clean_opt(o, warn, bbox=None):
    if o.get('kind') not in KINDS:
        o['kind'] = 'sight'
    try:
        la, lo = float(o['lat']), float(o['lon'])
    except (KeyError, TypeError, ValueError):
        warn.append(f"drop (no coords): {o.get('name')}")
        return None
    if bbox and not (bbox[0] < la < bbox[2] and bbox[1] < lo < bbox[3]):
        warn.append(f"drop (coords outside bbox): {o.get('name')}")
        return None
    seen, links = set(), []
    for l in o.get('links', []):
        if isinstance(l, dict) and str(l.get('u', '')).startswith('https://') and l['u'] not in seen:
            seen.add(l['u'])
            links.append({'t': l.get('t', 'Link'), 'u': l['u']})
    out = {'n': clip(o.get('name'), 80), 'k': o['kind'], 'why': clip(o.get('why')),
           'cost': clip(o.get('cost'), 90), 'hrs': clip(o.get('hours'), 70),
           'la': round(la, 4), 'lo': round(lo, 4), 'links': links[:4]}
    diet = o.get('diet') or o.get('veg')
    if diet:
        out['diet'] = clip(diet)
    return out


def merge(rdir, bbox=None, private=(), diet_label='Diet', note=None):
    """-> (plans dict, warnings). Raises ValueError on private data."""
    rdir = pathlib.Path(rdir)
    days, sources, warn, cities = {}, [], [], []
    files = sorted(rdir.glob('*.json'))
    if not files:
        warn.append(f'no research JSON in {rdir}')
    for p in files:
        d = json.loads(p.read_text())
        if 'days' not in d:
            warn.append(f'skip {p.name}: no "days"')
            continue
        cities.append(d.get('place', p.stem))
        sources += d.get('sources', [])
        for day in d['days']:
            date = day['date']
            datetime.date.fromisoformat(date)
            slots = []
            for s in day.get('slots', []):
                opts = [x for x in (clean_opt(o, warn, bbox) for o in s.get('options', [])) if x]
                if not opts:
                    continue
                w = s.get('when', '')
                slots.append({'w': w if w in WHEN else 'anytime', 'l': clip(s.get('label'), 70), 'o': opts[:3]})
            slots.sort(key=lambda s: WHEN.index(s['w']) if s['w'] in WHEN else 99)
            tips = [clip(t) for t in day.get('tips', [])][:5]
            if date in days:
                days[date]['slots'] += slots
                days[date]['tips'] += tips
            else:
                days[date] = {'title': clip(day.get('title'), 70), 'slots': slots, 'tips': tips}
    plans = {'updated': datetime.date.today().isoformat(), 'cities': cities, 'days': days,
             'sources': sorted(set(sources)), 'dietLabel': diet_label}
    if note:
        plans['note'] = note
    blob = json.dumps(plans, ensure_ascii=False)
    for pat in [*ALWAYS_PRIVATE, *private]:
        m = re.search(pat, blob, re.I)
        if m:
            raise ValueError(f'private data in plans: {m.group(0)!r}')
    return plans, warn


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('research_dir')
    ap.add_argument('--bbox', help='S,W,N,E; options outside are dropped')
    ap.add_argument('--private', help='file with one regex per line')
    ap.add_argument('--diet-label', default='Diet')
    ap.add_argument('--note', help='source line shown under each plan')
    ap.add_argument('--out', default=str(SITE / 'data' / 'plans.json'))
    a = ap.parse_args(argv)
    bbox = [float(x) for x in a.bbox.split(',')] if a.bbox else None
    private = [l.strip() for l in pathlib.Path(a.private).read_text().splitlines() if l.strip()] if a.private else []
    try:
        plans, warn = merge(a.research_dir, bbox, private, a.diet_label, a.note)
    except ValueError as e:
        sys.exit(str(e).upper())
    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(plans, ensure_ascii=False, separators=(',', ':')))
    n = sum(len(s['o']) for d in plans['days'].values() for s in d['slots'])
    print(f'wrote {out}: {len(plans["days"])} days, {n} options')
    for w in warn:
        print(' ', w)


if __name__ == '__main__':
    main()
