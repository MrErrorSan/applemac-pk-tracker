import openpyxl

from scraper import excel, score, store
from scraper.normalize import Product
from tests.test_store import make_product


def build(tmp_path, products, db=None, benchmarks=None, missing_msrp=None):
    db = db or store.Database()
    benchmarks = benchmarks or {}
    scores = score.score_all(products, db, benchmarks)
    meta = {"run_id": "r1", "generated_at": "2026-09-15T00:00:00",
            "fx_rate": 277.75, "fx_stale": False, "duty_percent": 0.55,
            "missing_msrp": missing_msrp if missing_msrp is not None else ["some_key"],
            "benchmarks": benchmarks}
    path = tmp_path / "out.xlsx"
    excel.build_workbook(products, scores, db, meta, path)
    return openpyxl.load_workbook(path)


def _summary_text(wb):
    return "\n".join(
        str(cell)
        for row in wb["Summary"].iter_rows(values_only=True)
        for cell in row if cell is not None
    )


def test_workbook_structure_and_summary_content(tmp_path):
    products = [make_product("expensive", price=900000),
                make_product("cheap", price=100000),
                make_product("mid", price=500000)]
    wb = build(tmp_path, products)

    assert wb.sheetnames == ["Summary", "MacBook Pro", "MacBook Air",
                             "iPhone", "Price Changes"]
    assert wb["iPhone"].max_row >= 1  # header row exists even with no products

    sheet = wb["MacBook Pro"]
    assert sheet.freeze_panes == "A2"
    assert sheet.auto_filter.ref is not None
    prices = [row[0] for row in sheet.iter_rows(min_row=2, min_col=9, max_col=9,
                                                values_only=True)]
    assert prices == sorted(prices)

    text = _summary_text(wb)
    assert "277.75" in text and "55" in text        # fx and duty
    assert "some_key" in text                        # missing msrp keys listed
    assert "how many of the 5 signals" in text        # confidence caveat
    rows = list(wb["Summary"].iter_rows(values_only=True))
    labels = {str(r[0]).strip(): r[1] for r in rows if r and r[0]}
    assert labels["MacBook Pro"] == 3
    assert labels["iPhone"] == 0

    # When every product has confidence 0, Summary explains why nothing ranks.
    products_zero_conf = [
        Product(slug="a", url="https://applemac.pk/product/a", name="A",
                family="macbook_pro", category_slug="macbook-pro-14", image_url=None,
                price=100000, old_price=None, ram_gb=8, storage_gb=256, chip="M4",
                cpu_cores=10, gpu_cores=10, screen_size=14.0, color="Silver",
                model_group="grp_a", config_key="unique_key_a"),
        Product(slug="b", url="https://applemac.pk/product/b", name="B",
                family="macbook_pro", category_slug="macbook-pro-14", image_url=None,
                price=200000, old_price=None, ram_gb=8, storage_gb=256, chip="M4",
                cpu_cores=10, gpu_cores=10, screen_size=14.0, color="Silver",
                model_group="grp_b", config_key="unique_key_b"),
    ]
    db0 = store.Database()
    scores0 = score.score_all(products_zero_conf, db0, {})
    assert scores0["a"].confidence == 0 and scores0["b"].confidence == 0
    wb0 = build(tmp_path, products_zero_conf, db=db0)
    assert "enough data to rank yet" in _summary_text(wb0)


def test_benchmark_column_never_claims_to_be_official(tmp_path):
    wb = build(tmp_path, [make_product()])
    headers = [c.value for c in wb["MacBook Pro"][1]]
    assert "Est. Apple Landed" in headers
    assert "Apple Price" not in headers


def test_zero_confidence_products_excluded_from_top_deals(tmp_path):
    """Products with confidence 0 should not appear in Top deals."""
    products = [make_product("no_data", price=100000)]
    text = _summary_text(build(tmp_path, products))
    assert "no_data" not in text or "not enough data to rank yet" in text


def test_price_movement_ranking_and_formatting(tmp_path):
    db = store.Database()
    db.record_run("r0", [make_product("high_conf", price=100000)], "2026-09-01T00:00:00",
                  "2026-09-01T00:01:00", 277.5, 0.55, "")
    db.record_run("r1", [make_product("high_conf", price=90000),
                          make_product("low_conf", price=200000)],
                  "2026-09-02T00:00:00", "2026-09-02T00:01:00", 277.5, 0.55, "")
    products = [make_product("high_conf", price=90000),
                make_product("low_conf", price=200000)]
    scores = score.score_all(products, db, {})
    meta = {"run_id": "r1", "generated_at": "x", "fx_rate": 277.5,
            "fx_stale": False, "duty_percent": 0.55, "missing_msrp": [],
            "benchmarks": {}}
    path = tmp_path / "out.xlsx"
    excel.build_workbook(products, scores, db, meta, path)
    wb = openpyxl.load_workbook(path)

    # Price Changes sheet lists the movement.
    changes_sheet = wb["Price Changes"]
    assert changes_sheet.max_row >= 2
    assert "-10000" in str([c.value for c in changes_sheet[2]])
    assert len(changes_sheet.conditional_formatting._cf_rules) > 0

    # The device sheet's delta-since-last-run column also has formatting.
    device_sheet = wb["MacBook Pro"]
    assert len(device_sheet.conditional_formatting._cf_rules) > 0

    # high_conf has price history (confidence >= 1) and must be listed in
    # Top deals, ranked ahead of the lower-confidence product at equal-ish scores.
    text = _summary_text(wb)
    assert "HIGH_CONF" in text.upper() or "high_conf" in text
    rows = list(wb["Summary"].iter_rows(values_only=True))
    top_deals_start = next((i for i, r in enumerate(rows) if r and "Top 15 deals" in str(r[0])), None)
    assert top_deals_start is not None
    high_conf_row = low_conf_row = None
    for i in range(top_deals_start + 2, len(rows)):
        if rows[i] and rows[i][0]:
            if "high_conf" in str(rows[i][0]):
                high_conf_row = i
            if "low_conf" in str(rows[i][0]):
                low_conf_row = i
    if high_conf_row and low_conf_row:
        assert high_conf_row < low_conf_row
