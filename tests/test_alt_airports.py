from tripforge.stops import alt_airports


def _ap(iata, km):
    return {"iata": iata, "km": km, "lat": 0, "lon": 0, "name": iata, "city": iata}


def test_twin_city_airports_are_both_priced():
    szb, kul, mkz = _ap("SZB", 16), _ap("KUL", 45), _ap("MKZ", 116)
    assert [a["iata"] for a in alt_airports(szb, 16, [szb, kul, mkz])] == ["KUL"]


def test_own_airport_far_hub_not_priced():
    kbv, hkt = _ap("KBV", 15), _ap("HKT", 65)
    assert alt_airports(kbv, 15, [kbv, hkt]) == []


def test_no_own_airport_prices_regional_options():
    kbv, hkt = _ap("KBV", 48), _ap("HKT", 110)
    assert [a["iata"] for a in alt_airports(kbv, 48, [kbv, hkt])] == ["HKT"]
