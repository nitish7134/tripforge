"""tripforge site: the generator must stay destination-agnostic and refuse private data."""
import json, pathlib, re, shutil, subprocess
import pytest
from tripforge.site import build, init, _derive, order, HERE

EX = pathlib.Path(__file__).resolve().parents[1] / "trips" / "example-vela-islands"


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
    dst = tmp_path / "example-vela-islands"
    shutil.copytree(EX, dst)
    shutil.rmtree(dst / "site" / "dist", ignore_errors=True)
    dist = build(dst)
    html = (dist / "index.html").read_text()
    assert "const TRIP=" in html and '"slug": "example-vela-islands"' in html
    assert "/*@TRIP*/" not in html
    assert (dist / "sw.js").read_text().count("example-vela-islands-v1") == 1
    assert (dist / "lock" / "index.html").read_text().count("<h1>Vela</h1>") == 1
    # second build bumps the cache
    build(dst)
    assert "example-vela-islands-v2" in (dist / "sw.js").read_text()


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


def test_check_clean_and_drift(tmp_path):
    from tripforge.site import check
    dst = tmp_path / "t"; shutil.copytree(EX, dst); shutil.rmtree(dst / "site" / "dist", ignore_errors=True)
    assert check(dst) == []
    build(dst)
    assert check(dst) == []
    (dst / "site" / "dist" / "index.html").write_text("stale")
    assert any("differs" in p for p in check(dst))


def test_settle_is_minimal_and_exact():
    """The settle-up module must beat greedy on the classic zero-sum-subset case and square every balance."""
    import subprocess
    node = shutil.which("node") or shutil.which("node", path="/opt/homebrew/opt/node@24/bin:/opt/homebrew/bin:/usr/local/bin")
    if not node:
        pytest.skip("node not installed")
    js = (pathlib.Path(__file__).parents[1] / "src/tripforge/site/js/14b-settle.js").read_text()
    prog = js + """
const tx=settle({A:10,B:-10,C:5,D:-5},1);
const net={A:10,B:-10,C:5,D:-5};for(const t of tx){net[t.from]+=t.amount;net[t.to]-=t.amount}
console.log(JSON.stringify({n:tx.length,net}));"""
    out = subprocess.run([node, "-e", prog], capture_output=True, text=True, check=True).stdout
    r = json.loads(out)
    assert r["n"] == 2  # greedy would give 3
    assert all(abs(v) < 1e-6 for v in r["net"].values())


def test_ledger_module_uses_trip_categories():
    js = (pathlib.Path(__file__).parents[1] / "src/tripforge/site/js/15-ledger.js").read_text()
    assert "TRIP.categories" in js and "Refresh" not in js
    shell = (pathlib.Path(__file__).parents[1] / "src/tripforge/site/shell.html.j2").read_text()
    assert 'id="l-cat"' in shell and 'id="settle"' in shell and "syncLedger(true)" not in shell
