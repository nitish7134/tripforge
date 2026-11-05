"""tripforge site: the generator must stay destination-agnostic and refuse private data."""
import json, pathlib, re, shutil, subprocess
import pytest
from tripforge.site import build, init, _derive, order, HERE

EX = pathlib.Path(__file__).resolve().parents[1] / "trips" / "example-goa-family"


def test_order_lists_existing_modules():
    o = order()
    for n in o["css"]:
        assert (HERE / "styles" / f"{n}.css").exists(), n
    for n in o["js"]:
        assert (HERE / "js" / f"{n}.js").exists(), n
    assert o["js"][0] == "03-trip-inject", "TRIP/DATA must be defined before every other module"


def test_template_has_no_destination_words():
    """Nothing trip-specific may live in the reusable template (code, styles, shell)."""
    bad = re.compile(r"\b(Goa|Thailand|Patong|Bangkok|Morjim|Baga|Phuket|Krabi|INR|THB|Bengaluru|Nagpur)\b")
    for f in list((HERE / "js").glob("*.js")) + list((HERE / "styles").glob("*.css")) + [HERE / "shell.html.j2", HERE / "sw.js.j2"]:
        hits = bad.findall(f.read_text())
        assert not hits, f"{f.name}: {hits}"


def test_derive_fills_defaults():
    t = _derive({"slug": "x", "name": "X", "home": "BLR", "start": "2027-01-10", "end": "2027-01-14", "tz": "Europe/Lisbon", "cur": "EUR", "sym": "€",
                 "homeCur": "INR", "homeSym": "₹", "people": [{"k": "A", "n": "A"}, {"k": "B", "n": "B"}]},
                [{"kind": "fly", "t": "2027-01-10T02:00:00+05:30"}, {"kind": "fly", "t": "2027-01-14T20:00:00+00:00"}])
    assert t["ndays"] == 5 and t["nights"] == 4
    assert t["features"]["fx"] is True and t["split"] == "equal"
    assert t["tzOffset"] == "+00:00" and t["t0"].startswith("2027-01-10T02:00")


def test_derive_single_currency_family():
    t = _derive({"slug": "x", "name": "X", "home": "NAG", "start": "2026-11-22", "end": "2026-11-30", "tz": "Asia/Kolkata", "cur": "INR", "sym": "₹",
                 "people": [{"k": "A", "n": "A"}], "split": "none"})
    assert t["features"]["fx"] is False and t["split"] == "none" and t["tzOffset"] == "+05:30"


def test_build_example(tmp_path):
    dst = tmp_path / "example-goa-family"
    shutil.copytree(EX, dst)
    shutil.rmtree(dst / "site" / "dist", ignore_errors=True)
    dist = build(dst)
    html = (dist / "index.html").read_text()
    assert "const TRIP=" in html and '"slug": "example-goa-family"' in html
    assert "/*@TRIP*/" not in html
    assert (dist / "sw.js").read_text().count("example-goa-family-v1") == 1
    assert (dist / "lock" / "index.html").read_text().count("<h1>Goa</h1>") == 1
    # second build bumps the cache
    build(dst)
    assert "example-goa-family-v2" in (dist / "sw.js").read_text()


def test_build_refuses_private_data(tmp_path):
    dst = tmp_path / "t"; shutil.copytree(EX, dst); shutil.rmtree(dst / "site" / "dist", ignore_errors=True)
    cfg = json.loads((dst / "site" / "trip.json").read_text())
    cfg["data"]["smarts"].append("Passport number Z1234567 at the desk")
    (dst / "site" / "trip.json").write_text(json.dumps(cfg))
    with pytest.raises(SystemExit):
        build(dst)


def test_init_skeleton(tmp_path):
    (tmp_path / "brief.yaml").write_text("destination: Lisbon, Portugal\nstart: 2027-03-01\nnights: 5\npeople: 2\nfrom: BLR\ncurrency: EUR\n")
    out = init(tmp_path)
    cfg = json.loads(out.read_text())
    assert cfg["trip"]["end"] == "2027-03-06" and cfg["trip"]["name"] == "Lisbon" and len(cfg["trip"]["people"]) == 2
