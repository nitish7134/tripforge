"""Multi-traveller flight plan: per-person legs, rule checks and a best-option pick.

`data.flightPlan` in trip.json holds candidate options (each a set of legs, one per traveller and direction) and the
rules every option is checked against. Nothing here knows a city, airline or traveller; see SCHEMA.md for the shape.

Rule types (`leg` / `than` / `legs` are leg `role` names inside one option):
  not_earlier   {leg, than}              arrival of `leg` is at or after arrival of `than`
  within        {legs:[a,b], minutes}    arrivals are at most `minutes` apart
  arrive_before {leg, time:"HH:MM"}      lands the day it departs, before `time` local (leg's arrival offset)
  arrive_on     {leg, date:"YYYY-MM-DD"} local arrival date equals `date` (same-day return)
  max_fare      {max, label?}           every leg's per-person fare (price / pax, pax default 1) is at most `max`; each leg gets
                                         `cap: {ok, headroom}` and an option breaking it is marked `over` (shown greyed, never recommended)
A rule with `"soft": true` shows as a warning and never fails an option. A rule naming a role the option lacks is skipped.
"""
from __future__ import annotations

from datetime import datetime


def _t(s: str) -> datetime:
    return datetime.fromisoformat(s)


def _gap_min(a: datetime, b: datetime) -> int:
    return round((a - b).total_seconds() / 60)


def _fmt_gap(m: int) -> str:
    m = abs(m)
    return f"{m // 60}h {m % 60:02d}m" if m >= 60 else f"{m}m"


def _per_person(l: dict) -> float | None:
    return None if l.get("price") is None else l["price"] / (l.get("pax") or 1)


def _cap(rule: dict, legs: list[dict]) -> dict:
    mx = float(rule["max"])
    over = [l for l in legs if (_per_person(l) or 0) > mx]
    priced = [l for l in legs if _per_person(l) is not None]
    if over:
        return {"ok": False, "detail": "over: " + ", ".join(f"{l.get('flight', '?')} {round(_per_person(l)):,}" for l in over)}
    if not priced:
        return {"ok": False, "detail": "no fares to check"}
    tight = min(priced, key=lambda l: mx - _per_person(l))
    return {"ok": True, "detail": f"tightest {tight.get('flight', '?')}, {round(mx - _per_person(tight)):,} under"}


def _check(rule: dict, legs: dict[str, dict]) -> dict | None:
    typ = rule.get("type")
    names = [rule[k] for k in ("leg", "than") if k in rule] + list(rule.get("legs", []))
    if any(n not in legs for n in names):
        return None
    arr = lambda n: _t(legs[n]["arr"])  # noqa: E731
    if typ == "not_earlier":
        gap = _gap_min(arr(rule["leg"]), arr(rule["than"]))
        return {"ok": gap >= 0, "detail": f"{_fmt_gap(gap)} {'after' if gap >= 0 else 'BEFORE'}"}
    if typ == "within":
        a, b = rule["legs"]
        gap = abs(_gap_min(arr(a), arr(b)))
        return {"ok": gap <= int(rule["minutes"]), "detail": f"{_fmt_gap(gap)} apart"}
    if typ == "arrive_before":
        a = arr(rule["leg"])
        hh, mm = (int(x) for x in rule["time"].split(":"))
        ok = a.date() == _t(legs[rule["leg"]]["dep"]).date() and (a.hour, a.minute) < (hh, mm)  # past midnight is never "before"
        return {"ok": ok, "detail": f"lands {a:%H:%M}"}
    if typ == "arrive_on":
        a = arr(rule["leg"])
        return {"ok": a.date().isoformat() == rule["date"], "detail": f"lands {a:%a %-d %b %H:%M}"}
    raise ValueError(f"unknown flightPlan rule type: {typ!r}")


def _local(iso: str, ref_date: str | None = None) -> str:
    t = _t(iso)
    s = f"{t:%H:%M}"
    return s + (f" +{(t.date() - _t(ref_date).date()).days}d" if ref_date and t.date() > _t(ref_date).date() else "")


def evaluate(plan: dict) -> dict:
    """Return the plan with per-option results, display strings and `best` (fewest hard failures, then cheapest)."""
    plan = dict(plan)
    rules = plan.get("rules", [])
    opts = []
    for o in plan.get("options", []):
        o = dict(o)
        legs = {l["role"]: l for l in o.get("legs", [])}
        res = []
        caps = [r for r in rules if r.get("type") == "max_fare"]
        for r in rules:
            c = _cap(r, o.get("legs", [])) if r.get("type") == "max_fare" else _check(r, legs)
            if c is None:
                continue
            soft = bool(r.get("soft"))
            res.append({"label": r.get("label") or r["type"], "ok": c["ok"], "soft": soft, "detail": c["detail"]})
        o["legs"] = [{**l, "depL": _local(l["dep"]), "arrL": _local(l["arr"], l["dep"]),
                      **({"cap": {"ok": _per_person(l) <= min(float(c["max"]) for c in caps), "headroom": round(min(float(c["max"]) for c in caps) - _per_person(l))}}
                         if caps and _per_person(l) is not None else {})} for l in o.get("legs", [])]
        o["over"] = any(l.get("cap", {}).get("ok") is False for l in o["legs"])
        o["results"] = res
        o["fails"] = sum(1 for x in res if not x["ok"] and not x["soft"])
        o["warns"] = sum(1 for x in res if not x["ok"] and x["soft"])
        o["total"] = sum(l.get("price") or 0 for l in o.get("legs", []))
        o["ok"] = o["fails"] == 0
        opts.append(o)
    plan["options"] = opts
    if opts and plan.get("best") not in {o["id"] for o in opts if not o["over"]}:   # an author-chosen `best` wins; otherwise fewest hard failures, then cheapest
        plan["best"] = min(opts, key=lambda o: (o["fails"], o["warns"], o["total"]))["id"]
    return plan


def problems(plan: dict) -> list[str]:
    """Deploy-gate messages: every option marked `recommended` must pass its hard rules."""
    out = []
    for o in evaluate(plan).get("options", []):
        if o.get("recommended") or o.get("id") == plan.get("chosen"):
            out += [f"flight option '{o['id']}' breaks rule '{x['label']}' ({x['detail']})" for x in o["results"] if not x["ok"] and not x["soft"]]
    return out
