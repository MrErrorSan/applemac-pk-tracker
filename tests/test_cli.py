import pytest

from scraper import cli, config, store
from scraper.normalize import Product
from tests.test_store import make_product


def fixture(name):
    return (config.FIXTURE_DIR / name).read_text(encoding="utf-8")


class StubFetcher:
    """Serves fixture HTML per category slug."""

    def __init__(self, pages, fx=None):
        self.pages = pages
        self.fx = fx or {"result": "success", "rates": {"PKR": 277.75}}

    def fetch_category(self, slug):
        if slug not in self.pages:
            return fixture("empty-category.html")
        return self.pages[slug]

    def fetch_fx(self, url):
        return self.fx

    def fetch_sitemap(self):
        return SITEMAP


SITEMAP = """<?xml version="1.0"?>
<urlset><url><loc>https://applemac.pk/product/apple-iphone-17-pro-max-2tb</loc></url>
<url><loc>https://applemac.pk/product/apple-iphone-99-unseen</loc></url>
<url><loc>https://applemac.pk/product/macbook-air-m4-ignored</loc></url></urlset>"""


def test_coverage_gaps_reports_iphone_slugs_no_category_yielded():
    gaps = cli.coverage_gaps(SITEMAP, {"apple-iphone-17-pro-max-2tb"})
    assert gaps == ["apple-iphone-99-unseen"]


def test_coverage_gaps_ignores_non_matching_products():
    gaps = cli.coverage_gaps(SITEMAP, set())
    assert "macbook-air-m4-ignored" not in gaps


def test_coverage_gaps_is_empty_when_everything_collected():
    assert cli.coverage_gaps(SITEMAP, {"apple-iphone-17-pro-max-2tb",
                                       "apple-iphone-99-unseen"}) == []


def test_coverage_gaps_excludes_accessories_containing_iphone():
    sitemap = """<?xml version="1.0"?>
    <urlset><url><loc>https://applemac.pk/product/apple-18w-usb-c-iphone-charger</loc></url>
    <url><loc>https://applemac.pk/product/apple-iphone-11-4gb-ram-128gb-storage</loc></url></urlset>"""
    gaps = cli.coverage_gaps(sitemap, set())
    assert "apple-18w-usb-c-iphone-charger" not in gaps
    assert "apple-iphone-11-4gb-ram-128gb-storage" in gaps


def test_coverage_gaps_includes_iphone_air_handsets():
    sitemap = """<?xml version="1.0"?>
    <urlset><url><loc>https://applemac.pk/product/apple-iphone-air-256gb</loc></url></urlset>"""
    assert cli.coverage_gaps(sitemap, set()) == ["apple-iphone-air-256gb"]


def test_coverage_gaps_excludes_accessories_under_a_numbered_iphone_line():
    sitemap = """<?xml version="1.0"?>
    <urlset>
    <url><loc>https://applemac.pk/product/apple-18w-usb-c-iphone-charger</loc></url>
    <url><loc>https://applemac.pk/product/iphone-16-case-clear</loc></url>
    <url><loc>https://applemac.pk/product/apple-iphone-17-pro-max-2tb</loc></url>
    <url><loc>https://applemac.pk/product/apple-iphone-air-256gb</loc></url>
    </urlset>"""
    gaps = cli.coverage_gaps(sitemap, set())
    assert "apple-18w-usb-c-iphone-charger" not in gaps
    assert "iphone-16-case-clear" not in gaps
    assert "apple-iphone-17-pro-max-2tb" in gaps
    assert "apple-iphone-air-256gb" in gaps


SE_LEAK_HTML = """
<div id="main_categoryinner">
  <div class="pdt" data-price="119999" data-ram="3" data-storage="64">
    <a href="/product/iphone-se-2020-64gb"><h3 class="product-title-name">iPhone SE (2020)</h3></a>
  </div>
  <div class="pdt" data-price="250000" data-ram="6" data-storage="128">
    <a href="/product/iphone-17-128gb"><h3 class="product-title-name">iPhone 17</h3></a>
  </div>
</div>
"""


def test_collect_excludes_products_matching_exclude_slug_patterns():
    fetcher = StubFetcher({"iphone": SE_LEAK_HTML})
    products, notes = cli.collect(fetcher, store.Database(), {"iphone": "iphone"})
    assert {p.slug for p in products} == {"iphone-17-128gb"}
    assert any("excluded by slug pattern" in n for n in notes)


def test_collect_dedupes_slugs_across_categories():
    html = fixture("iphone-17-pro-max.html")
    fetcher = StubFetcher({"iphone-17-pro-max": html, "iphone": html})
    products, _ = cli.collect(
        fetcher, store.Database(),
        {"iphone-17-pro-max": "iphone", "iphone": "iphone"})
    assert len(products) == 4          # not 8
    assert len({p.slug for p in products}) == 4


def test_collect_allows_empty_category_never_seen_before():
    fetcher = StubFetcher({})
    products, notes = cli.collect(fetcher, store.Database(),
                                  {"iphone-16-series": "iphone"})
    assert products == []
    assert any("empty" in n for n in notes)


def test_collect_aborts_when_previously_populated_category_empties():
    db = store.Database()
    db.record_run("r0", [make_product("a")], "2026-09-01T00:00:00",
                  "2026-09-01T00:01:00", 277.5, 0.55, "")
    fetcher = StubFetcher({})
    with pytest.raises(cli.RunAborted) as exc:
        cli.collect(fetcher, db, {"macbook-pro-14": "macbook_pro"})
    assert "macbook-pro-14" in str(exc.value)


