"""Browserless Google Flights via fli (https://github.com/punitarani/fli).

One-way nonstop per leg, priced in `currency` for country `country` (the traveller's market, the `gl`
parameter: the home airport's country, so fares match what that country's Google Flights page shows). Returns rows in the same shape as fetchers.flights.parse_flights,
including the flight number (carrier code + number) that fli exposes on every leg.
"""
from __future__ import annotations

import time
import urllib.parse

from .. import money

from .common import Result, fail



def _hm(t) -> str:
    """datetime -> '9:45AM' (matches the browser parser's format)."""
    return t.strftime("%I:%M%p").lstrip("0")


def to_rows(results, orig: str, dest: str, currency: str) -> list[dict]:
    out, seen = [], set()
    for res in results or []:
        if getattr(res, "stops", 0) or len(res.legs) != 1:
            continue
        lg = res.legs[0]
        code = lg.airline.name.lstrip("_")
        fno = f"{code} {lg.flight_number}"
        if fno in seen:
            continue
        seen.add(fno)
        dep, arr = lg.departure_datetime, lg.arrival_datetime
        price = int(round(res.price)) if res.price is not None and (res.currency in (None, currency)) else None
        out.append({
            "airline": getattr(lg.airline, "value", code), "aircraft": lg.aircraft or "",
            "flight": fno, "from": lg.departure_airport.name.lstrip("_"), "to": lg.arrival_airport.name.lstrip("_"),
            "dep": _hm(dep), "arr": _hm(arr), "next_day": arr.date() > dep.date(),
            "duration_min": res.duration or lg.duration,
            "price": price, "currency_symbol": money.symbol(currency).strip(),
        })
    out = [r for r in out if r["from"] == orig and r["to"] == dest] or out
    out.sort(key=lambda r: (r["price"] is None, r["price"] or 0))
    return out


def to_rows_connecting(results, orig: str, dest: str, currency: str, max_total_min: int) -> list[dict]:
    """One-stop itineraries (2 legs) whose total time is within `max_total_min`. Same row shape as to_rows;
    flight = 'XX 123 + YY 456', plus via (the connecting airport) and stops."""
    out, seen = [], set()
    for res in results or []:
        if len(res.legs) != 2 or (res.duration or 0) > max_total_min:
            continue
        l1, l2 = res.legs
        code1, code2 = l1.airline.name.lstrip("_"), l2.airline.name.lstrip("_")
        fno = f"{code1} {l1.flight_number} + {code2} {l2.flight_number}"
        if fno in seen:
            continue
        seen.add(fno)
        price = int(round(res.price)) if res.price is not None and (res.currency in (None, currency)) else None
        out.append({
            "airline": getattr(l1.airline, "value", code1) + (" / " + getattr(l2.airline, "value", code2)
                                                             if code2 != code1 else ""),
            "aircraft": "", "flight": fno, "from": l1.departure_airport.name.lstrip("_"),
            "to": l2.arrival_airport.name.lstrip("_"), "via": l1.arrival_airport.name.lstrip("_"), "stops": 1,
            "dep": _hm(l1.departure_datetime), "arr": _hm(l2.arrival_datetime),
            "next_day": l2.arrival_datetime.date() > l1.departure_datetime.date(),
            "duration_min": res.duration, "price": price, "currency_symbol": money.symbol(currency).strip()})
    out.sort(key=lambda r: (r["price"] is None, r["price"] or 0, r["duration_min"] or 0))
    return out


def fetch_leg_one_stop(orig: str, dest: str, date: str, currency: str, country: str, max_total_hours: float) -> Result:
    """Fallback when no nonstop exists: at most one stop, total time within the brief's
    `flights.max_total_hours_if_stop`. Empty -> ok=False."""
    url = gf_url(orig, dest, date, currency, country).replace("nonstop", "one stop or fewer")
    try:
        from fli.models import Airport, FlightSegment, MaxStops, PassengerInfo
        from fli.models.google_flights.flights import FlightSearchFilters
        from fli.search import SearchFlights
    except Exception as e:  # noqa: BLE001
        return fail(f"fli not installed: {e}", url)
    try:
        a, b = getattr(Airport, orig), getattr(Airport, dest)
        filt = FlightSearchFilters(passenger_info=PassengerInfo(adults=1), stops=MaxStops.ONE_STOP_OR_FEWER,
                                   flight_segments=[FlightSegment(departure_airport=[[a, 0]],
                                                                  arrival_airport=[[b, 0]], travel_date=date)])
    except (AttributeError, ValueError) as e:
        return fail(f"invalid flight query: {e}", url)
    rows: list[dict] = []
    for _ in range(2):
        try:
            res = SearchFlights().search(filt, currency=currency, country=country, language="en")
            rows = to_rows_connecting(res, orig, dest, currency, int(max_total_hours * 60))
        except Exception as e:  # noqa: BLE001
            return fail(f"fli error: {type(e).__name__}: {e}", url)
        if rows and all(r["price"] is not None for r in rows[:3]):
            break
        time.sleep(1.0)
    if not rows:
        return fail(f"no one-stop itinerary within {max_total_hours:g} h", url)
    r = Result(ok=True, data=rows[:4], source_url=url)
    r.backend = "fli"  # type: ignore[attr-defined]
    return r


def gf_url(orig: str, dest: str, date: str, currency: str, country: str = "") -> str:
    q = f"Flights from {orig} to {dest} on {date} nonstop one way"
    return "https://www.google.com/travel/flights?q=" + urllib.parse.quote(q) + f"&curr={currency}&hl=en" + (f"&gl={country}" if country else "")


def fetch_leg(orig: str, dest: str, date: str, currency: str, country: str, tries: int = 2) -> Result:
    """Query fli up to `tries` times (Google returns an empty page ~1 in 60). Empty -> ok=False."""
    url = gf_url(orig, dest, date, currency, country)
    try:
        from fli.models import Airport, FlightSegment, MaxStops, PassengerInfo
        from fli.models.google_flights.flights import FlightSearchFilters
        from fli.search import SearchFlights
    except Exception as e:  # noqa: BLE001
        return fail(f"fli not installed: {e}", url)
    try:
        a, b = getattr(Airport, orig), getattr(Airport, dest)
    except AttributeError as e:
        return fail(f"fli does not know airport {e}", url)
    try:
        filt = FlightSearchFilters(passenger_info=PassengerInfo(adults=1), stops=MaxStops.NON_STOP,
                                   flight_segments=[FlightSegment(departure_airport=[[a, 0]],
                                                                  arrival_airport=[[b, 0]], travel_date=date)])
    except ValueError as e:
        return fail(f"invalid flight query: {e}", url)
    last_err, merged = "fli returned no nonstop flights", {}
    # Google sometimes omits the price on a row; one extra query usually fills it. Merge by flight number.
    for i in range(tries + 1):
        try:
            res = SearchFlights().search(filt, currency=currency, country=country, language="en")
            for row in to_rows(res, orig, dest, currency):
                old = merged.get(row["flight"])
                if old is None or (old["price"] is None and row["price"] is not None):
                    merged[row["flight"]] = row
        except Exception as e:  # noqa: BLE001
            last_err = f"fli error: {type(e).__name__}: {e}"
        if merged and all(r["price"] is not None for r in merged.values()):
            break
        if merged and i + 1 >= tries:
            break
        time.sleep(1.0)
    if merged:
        rows = sorted(merged.values(), key=lambda r: (r["price"] is None, r["price"] or 0))
        r = Result(ok=True, data=rows, source_url=url)
        r.backend = "fli"  # type: ignore[attr-defined]
        return r
    return fail(last_err, url)
