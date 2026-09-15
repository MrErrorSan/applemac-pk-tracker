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
    db.record_run("run1", [make_product()], "2026-09-01T00:00:00",
                  "2026-09-01T00:01:00", 277.5, 0.55, "")
    store.save(db, tmp_path)

    reloaded = store.load(tmp_path)
    assert list(reloaded.products) == ["a"]
    assert reloaded.history[0].price == 100000
    assert reloaded.runs[0].run_id == "run1"
    assert reloaded.runs[0].fx_rate == 277.5


def test_history_is_append_only(tmp_path):
    db = store.Database()
    db.record_run("run1", [make_product(price=100000)], "2026-09-01T00:00:00",
                  "2026-09-01T00:01:00", 277.5, 0.55, "")
    store.save(db, tmp_path)

    db = store.load(tmp_path)
    db.record_run("run2", [make_product(price=90000)], "2026-09-02T00:00:00",
                  "2026-09-02T00:01:00", 277.5, 0.55, "")
    store.save(db, tmp_path)

    reloaded = store.load(tmp_path)
    assert [s.price for s in reloaded.price_history("a")] == [100000, 90000]


def test_load_from_empty_directory(tmp_path):
    db = store.load(tmp_path)
    assert db.products == {}
    assert db.history == []
    assert db.previous_run() is None


def test_changes_since_reports_movement(tmp_path):
    db = store.Database()
    db.record_run("run1", [make_product(price=100000)], "2026-09-01T00:00:00",
                  "2026-09-01T00:01:00", 277.5, 0.55, "")
    db.record_run("run2", [make_product(price=90000)], "2026-09-02T00:00:00",
                  "2026-09-02T00:01:00", 277.5, 0.55, "")
    changes = db.changes_since("run2")
    assert len(changes) == 1
    assert changes[0].delta == -10000
    assert round(changes[0].pct, 2) == -10.0


def test_changes_since_ignores_unchanged_and_new_products():
    db = store.Database()
    db.record_run("run1", [make_product("a", 100000)], "2026-09-01T00:00:00",
                  "2026-09-01T00:01:00", 277.5, 0.55, "")
    db.record_run("run2", [make_product("a", 100000), make_product("b", 50000)],
                  "2026-09-02T00:00:00", "2026-09-02T00:01:00", 277.5, 0.55, "")
    assert db.changes_since("run2") == []


def test_median_price_respects_window():
    db = store.Database()
    now = dt.datetime(2026, 9, 15, tzinfo=dt.timezone.utc)
    old = (now - dt.timedelta(days=200)).isoformat()
    recent = (now - dt.timedelta(days=5)).isoformat()
    db.record_run("old", [make_product(price=500000)], old, old, 277.5, 0.55, "")
    db.record_run("new", [make_product(price=100000)], recent, recent, 277.5, 0.55, "")
    assert db.median_price("a", days=90, now=now) == 100000


def test_median_price_none_without_history():
    assert store.Database().median_price("nope", days=90) is None


def test_save_is_atomic_leaving_no_temp_files(tmp_path):
    db = store.Database()
    db.record_run("run1", [make_product()], "2026-09-01T00:00:00",
                  "2026-09-01T00:01:00", 277.5, 0.55, "")
    store.save(db, tmp_path)
    assert not list(tmp_path.glob("*.tmp"))


def test_build_sqlite_creates_queryable_database(tmp_path):
    db = store.Database()
    db.record_run("run1", [make_product()], "2026-09-01T00:00:00",
                  "2026-09-01T00:01:00", 277.5, 0.55, "")
    path = tmp_path / "prices.db"
    store.build_sqlite(db, path)

    con = sqlite3.connect(path)
    assert con.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] == 1
    assert con.execute("SELECT price FROM snapshots").fetchone()[0] == 100000
    con.close()


def test_category_counts(tmp_path):
    db = store.Database()
    db.record_run("run1", [make_product("a"), make_product("b")],
                  "2026-09-01T00:00:00", "2026-09-01T00:01:00", 277.5, 0.55, "")
    assert db.category_counts("run1") == {"macbook-pro-14": 2}