def test_collect_aborts_on_large_count_drop():
    db = store.Database()
    previous = [make_product(f"p{i}") for i in range(10)]
    db.record_run("r0", previous, "2026-09-01T00:00:00", "2026-09-01T00:01:00",
                  277.5, 0.55, "")
    fetcher = StubFetcher({"macbook-pro-14": fixture("iphone-17-pro-max.html")})
    with pytest.raises(cli.RunAborted) as exc:
        cli.collect(fetcher, db, {"macbook-pro-14": "macbook_pro"})
    assert "dropped" in str(exc.value).lower()


def test_failed_run_writes_nothing(tmp_path):
    db = store.Database()
    db.record_run("r0", [make_product("a")], "2026-09-01T00:00:00",
                  "2026-09-01T00:01:00", 277.5, 0.55, "")
    store.save(db, tmp_path)
    before = (tmp_path / "history.csv").read_text()

    class Broken:
        def fetch_category(self, slug):
            raise RuntimeError("network down")

        def fetch_fx(self, url):
            return {"result": "success", "rates": {"PKR": 277.75}}

    with pytest.raises(Exception):
        cli.run(fetcher=Broken(), data_dir=tmp_path, web_dir=tmp_path / "web")

    assert (tmp_path / "history.csv").read_text() == before


def test_successful_run_appends_history_and_writes_outputs(tmp_path):
    fetcher = StubFetcher({"macbook-pro-14": fixture("macbook-pro-14.html")})
    web = tmp_path / "web"
    meta = cli.run(fetcher=fetcher, data_dir=tmp_path, web_dir=web)

    assert meta["product_count"] == 58
    assert (tmp_path / "history.csv").exists()
    assert (web / "data" / "latest.json").exists()
    assert (web / "downloads" / "applemac-prices.xlsx").exists()
    assert (web / "downloads" / "prices.db").exists()


def test_two_runs_accumulate_history(tmp_path):
    fetcher = StubFetcher({"macbook-pro-14": fixture("macbook-pro-14.html")})
    web = tmp_path / "web"
    cli.run(fetcher=fetcher, data_dir=tmp_path, web_dir=web)
    cli.run(fetcher=fetcher, data_dir=tmp_path, web_dir=web)
    db = store.load(tmp_path)
    assert len(db.runs) == 2
    assert len(db.history) == 116


def _make_product(slug, category_slug):
    return Product(
        slug=slug, url=f"https://applemac.pk/product/{slug}", name=slug.upper(),
        family="macbook_pro", category_slug=category_slug, image_url=None,
        price=100000, old_price=None, ram_gb=8, storage_gb=256, chip="M4",
        cpu_cores=10, gpu_cores=10, screen_size=14.0, color="Silver",
        model_group="grp", config_key="grp_8_256",
    )


def test_partial_collect_success_then_later_abort_writes_nothing(tmp_path):
    # macbook-pro-14 (first in config.CATEGORIES) will succeed this run;
    # macbook-pro-16 (second) was previously populated and comes back empty,
    # so collect() aborts partway through. Nothing collected so far may reach
    # disk — the whole point of gathering everything before writing anything.
    db = store.Database()
    db.record_run("r0", [_make_product("a", "macbook-pro-14"),
                        _make_product("b", "macbook-pro-16")],
                  "2026-09-01T00:00:00", "2026-09-01T00:01:00", 277.5, 0.55, "")
    store.save(db, tmp_path)
    before = (tmp_path / "history.csv").read_text()

    fetcher = StubFetcher({"macbook-pro-14": fixture("macbook-pro-14.html")})
    with pytest.raises(cli.RunAborted):
        cli.run(fetcher=fetcher, data_dir=tmp_path, web_dir=tmp_path / "web")

    assert (tmp_path / "history.csv").read_text() == before


def test_post_save_failure_preserves_history_and_message(tmp_path, monkeypatch, capsys):
    fetcher = StubFetcher({"macbook-pro-14": fixture("macbook-pro-14.html")})
    web = tmp_path / "web"

    def boom(*args, **kwargs):
        raise RuntimeError("workbook exploded")

    monkeypatch.setattr(cli.excel, "build_workbook", boom)

    with pytest.raises(cli.RunOutputsFailed) as exc:
        cli.run(fetcher=fetcher, data_dir=tmp_path, web_dir=web)

    # The price history was already saved before excel.build_workbook ran.
    db = store.load(tmp_path)
    assert len(db.runs) == 1
    assert len(db.history) == 58

    # main()'s message for this failure must not claim nothing was written.
    captured_error = exc.value
    monkeypatch.setattr(cli, "run",
                        lambda force=False: (_ for _ in ()).throw(captured_error))
    code = cli.main(["run"])
    stderr = capsys.readouterr().err

    assert code == 1
    assert "Nothing was written" not in stderr
    assert "history.csv is intact" in stderr


def test_first_ever_run_has_no_fabricated_vs_history(tmp_path):
    """A first-ever run must not compare a product's price to its own snapshot."""
    import json

    fetcher = StubFetcher({"macbook-pro-14": fixture("macbook-pro-14.html")})
    web = tmp_path / "web"
    cli.run(fetcher=fetcher, data_dir=tmp_path, web_dir=web)

    latest = json.loads((web / "data" / "latest.json").read_text(encoding="utf-8"))
    for row in latest["products"]:
        assert row["scores"]["vs_history"] is None


def test_immediate_successive_runs_get_different_run_ids(tmp_path):
    fetcher = StubFetcher({"macbook-pro-14": fixture("macbook-pro-14.html")})
    web = tmp_path / "web"
    meta1 = cli.run(fetcher=fetcher, data_dir=tmp_path, web_dir=web)
    meta2 = cli.run(fetcher=fetcher, data_dir=tmp_path, web_dir=web)
    assert meta1["run_id"] != meta2["run_id"]
