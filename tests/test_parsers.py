import json
from pathlib import Path

from tripforge.fetchers.flights import parse_flights
from tripforge.fetchers.stays import parse_cards

FX = Path(__file__).parent / "fixtures"


def test_flights_parse_numbers_and_times():
    sec = (FX / "flights_raw.txt").read_text().split("=== ")[1]
    text = json.loads(sec.split("\n", 1)[1].strip().splitlines()[0])
    rows = parse_flights(text)
    assert rows[0]["flight"] == "6E 1217" and rows[0]["dep"] == "6:20AM" and rows[0]["arr"] == "11:30AM"
    assert rows[0]["from"] == "BLR" and rows[0]["to"] == "HKT" and rows[0]["price"] == 24238
    assert rows[1]["flight"] == "QP 623"


def test_airbnb_cards_parse():
    sec = (FX / "airbnb_cards.txt").read_text().split("=== ")[1]
    cards = json.loads(json.loads(sec.split("\n", 1)[1].strip().splitlines()[0]))
    rows = parse_cards(cards, 1)
    assert rows[0]["rating"] == 4.96 and rows[0]["reviews"] == 28 and rows[0]["total"] == 2936
    assert rows[0]["url"].startswith("https://www.airbnb.co.in/rooms/")
