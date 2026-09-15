import datetime as dt
import sqlite3

from scraper import store
from scraper.normalize import Product


def make_product(slug="a", price=100000, old_price=None, config_key="grp_8_256"):
    return Product(
        slug=slug, url=f"https://applemac.pk/product/{slug}", name=slug.upper(),
        family="macbook_pro", category_slug="macbook-pro-14", image_url=None,
        price=price, old_price=old_price, ram_gb=8, storage_gb=256, chip="M4",
        cpu_cores=10, gpu_cores=10, screen_size=14.0, color="Silver",
        model_group="grp", config_key=config_key,
    )


def test_round_trip_preserves_data(tmp_path):
    db = store.Database()
    db.record_run("run1", [make_product("a"), make_product("b")], "2026-09-01T00:00:00",
                  "2026-09-01T00:01:00", 277.5, 0.55, "")
    store.save(db, tmp_path)

    reloaded = store.load(tmp_path)
    assert set(reloaded.products) == {"a", "b"}
    assert reloaded.history[0].price == 100000
    assert reloaded.runs[0].run_id == "run1"
    assert reloaded.runs[0].fx_rate == 277.5
    assert reloaded.category_counts("run1") == {"macbook-pro-14": 2}


def test_csv_type_fidelity_round_trip(tmp_path):
    """int/float/None values must survive a save/load round trip as their
    real types, not as the literal string "None"."""
    db = store.Database()
    db.record_run("run1", [make_product("a", price=100000, old_price=None)],
                  "2026-09-01T00:00:00", "2026-09-01T00:01:00", 277.5, 0.55, "")
    store.save(db, tmp_path)

    raw = (tmp_path / "history.csv").read_text(encoding="utf-8")
    assert '"None"' not in raw and ",None," not in raw.replace("\r\n", "\n").split("\n")[1]

    reloaded = store.load(tmp_path)
    snapshot = reloaded.history[0]
    assert snapshot.price == 100000 and isinstance(snapshot.price, int)
    assert snapshot.old_price is None
    product = reloaded.products["a"]
    assert product["ram_gb"] == 8 and isinstance(product["ram_gb"], int)
    assert product["screen_size"] == 14.0 and isinstance(product["screen_size"], float)
    run = reloaded.runs[0]
    assert run.fx_rate == 277.5 and isinstance(run.fx_rate, float)


def test_first_seen_preserved_last_seen_advances(tmp_path):
    db = store.Database()
    db.record_run("run1", [make_product("a")], "2026-09-01T00:00:00",
                  "2026-09-01T00:01:00", 277.5, 0.55, "")
    store.save(db, tmp_path)

    db = store.load(tmp_path)
    db.record_run("run2", [make_product("a")], "2026-09-05T00:00:00",
                  "2026-09-05T00:01:00", 277.5, 0.55, "")
    store.save(db, tmp_path)

    reloaded = store.load(tmp_path)
    assert reloaded.products["a"]["first_seen"] == "2026-09-01T00:00:00"
    assert reloaded.products["a"]["last_seen"] == "2026-09-05T00:00:00"


def test_history_append_only_and_changes_since(tmp_path):
    empty = store.load(tmp_path)
    assert empty.products == {} and empty.history == [] and empty.previous_run() is None

    db = store.Database()
    db.record_run("run1", [make_product("a", 100000)], "2026-09-01T00:00:00",
                  "2026-09-01T00:01:00", 277.5, 0.55, "")
    db.record_run("run2", [make_product("a", 90000), make_product("b", 50000)],
                  "2026-09-02T00:00:00", "2026-09-02T00:01:00", 277.5, 0.55, "")
    assert [s.price for s in db.price_history("a")] == [100000, 90000]

    changes = db.changes_since("run2")
    assert len(changes) == 1                  # "b" is new, must be ignored
    assert changes[0].slug == "a"
    assert changes[0].delta == -10000
    assert round(changes[0].pct, 2) == -10.0

    db.record_run("run3", [make_product("a", 90000), make_product("b", 50000)],
                  "2026-09-03T00:00:00", "2026-09-03T00:01:00", 277.5, 0.55, "")
    assert db.changes_since("run3") == []      # unchanged prices produce no changes


def test_median_price():
    now = dt.datetime(2026, 9, 15, tzinfo=dt.timezone.utc)

    assert store.Database().median_price("nope", days=90) is None

    db = store.Database()
    old = (now - dt.timedelta(days=200)).isoformat()
    recent = (now - dt.timedelta(days=5)).isoformat()
    db.record_run("old", [make_product(price=500000)], old, old, 277.5, 0.55, "")
    db.record_run("new", [make_product(price=100000)], recent, recent, 277.5, 0.55, "")
    assert db.median_price("a", days=90, now=now) == 100000  # respects the window

    db2 = store.Database()
    prices = [100000, 110000, 90000, 105000, 95000]
    for i, (age, price) in enumerate(zip([1, 2, 3, 4, 5], prices)):
        seen = (now - dt.timedelta(days=age)).isoformat()
        db2.record_run(f"run{i}", [make_product(price=price)], seen, seen, 277.5, 0.55, "")
    assert db2.median_price("a", days=90, now=now) == 100000  # median over several

    # A run comparing its own just-saved snapshot to itself would fabricate a 0.
    db3 = store.Database()
    started = now.isoformat()
    db3.record_run("today", [make_product(price=100000)], started, started, 277.5, 0.55, "")
    assert db3.median_price("a", days=90, now=now, exclude_run_id="today") is None

    db4 = store.Database()
    prior = (now - dt.timedelta(days=5)).isoformat()
    db4.record_run("prior", [make_product(price=150000)], prior, prior, 277.5, 0.55, "")
    db4.record_run("today", [make_product(price=100000)], started, started, 277.5, 0.55, "")
    assert db4.median_price("a", days=90, now=now, exclude_run_id="today") == 150000


def test_save_is_atomic_and_sqlite_export(tmp_path):
    db = store.Database()
    db.record_run("run1", [make_product()], "2026-09-01T00:00:00",
                  "2026-09-01T00:01:00", 277.5, 0.55, "")
    store.save(db, tmp_path)
    assert not list(tmp_path.glob("*.tmp"))

    path = tmp_path / "prices.db"
    store.build_sqlite(db, path)
    con = sqlite3.connect(path)
    assert con.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] == 1
    assert con.execute("SELECT price FROM snapshots").fetchone()[0] == 100000
    con.close()
