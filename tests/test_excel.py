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
