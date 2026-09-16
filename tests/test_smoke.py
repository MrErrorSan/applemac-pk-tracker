"""Browser smoke test: drives the real dashboard in a real browser.

Deselected by default, exactly like the `live` marker. Run explicitly:

    uv run python -m pytest -m smoke

Builds its own `web/`-shaped fixture directory from the committed HTML
fixtures via the project's own parse -> normalize -> score -> report
pipeline, then serves it with `scraper.server` and points a real browser
at it. No network access: not to applemac.pk, and not to fetch a browser
driver. If Playwright is not already installed in this environment, every
test in this file is skipped with instructions rather than silently doing
nothing (and it is never added as a project dependency for that reason).
"""
import dataclasses
import datetime as dt
import http.server
import threading

import pytest

from scraper import normalize as normalize_mod
from scraper import parse, report, score, server, store
from scraper.config import FIXTURE_DIR, WEB_DIR

pytestmark = pytest.mark.smoke

XSS_NAME = '<img src=x onerror=alert(1)>"Deal" & <b>Special</b> Product'
XSS_SLUG = "xss-smoke-test-product"


def _fixture_products():
    """Real product data from committed fixtures, plus one XSS-payload name.

    Exercises the real render path with real specs/prices and zero network
    use, and pins the DOM-level HTML-escaping of a hostile product name -
    something a unit test on the JSON alone cannot verify.
    """
    macbook_html = (FIXTURE_DIR / "macbook-pro-14.html").read_text(encoding="utf-8")
    iphone_html = (FIXTURE_DIR / "iphone-17-pro-max.html").read_text(encoding="utf-8")

    products = []
    for raw in parse.parse_category(macbook_html, "macbook-pro-14"):
        product = normalize_mod.normalize(raw, "macbook_pro")
        if product is not None:
            products.append(product)
    for raw in parse.parse_category(iphone_html, "iphone-17-pro-max"):
        product = normalize_mod.normalize(raw, "iphone")
        if product is not None:
            products.append(product)

    assert products, "fixtures produced no usable products"

    products.append(dataclasses.replace(
        products[0],
        slug=XSS_SLUG,
        name=XSS_NAME,
        url="https://applemac.pk/product/" + XSS_SLUG,
    ))
    return products


@pytest.fixture(scope="module")
def dashboard_site(tmp_path_factory):
    """A temporary web/ directory served by the project's own HTTP server."""
    web_dir = tmp_path_factory.mktemp("smoke-web")
    (web_dir / "data").mkdir()
    (web_dir / "index.html").write_bytes((WEB_DIR / "index.html").read_bytes())

    products = _fixture_products()

    db = store.Database()
    started_at = dt.datetime.now(dt.timezone.utc).isoformat()
    db.record_run("smoke-run", products, started_at, started_at, 278.0, 0.55, "")
    scores = score.score_all(products, db, {})
    meta = {
        "run_id": "smoke-run",
        "generated_at": started_at,
        "fx_rate": 278.0,
        "fx_stale": False,
        "duty_percent": 0.55,
        "missing_msrp": [],
        "product_count": len(products),
        "notes": [],
        "benchmarks": {},
    }
    report.write_latest(products, scores, db, meta, web_dir / "data" / "latest.json")
    report.write_history(db, web_dir / "data" / "history.json")

    httpd = http.server.HTTPServer(("127.0.0.1", 0), server.make_handler(web_dir))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{httpd.server_port}"
    try:
        yield base_url, products
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


@pytest.fixture(scope="module")
def browser_instance():
    # Imported here, not at module level: this file must still *import*
    # cleanly when playwright is absent, so that `-m "not smoke"` can
    # deselect these tests normally instead of the whole module being
    # reported as skipped during collection.
    playwright_sync_api = pytest.importorskip(
        "playwright.sync_api",
        reason=(
            "no browser driver available for the smoke test - install with "
            "`uv add --group dev playwright` and then "
            "`uv run playwright install chromium`"
        ),
    )
    with playwright_sync_api.sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch()
        except Exception as error:  # noqa: BLE001 - reported via skip, not a failure
            pytest.skip(
                "Playwright is installed but no Chromium browser is available - "
                f"run `uv run playwright install chromium` ({error})"
            )
        try:
            yield browser
        finally:
            browser.close()


@pytest.fixture
def page(browser_instance, dashboard_site):
    """A fresh page per test, already loaded and rendered, plus any dialogs."""
    base_url, _products = dashboard_site
    pg = browser_instance.new_page()
    dialogs = []
    pg.on("dialog", lambda d: (dialogs.append(d.message), d.dismiss()))
    pg.goto(base_url + "/")
    pg.wait_for_selector("#rows tr")
    try:
        yield pg, dialogs
    finally:
        pg.close()


def test_row_count_matches_json(page, dashboard_site):
    pg, _dialogs = page
    _base_url, products = dashboard_site
    assert pg.locator("#rows tr").count() == len(products)


def test_top_deals_cards_render_without_zero_price(page, dashboard_site):
    pg, _dialogs = page
    _base_url, products = dashboard_site
    cards = pg.locator("#cards .card")
    assert cards.count() == min(6, len(products))
    prices = cards.locator(".price").all_inner_texts()
    assert prices
    assert all(text.strip() != "PKR 0" for text in prices)


def test_apple_landed_wording_present_and_no_forbidden_phrase(page):
    pg, _dialogs = page
    content = pg.content()
    assert "Est. Apple Landed" in content
    assert "Apple Price" not in content


def test_refresh_button_visible_in_live_mode(page):
    pg, _dialogs = page
    assert pg.locator("#refresh").is_visible()


def test_sorting_by_price_column_reorders_rows_cheapest_first(page, dashboard_site):
    pg, _dialogs = page
    _base_url, products = dashboard_site
    initial_first_row = pg.locator("#rows tr").first.inner_text()

    price_header = pg.locator('th[data-key="price"]')
    price_header.click()  # 1st click: descending (new column)
    price_header.click()  # 2nd click: toggles to ascending

    reordered_first_row = pg.locator("#rows tr").first.inner_text()
    assert reordered_first_row != initial_first_row

    first_row_cells = pg.locator("#rows tr").first.locator("td").all_inner_texts()
    cheapest_price = min(p.price for p in products)
    assert f"{cheapest_price:,}" in first_row_cells[1]


def test_xss_product_name_renders_as_literal_text(page):
    pg, dialogs = page
    # The payload must never become a real element (no <img> was created).
    assert pg.locator("img[src='x']").count() == 0
    # ...but its literal, escaped text must still be visible in the table.
    assert XSS_NAME in pg.locator("#rows").inner_text()
    assert dialogs == []
