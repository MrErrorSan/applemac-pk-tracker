import json

from scraper import report, score, store
from tests.test_store import make_product


def test_latest_json_is_sorted_and_complete(tmp_path):
    products = [make_product("b", price=200000), make_product("a", price=100000)]
    db = store.Database()
    scores = score.score_all(products, db, {})
    meta = {"run_id": "r1", "generated_at": "x", "fx_rate": 277.5,
            "fx_stale": False, "duty_percent": 0.55, "missing_msrp": [],
            "product_count": 2, "notes": [], "benchmarks": {"a": 150000}}
    path = tmp_path / "latest.json"
    report.write_latest(products, scores, db, meta, path)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert [p["slug"] for p in payload["products"]] == ["a", "b"]
    assert payload["products"][0]["benchmark"] == 150000
    assert "scores" in payload["products"][0]
    assert "benchmarks" not in payload["meta"]


def test_history_json_groups_by_slug(tmp_path):
    db = store.Database()
    db.record_run("r1", [make_product("a", price=100000)], "2026-09-01T00:00:00",
                  "2026-09-01T00:01:00", 277.5, 0.55, "")
    db.record_run("r2", [make_product("a", price=90000)], "2026-09-02T00:00:00",
                  "2026-09-02T00:01:00", 277.5, 0.55, "")
    path = tmp_path / "history.json"
    report.write_history(db, path)
    series = json.loads(path.read_text(encoding="utf-8"))
    assert [point[1] for point in series["a"]] == [100000, 90000]
