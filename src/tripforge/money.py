"""Currency resolution, conversion and formatting. Nothing here assumes a home country.

- country -> currency: Wikidata SPARQL (ISO 3166-1 alpha-2 -> current ISO 4217 code), keyless, cached 30 days.
- conversion: frankfurter.dev (ECB reference rates), keyless, cached 24h.
- symbols: a small ISO 4217 -> symbol table; unknown codes print as the code itself.
"""
from __future__ import annotations

from . import cache
from .fetchers.common import Result, client, fail

SPARQL = "https://query.wikidata.org/sparql"
FRANKFURTER = "https://api.frankfurter.dev/v1/latest"

# Symbols for the major currencies. Anything missing is shown as its ISO code ("CHF 120").
SYMBOLS = {
    "USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥", "CNY": "CN¥", "INR": "₹", "KRW": "₩", "THB": "฿",
    "VND": "₫", "PHP": "₱", "ILS": "₪", "TRY": "₺", "RUB": "₽", "UAH": "₴", "NGN": "₦", "PLN": "zł",
    "CZK": "Kč", "HUF": "Ft", "SEK": "kr", "NOK": "kr", "DKK": "kr", "ISK": "kr", "CHF": "CHF ",
    "AUD": "A$", "NZD": "NZ$", "CAD": "C$", "HKD": "HK$", "SGD": "S$", "TWD": "NT$", "MXN": "MX$",
    "BRL": "R$", "ZAR": "R", "IDR": "Rp", "MYR": "RM", "AED": "AED ", "SAR": "SAR ", "MAD": "MAD ",
    "EGP": "E£", "KES": "KSh", "LKR": "Rs", "PKR": "Rs", "NPR": "Rs", "BDT": "৳", "RON": "lei",
    "BGN": "лв", "CLP": "CLP$", "COP": "COL$", "ARS": "AR$", "PEN": "S/",
}


def symbol(ccy: str) -> str:
    return SYMBOLS.get(ccy.upper(), ccy.upper() + " ")


def fmt(n, ccy: str) -> str:
    """12345 -> '€12,345'; None -> 'unavailable'."""
    if n is None:
        return "unavailable"
    return f"{symbol(ccy)}{int(round(n)):,}"


def country_currency(cc: str) -> Result:
    """ISO 3166-1 alpha-2 -> current ISO 4217 code (data = 'EUR'), via Wikidata."""
    cc = cc.upper()

    def go() -> Result:
        q = (f'SELECT ?code WHERE {{ ?c wdt:P297 "{cc}"; wdt:P38 ?cur. ?cur wdt:P498 ?code. '
             "FILTER NOT EXISTS { ?cur wdt:P576 [] } } LIMIT 3")
        try:
            with client(30) as c:
                j = c.get(SPARQL, params={"query": q}, headers={"Accept": "application/sparql-results+json"}).json()
            rows = j["results"]["bindings"]
            return Result(ok=True, data=rows[0]["code"]["value"], source_url=f"{SPARQL}?query={q}")
        except Exception as e:  # noqa: BLE001
            return fail(f"currency lookup for {cc} failed: {e}", SPARQL)
    return cache.cached("geo:currency", {"cc": cc, "v": 2}, go)


def rate(src: str, dst: str) -> float | None:
    """Units of dst per 1 src, or None when frankfurter cannot say."""
    src, dst = src.upper(), dst.upper()
    if src == dst:
        return 1.0

    def go() -> Result:
        url = f"{FRANKFURTER}?from={src}&to={dst}"
        try:
            with client(20) as c:
                j = c.get(url).json()
            return Result(ok=True, data=float(j["rates"][dst]), source_url=url)
        except Exception as e:  # noqa: BLE001
            return fail(f"fx {src}->{dst} failed: {e}", url)
    r = cache.cached("fx:rate", {"s": src, "d": dst}, go)
    return r.data if r.ok else None


def convert_range(rng: list[float], src: str, dst: str, step: int = 10) -> list[int] | None:
    k = rate(src, dst)
    if k is None:
        return None
    return [int(round(x * k / step)) * step if x * k >= step * 5 else int(round(x * k)) for x in rng]


def resolve_currency(cfg: dict, home_cc: str) -> str:
    """Brief's currency wins; otherwise the home airport's country currency. Raises ValueError if neither."""
    if cfg.get("currency"):
        return str(cfg["currency"]).upper()
    r = country_currency(home_cc)
    if r.ok:
        return r.data
    raise ValueError(f"no currency in the brief and the home country's currency could not be looked up "
                     f"({r.error}); set currency: <ISO 4217 code> in the brief")
