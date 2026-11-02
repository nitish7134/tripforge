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
    hits = []
    for p in SRC.rglob("*"):
        if p.suffix not in {".py", ".j2", ".md", ".txt"} or "data" in p.relative_to(SRC).parts:
            continue
        for i, line in enumerate(p.read_text().splitlines(), 1):
            if p.name == "money.py" and line.startswith('    "USD"'):
                continue  # the symbol table
            if bad.search(line):
                hits.append(f"{p.relative_to(SRC)}:{i}: {line.strip()}")
    assert not hits, "\n".join(hits)


def test_no_data_files_under_src():
    """Fetch strategy, not data: src/ ships no JSON/YAML/CSV data (no place names, no prices)."""
    found = [str(p.relative_to(SRC)) for p in SRC.rglob("*") if p.suffix in {".json", ".yaml", ".yml", ".csv"}]
    assert not found, f"data files under src/: {found}"
