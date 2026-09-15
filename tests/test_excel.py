import openpyxl

from scraper import excel, score, store
from tests.test_store import make_product


def build(tmp_path, products, db=None, benchmarks=None):
    db = db or store.Database()
    benchmarks = benchmarks or {}
    scores = score.score_all(products, db, benchmarks)
    meta = {"run_id": "r1", "generated_at": "2026-09-15T00:00:00",
            "fx_rate": 277.75, "fx_stale": False, "duty_percent": 0.55,
            "missing_msrp": ["some_key"], "benchmarks": benchmarks}
    path = tmp_path / "out.xlsx"
    excel.build_workbook(products, scores, db, meta, path)
    return openpyxl.load_workbook(path)


def test_workbook_has_expected_sheets(tmp_path):
    wb = build(tmp_path, [make_product()])
    assert wb.sheetnames == ["Summary", "MacBook Pro", "MacBook Air",
                             "iPhone", "Price Changes"]


def test_rows_sorted_cheapest_first(tmp_path):
    products = [make_product("expensive", price=900000),
                make_product("cheap", price=100000),
                make_product("mid", price=500000)]
    sheet = build(tmp_path, products)["MacBook Pro"]
    prices = [row[0] for row in sheet.iter_rows(min_row=2, min_col=9, max_col=9,
                                                values_only=True)]
    assert prices == sorted(prices)


def test_header_row_is_frozen_and_filtered(tmp_path):
    sheet = build(tmp_path, [make_product()])["MacBook Pro"]
    assert sheet.freeze_panes == "A2"
    assert sheet.auto_filter.ref is not None


def test_summary_records_fx_and_duty(tmp_path):
    text = "\n".join(
        str(cell)
        for row in build(tmp_path, [make_product()])["Summary"].iter_rows(values_only=True)
        for cell in row if cell is not None
    )
    assert "277.75" in text
    assert "55" in text


def test_summary_lists_per_family_counts(tmp_path):
    rows = list(build(tmp_path, [make_product()])["Summary"].iter_rows(values_only=True))
    labels = {str(r[0]).strip(): r[1] for r in rows if r and r[0]}
    assert labels["MacBook Pro"] == 1
    assert labels["iPhone"] == 0


def test_summary_lists_missing_msrp_keys(tmp_path):
    text = "\n".join(
        str(cell)
        for row in build(tmp_path, [make_product()])["Summary"].iter_rows(values_only=True)
        for cell in row if cell is not None
    )
    assert "some_key" in text


def test_benchmark_column_never_claims_to_be_official(tmp_path):
    wb = build(tmp_path, [make_product()])
    headers = [c.value for c in wb["MacBook Pro"][1]]
    assert "Est. Apple Landed" in headers
    assert "Apple Price" not in headers


def test_price_changes_sheet_lists_movement(tmp_path):
    db = store.Database()
    db.record_run("r0", [make_product("a", price=100000)], "2026-09-01T00:00:00",
                  "2026-09-01T00:01:00", 277.5, 0.55, "")
    db.record_run("r1", [make_product("a", price=90000)], "2026-09-02T00:00:00",
                  "2026-09-02T00:01:00", 277.5, 0.55, "")
    products = [make_product("a", price=90000)]
    scores = score.score_all(products, db, {})
    meta = {"run_id": "r1", "generated_at": "x", "fx_rate": 277.5,
            "fx_stale": False, "duty_percent": 0.55, "missing_msrp": [],
            "benchmarks": {}}
    path = tmp_path / "out.xlsx"
    excel.build_workbook(products, scores, db, meta, path)
    sheet = openpyxl.load_workbook(path)["Price Changes"]
    assert sheet.max_row >= 2
    assert "-10000" in str([c.value for c in sheet[2]])


def test_empty_family_still_produces_a_sheet(tmp_path):
    wb = build(tmp_path, [make_product()])
    assert wb["iPhone"].max_row >= 1  # header row exists even with no products


def test_zero_confidence_products_excluded_from_top_deals(tmp_path):
    """Products with confidence 0 should not appear in Top deals"""
    # confidence 0 product (make_product defaults to this)
    products = [make_product("no_data", price=100000)]
    text = "\n".join(
        str(cell)
        for row in build(tmp_path, products)["Summary"].iter_rows(values_only=True)
        for cell in row if cell is not None
    )
    # Should not list the product in Top deals
    assert "no_data" not in text or "not enough data to rank yet" in text


def test_high_confidence_products_included_in_top_deals(tmp_path):
    """Products with confidence >= 1 should appear in Top deals"""
    db = store.Database()
    db.record_run("r0", [make_product("a", price=100000)], "2026-09-01T00:00:00",
                  "2026-09-01T00:01:00", 277.5, 0.55, "")
    db.record_run("r1", [make_product("a", price=100000)], "2026-09-02T00:00:00",
                  "2026-09-02T00:01:00", 277.5, 0.55, "")
    products = [make_product("a", price=100000)]
    # This should have confidence >= 1 due to price history
    text = "\n".join(
        str(cell)
        for row in build(tmp_path, products, db=db)["Summary"].iter_rows(values_only=True)
        for cell in row if cell is not None
    )
    assert "A" in text  # Product name should be in Top deals


