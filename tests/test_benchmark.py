import json

import pytest

from scraper import benchmark
from tests.test_store import make_product


class FakeFetcher:
    def __init__(self, payload=None, error=None):
        self.payload, self.error = payload, error

    def fetch_fx(self, url):
        if self.error:
            raise self.error
        return self.payload


def test_landed_pkr():
    assert benchmark.landed_pkr(1000, 277.5, 0.55) == 430125
    assert isinstance(benchmark.landed_pkr(1599, 277.757506, 0.55), int)


def test_get_fx_rate_live_value_and_cache_fallback(tmp_path):
    # Live fetch succeeds -> value used and cached.
    cache = tmp_path / "fx_cache.json"
    fetcher = FakeFetcher({"result": "success", "rates": {"PKR": 277.75}})
    rate, stale = benchmark.get_fx_rate(fetcher, cache)
    assert rate == 277.75
    assert stale is False
    assert json.loads(cache.read_text())["rate"] == 277.75

    # Live fetch fails -> falls back to a valid cache, marked stale.
    cache2 = tmp_path / "fx_cache2.json"
    cache2.write_text(json.dumps({"rate": 270.0, "fetched_at": "2026-09-01"}))
    rate, stale = benchmark.get_fx_rate(FakeFetcher(error=RuntimeError("down")), cache2)
    assert rate == 270.0
    assert stale is True

    # No live fetch and no cache at all -> BenchmarkError.
    with pytest.raises(benchmark.BenchmarkError):
        benchmark.get_fx_rate(FakeFetcher(error=RuntimeError("down")),
                              tmp_path / "missing.json")


def test_get_fx_rate_cache_write_failure_does_not_discard_live_rate(tmp_path):
    """Fetch succeeds but cache write fails -> return fresh rate with is_stale False."""
    class FailingFetcher:
        def fetch_fx(self, url):
            return {"result": "success", "rates": {"PKR": 277.75}}

    class RichPath:
        """Path-like that succeeds on read, fails on write."""
        def __init__(self, path):
            self.path = path
        def exists(self):
            return self.path.exists()
        def read_text(self, encoding=None):
            return self.path.read_text(encoding=encoding)
        def write_text(self, content, encoding=None):
            raise PermissionError("disk read-only")
        @property
        def parent(self):
            return self.path.parent
        def mkdir(self, **kwargs):
            self.path.parent.mkdir(**kwargs)

    cache = RichPath(tmp_path / "fx_cache.json")
    rate, stale = benchmark.get_fx_rate(FailingFetcher(), cache)
    assert rate == 277.75
    assert stale is False


def test_get_fx_rate_bad_cache_raises_benchmark_error(tmp_path):
    """Corrupt or incomplete cache with a failing fetcher raises BenchmarkError,
    not a raw JSONDecodeError/KeyError traceback."""
    for cache_contents, description in [
        ("{invalid json", "corrupt JSON"),
        (json.dumps({"fetched_at": "2026-09-01"}), "missing 'rate' key"),
    ]:
        cache = tmp_path / "fx_cache.json"
        cache.write_text(cache_contents)
        with pytest.raises(benchmark.BenchmarkError):
            benchmark.get_fx_rate(FakeFetcher(error=RuntimeError("down")), cache)


def test_benchmark_for_and_missing_keys(tmp_path):
    product = make_product(config_key="grp_8_256")
    assert benchmark.benchmark_for(product, {"grp_8_256": 1000}, 277.5, 0.55) == 430125
    assert benchmark.benchmark_for(make_product(config_key="unknown_key"),
                                   {"grp_8_256": 1000}, 277.5, 0.55) is None
    assert benchmark.benchmark_for(make_product(config_key="_meta"),
                                   {"_meta": {"note": "x"}}, 277.5, 0.55) is None

    products = [make_product("a", config_key="k1"), make_product("b", config_key="k1"),
                make_product("c", config_key="k2")]
    assert benchmark.missing_keys(products, {"k1": 999}) == ["k2"]

    path = tmp_path / "msrp.json"
    path.write_text(json.dumps({"_meta": {"note": "x"}, "k1": 1599}))
    assert benchmark.load_msrp(path) == {"k1": 1599}


def test_benchmark_for_rejects_invalid_prices():
    product = make_product(config_key="k1")
    for bad_price, description in [
        (True, "boolean value (bool subclasses int but should not be a price)"),
        (0, "zero is rejected as a typo, not a valid benchmark"),
        (-100, "negative is rejected as a typo, not a valid benchmark"),
    ]:
        assert benchmark.benchmark_for(product, {"k1": bad_price}, 277.5, 0.55) is None, description
