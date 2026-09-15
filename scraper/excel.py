"""Multi-sheet workbook. Columns 1-9 are identity and price; 10+ are analysis."""
from openpyxl import Workbook
from openpyxl.formatting.rule import CellIsRule, ColorScaleRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

SHEETS = (
    ("MacBook Pro", ("macbook_pro",)),
    ("MacBook Air", ("macbook_air",)),
    ("iPhone", ("iphone",)),
)

HEADERS = [
    "Name", "Screen", "Chip", "RAM (GB)", "Storage (GB)", "CPU", "GPU", "Color",
    "Price (PKR)", "Old Price", "Est. Apple Landed", "vs Apple %",
    "Δ Since Last Run", "vs History", "vs Peers", "Spec Value",
    "Deal Score", "Confidence", "First Seen",
]
PRICE_COLUMNS = (9, 10, 11, 13)
DEAL_SCORE_COLUMN = 17


def _style_header(sheet):
    for cell in sheet[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = (
        f"A1:{get_column_letter(sheet.max_column)}{max(sheet.max_row, 1)}"
    )
    widths = {1: 52, 2: 9, 3: 12, 9: 14, 10: 14, 11: 18, 13: 16, 17: 12, 19: 20}
    for index, width in widths.items():
        sheet.column_dimensions[get_column_letter(index)].width = width


def build_workbook(products, scores, db, meta, path):
    workbook = Workbook()
    workbook.remove(workbook.active)

    _build_summary(workbook, products, scores, meta)

    previous = {}
    if db.previous_run():
        previous = {s.slug: s.price
                    for s in db.snapshots_for_run(db.previous_run().run_id).values()}

    for sheet_name, families in SHEETS:
        sheet = workbook.create_sheet(sheet_name)
        sheet.append(HEADERS)
        rows = sorted((p for p in products if p.family in families),
                      key=lambda p: p.price)
        for product in rows:
            score_row = scores[product.slug]
            benchmark = meta["benchmarks"].get(product.slug)
            before = previous.get(product.slug)
            sheet.append([
                product.name, product.screen_size, product.chip, product.ram_gb,
                product.storage_gb, product.cpu_cores, product.gpu_cores,
                product.color, product.price, product.old_price, benchmark,
                score_row.vs_apple,
                product.price - before if before is not None else None,
                score_row.vs_history, score_row.vs_peers, score_row.spec_value,
                score_row.deal_score, score_row.confidence,
                db.products.get(product.slug, {}).get("first_seen"),
            ])
            sheet.cell(row=sheet.max_row, column=1).hyperlink = product.url
            sheet.cell(row=sheet.max_row, column=1).font = Font(
                color="0563C1", underline="single")

        for row in sheet.iter_rows(min_row=2):
            for column in PRICE_COLUMNS:
                row[column - 1].number_format = "#,##0"

        if sheet.max_row > 1:
            letter = get_column_letter(DEAL_SCORE_COLUMN)
            sheet.conditional_formatting.add(
                f"{letter}2:{letter}{sheet.max_row}",
                ColorScaleRule(start_type="min", start_color="FFFFFF",
                               end_type="max", end_color="63BE7B"))

            # Green for price drops (negative delta), red for price rises (positive delta)
            delta_letter = get_column_letter(13)
            green_fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
            red_fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
            sheet.conditional_formatting.add(
                f"{delta_letter}2:{delta_letter}{sheet.max_row}",
                CellIsRule(operator="lessThan", formula=["0"], fill=green_fill))
            sheet.conditional_formatting.add(
                f"{delta_letter}2:{delta_letter}{sheet.max_row}",
                CellIsRule(operator="greaterThan", formula=["0"], fill=red_fill))
        _style_header(sheet)

    _build_changes(workbook, db, meta)
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(path)


def _build_summary(workbook, products, scores, meta):
    sheet = workbook.create_sheet("Summary")
    sheet.append(["applemac.pk Price Tracker"])
    sheet["A1"].font = Font(bold=True, size=14)
    sheet.append([])
    sheet.append(["Run ID", meta["run_id"]])
    sheet.append(["Generated", meta["generated_at"]])
    sheet.append(["USD to PKR rate", meta["fx_rate"],
                  "STALE - cached rate used" if meta["fx_stale"] else "live"])
    sheet.append(["Import duty assumption (%)", round(meta["duty_percent"] * 100, 1)])
    sheet.append(["Products tracked", len(products)])
    for sheet_name, families in SHEETS:
        count = sum(1 for p in products if p.family in families)
        sheet.append([f"  {sheet_name}", count])
    sheet.append([])
    sheet.append(["'Est. Apple Landed' = US MSRP x FX x (1 + duty). "
                  "An estimate, not an official or actual landed price."])
    sheet.append([])

    sheet.append(["Top 15 deals (by Deal Score)"])
    sheet[f"A{sheet.max_row}"].font = Font(bold=True)
    sheet.append(["Confidence shows how many of the 5 signals had data. A high score from 1 signal is weaker evidence than the same score from 4."])
    sheet.append(["Name", "Family", "Price (PKR)", "Deal Score", "Confidence"])

    # Filter products with confidence >= 1, sort by deal_score DESC, then confidence DESC
    ranked = sorted(
        (p for p in products if scores[p.slug].confidence >= 1),
        key=lambda p: (scores[p.slug].deal_score, scores[p.slug].confidence),
        reverse=True
    )

    if ranked:
        for product in ranked[:15]:
            sheet.append([product.name, product.family, product.price,
                          scores[product.slug].deal_score,
                          scores[product.slug].confidence])
            sheet.cell(row=sheet.max_row, column=3).number_format = "#,##0"
    else:
        sheet.append(["No products have enough data to rank yet - run again after the Apple MSRP table is populated and some price history exists."])

    sheet.append([])
    sheet.append([f"Configs with no Apple MSRP entry ({len(meta['missing_msrp'])})"])
    sheet[f"A{sheet.max_row}"].font = Font(bold=True)
    for key in meta["missing_msrp"]:
        sheet.append([key])
    sheet.column_dimensions["A"].width = 52
    sheet.column_dimensions["B"].width = 18


def _build_changes(workbook, db, meta):
    sheet = workbook.create_sheet("Price Changes")
    sheet.append(["Name", "Direction", "Previous", "Current", "Change", "Change %"])
    for change in db.changes_since(meta["run_id"]):
        product = db.products.get(change.slug, {})
        sheet.append([product.get("name", change.slug),
                      "DOWN" if change.delta < 0 else "UP",
                      change.old, change.new, change.delta, round(change.pct, 2)])
        for column in (3, 4, 5):
            sheet.cell(row=sheet.max_row, column=column).number_format = "#,##0"

    if sheet.max_row > 1:
        # Green for price drops (negative change), red for price rises (positive change)
        change_letter = get_column_letter(5)
        green_fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
        red_fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
        sheet.conditional_formatting.add(
            f"{change_letter}2:{change_letter}{sheet.max_row}",
            CellIsRule(operator="lessThan", formula=["0"], fill=green_fill))
        sheet.conditional_formatting.add(
            f"{change_letter}2:{change_letter}{sheet.max_row}",
            CellIsRule(operator="greaterThan", formula=["0"], fill=red_fill))

    _style_header(sheet)