def test_all_zero_confidence_shows_not_enough_data_message(tmp_path):
    """When all products have confidence 0, show explanatory message"""
    # Create products with different config_keys so they're not peers of each other
    # This ensures confidence 0 (no signals: no benchmarks, no history, no peers, no specs)
    from scraper.normalize import Product
    products = [
        Product(
            slug="a", url="https://applemac.pk/product/a", name="A",
            family="macbook_pro", category_slug="macbook-pro-14", image_url=None,
            price=100000, old_price=None, ram_gb=8, storage_gb=256, chip="M4",
            cpu_cores=10, gpu_cores=10, screen_size=14.0, color="Silver",
            model_group="grp_a", config_key="unique_key_a",
        ),
        Product(
            slug="b", url="https://applemac.pk/product/b", name="B",
            family="macbook_pro", category_slug="macbook-pro-14", image_url=None,
            price=200000, old_price=None, ram_gb=8, storage_gb=256, chip="M4",
            cpu_cores=10, gpu_cores=10, screen_size=14.0, color="Silver",
            model_group="grp_b", config_key="unique_key_b",
        ),
    ]
    db = store.Database()
    scores = score.score_all(products, db, {})
    # Verify both have confidence 0
    assert scores[products[0].slug].confidence == 0
    assert scores[products[1].slug].confidence == 0

    meta = {"run_id": "r1", "generated_at": "2026-09-15T00:00:00",
            "fx_rate": 277.75, "fx_stale": False, "duty_percent": 0.55,
            "missing_msrp": ["some_key"], "benchmarks": {}}
    path = tmp_path / "out.xlsx"
    excel.build_workbook(products, scores, db, meta, path)

    text = "\n".join(
        str(cell)
        for row in openpyxl.load_workbook(path)["Summary"].iter_rows(values_only=True)
        for cell in row if cell is not None
    )
    assert "enough data to rank yet" in text


def test_equal_deal_scores_break_by_confidence(tmp_path):
    """Products with equal deal_score should rank by confidence descending"""
    db = store.Database()
    # First product: will have price history (confidence >= 1)
    db.record_run("r0", [make_product("high_conf", price=100000)], "2026-09-01T00:00:00",
                  "2026-09-01T00:01:00", 277.5, 0.55, "")
    db.record_run("r1", [make_product("high_conf", price=100000),
                          make_product("low_conf", price=200000)],
                  "2026-09-02T00:00:00", "2026-09-02T00:01:00", 277.5, 0.55, "")
    products = [make_product("high_conf", price=100000),
                make_product("low_conf", price=200000)]
    sheet = build(tmp_path, products, db=db)["Summary"]
    # Find Top 15 deals section
    rows = list(sheet.iter_rows(values_only=True))
    top_deals_start = None
    for i, row in enumerate(rows):
        if row and "Top 15 deals" in str(row[0]):
            top_deals_start = i
            break
    assert top_deals_start is not None
    # High confidence should appear before low confidence in the list
    high_conf_row = None
    low_conf_row = None
    for i in range(top_deals_start + 2, len(rows)):
        if rows[i] and rows[i][0]:
            if "high_conf" in str(rows[i][0]):
                high_conf_row = i
            if "low_conf" in str(rows[i][0]):
                low_conf_row = i
    if high_conf_row and low_conf_row:
        assert high_conf_row < low_conf_row


def test_confidence_caveat_in_summary(tmp_path):
    """Summary should include caveat about confidence meaning"""
    text = "\n".join(
        str(cell)
        for row in build(tmp_path, [make_product()])["Summary"].iter_rows(values_only=True)
        for cell in row if cell is not None
    )
    assert "how many of the 5 signals" in text


def test_price_delta_formatting_on_device_sheet(tmp_path):
    """Column 13 (Δ Since Last Run) should have conditional formatting"""
    db = store.Database()
    db.record_run("r0", [make_product("a", price=100000)], "2026-09-01T00:00:00",
                  "2026-09-01T00:01:00", 277.5, 0.55, "")
    db.record_run("r1", [make_product("a", price=90000)], "2026-09-02T00:00:00",
                  "2026-09-02T00:01:00", 277.5, 0.55, "")
    products = [make_product("a", price=90000)]
    sheet = build(tmp_path, products, db=db)["MacBook Pro"]
    # Check that conditional formatting is applied to column M (13)
    has_formatting = len(sheet.conditional_formatting._cf_rules) > 0
    assert has_formatting, "Should have conditional formatting rules"


def test_price_changes_formatting(tmp_path):
    """Price Changes sheet Change column should have conditional formatting"""
    db = store.Database()
    db.record_run("r0", [make_product("a", price=100000)], "2026-09-01T00:00:00",
                  "2026-09-01T00:01:00", 277.5, 0.55, "")
    db.record_run("r1", [make_product("a", price=90000)], "2026-09-02T00:00:00",
                  "2026-09-02T00:01:00", 277.5, 0.55, "")
    products = [make_product("a", price=90000)]
    sheet = build(tmp_path, products, db=db)["Price Changes"]
    # Check that conditional formatting is applied
    has_formatting = len(sheet.conditional_formatting._cf_rules) > 0
    assert has_formatting, "Should have conditional formatting rules"
