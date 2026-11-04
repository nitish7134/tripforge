from tripforge.fetchers.stays_pyairbnb import pick


def _row(kind, **kw):
    return {"name": kind, "kind": kind, "room_type": kw.get("room_type", "Entire place"), "rating": 4.8,
            "reviews": 30, "per_night": 1500, "total": 3000, "url": f"https://example.test/{kind}"}


def test_entire_place_search_skips_tents_and_dorms():
    rows = [_row("Tent in Ao Nang"), _row("Bed in dorm", room_type="Shared room"), _row("Condo in Patong")]
    assert [r["kind"] for r in pick(rows)] == ["Condo in Patong"]


def test_room_search_keeps_them():
    rows = [_row("Tent in Ao Nang"), _row("Condo in Patong")]
    assert len(pick(rows, allow_shared=True)) == 2
