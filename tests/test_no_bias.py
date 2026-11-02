"""Nothing in the tool may be biased toward one traveller or one trip."""
import re
from pathlib import Path

import pytest

from tripforge import money
from tripforge.fetchers import airports as AP
from tripforge.fetchers.common import Result
from tripforge.plan import SPEND_PLACEHOLDER, daily_spend

SRC = Path(__file__).resolve().parents[1] / "src" / "tripforge"


def test_lisbon_brief_without_currency_resolves_eur(monkeypatch):
    # plumbing is offline: the Wikidata answer is stubbed; the live lookup is covered below
    monkeypatch.setattr(money, "country_currency", lambda cc: Result(ok=True, data={"PT": "EUR"}[cc]))
    try:
        home = AP.resolve_home({"from": "LIS"})
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"OurAirports data unavailable: {e}")
    assert home["cc"] == "PT"
    assert money.resolve_currency({"from": "LIS"}, home["cc"]) == "EUR"
    assert money.resolve_currency({"from": "LIS", "currency": "usd"}, home["cc"]) == "USD"


def test_live_wikidata_currency():
    r = money.country_currency("PT")
    if not r.ok:
        pytest.skip(r.error)
    assert r.data == "EUR"


def test_missing_home_is_an_error():
    with pytest.raises(ValueError, match="home airport"):
        AP.resolve_home({})


def test_symbols_generic():
    assert money.fmt(1234, "EUR") == "€1,234"
    assert money.fmt(1234, "CHF") == "CHF 1,234"
    assert money.fmt(None, "EUR") == "unavailable"
    assert money.symbol("XYZ") == "XYZ "


def test_no_meal_rate_gives_placeholder_not_numbers():
    rows, total, note = daily_spend({"meals_per_day": 3, "meal_rate": None, "party_rate": None,
                                     "transport_day": None}, 11, 5, True)
    assert rows == [] and total is None and note == SPEND_PLACEHOLDER
    # party trip without party_rate is also a placeholder; no invented number
    assert daily_spend({"meals_per_day": 3, "meal_rate": 20, "party_rate": None, "transport_day": None},
                       11, 5, True)[2] == SPEND_PLACEHOLDER
    rows, total, note = daily_spend({"meals_per_day": 3, "meal_rate": 20, "party_rate": None,
                                     "transport_day": None}, 11, 0, False)
    assert note is None and total == 11 * 3 * 20


def test_template_renders_placeholder_branch():
    tpl = (SRC / "templates" / "plan.html.j2").read_text()
    assert "spend_note" in tpl


def test_no_hardcoded_traveller_in_source():
    """INR / BLR / Thailand may live in example data and tests only. money.py's ISO symbol table is the one
    place a currency code is named (INR is a major currency, not a default)."""
    bad = re.compile(r"\bINR\b|\bBLR\b|Thailand|Bangkok|Phuket|Bengaluru|Akasa|IndiGo|₹|TDAC|7 ?kg", re.I)
    bad_exact = re.compile(r"\bIST\b|Full Moon|US State Department used as default|two sharing|two friends|Suparth"
                           r"|nonstop flights only|nonstop-only|Rs\.? ?\d")
    hits = []
    for p in SRC.rglob("*"):
        if p.suffix not in {".py", ".j2", ".md", ".txt"} or "data" in p.relative_to(SRC).parts:
            continue
        for i, line in enumerate(p.read_text().splitlines(), 1):
            if p.name == "money.py" and line.startswith('    "USD"'):
                continue  # the symbol table
            if bad_exact.search(line):
                hits.append(f"{p.relative_to(SRC)}:{i}: {line.strip()}")
            if bad.search(line):
                hits.append(f"{p.relative_to(SRC)}:{i}: {line.strip()}")
    assert not hits, "\n".join(hits)


def test_no_data_files_under_src():
    """Fetch strategy, not data: src/ ships no JSON/YAML/CSV data (no place names, no prices)."""
    found = [str(p.relative_to(SRC)) for p in SRC.rglob("*") if p.suffix in {".json", ".yaml", ".yml", ".csv"}]
    assert not found, f"data files under src/: {found}"


def test_advisory_source_follows_passport():
    from tripforge.fetchers import advisory
    assert advisory.SOURCES["GB"] == ["FCDO"] and advisory.SOURCES["US"] == ["US"] and advisory.SOURCES["CA"] == ["CA"]
    assert "AU" not in advisory.SOURCES and advisory.THIRD_COUNTRY == ["FCDO", "US"]


def test_climate_warning_is_derived_from_numbers():
    from tripforge.fetchers.climate import warning
    assert "wet season: 18 rain days" in warning({"rain_days": 18, "day_high_c": 30, "night_low_c": 22})
    assert warning({"rain_days": 2, "day_high_c": 37, "night_low_c": 1}).startswith("mostly dry: 2 rain days; very hot")


def test_moon_events_only_when_guide_mentions_them():
    import datetime as dt
    from tripforge import events
    a, b = dt.date(2026, 12, 15), dt.date(2027, 1, 5)
    assert events.lunar_rows(a, b, ["a quiet town with beaches"]) == []
    assert events.lunar_rows(a, b, ["famous monthly full moon party"])


def test_dietary_prefs_are_generic_tags():
    from tripforge.fetchers import places
    assert places.diets_in(["party", "halal", "gluten-free", "veg"]) == ("gluten-free", "halal", "veg")
    q = places._q(1.0, 2.0, 500, ("halal",))
    assert "diet:halal" in q and "diet:vegetarian" not in q
    out = places.classify([{"type": "node", "id": 1, "lat": 1, "lon": 2,
                            "tags": {"amenity": "restaurant", "name": "Alpha", "diet:halal": "only"}}], ("halal",))
    assert out["diet"]["halal"][0]["kind"] == "only halal"
