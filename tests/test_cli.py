import pytest

from scraper import cli, config, store
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
