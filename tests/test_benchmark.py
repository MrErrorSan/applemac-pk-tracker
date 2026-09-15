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


def test_landed_pkr_arithmetic():
    assert benchmark.landed_pkr(1000, 277.5, 0.55) == 430125


def test_landed_pkr_returns_integer():
    assert isinstance(benchmark.landed_pkr(1599, 277.757506, 0.55), int)


def test_get_fx_rate_uses_live_value_and_caches_it(tmp_path):
    cache = tmp_path / "fx_cache.json"
    fetcher = FakeFetcher({"result": "success", "rates": {"PKR": 277.75}})
    rate, stale = benchmark.get_fx_rate(fetcher, cache)
    assert rate == 277.75
    assert stale is False
    assert json.loads(cache.read_text())["rate"] == 277.75


def test_get_fx_rate_falls_back_to_cache(tmp_path):
    cache = tmp_path / "fx_cache.json"
    cache.write_text(json.dumps({"rate": 270.0, "fetched_at": "2026-09-01"}))
    rate, stale = benchmark.get_fx_rate(FakeFetcher(error=RuntimeError("down")), cache)
    assert rate == 270.0
    assert stale is True


def test_get_fx_rate_raises_without_live_or_cache(tmp_path):
    with pytest.raises(benchmark.BenchmarkError):
        benchmark.get_fx_rate(FakeFetcher(error=RuntimeError("down")),
                              tmp_path / "missing.json")


def test_benchmark_for_known_config():
    product = make_product(config_key="grp_8_256")
    result = benchmark.benchmark_for(product, {"grp_8_256": 1000}, 277.5, 0.55)
    assert result == 430125


def test_benchmark_for_unknown_config_is_none():
    product = make_product(config_key="unknown_key")
    assert benchmark.benchmark_for(product, {"grp_8_256": 1000}, 277.5, 0.55) is None


def test_meta_keys_are_ignored():
    product = make_product(config_key="_meta")
    assert benchmark.benchmark_for(product, {"_meta": {"note": "x"}}, 277.5, 0.55) is None


def test_missing_keys_lists_gaps_without_duplicates():
    products = [make_product("a", config_key="k1"), make_product("b", config_key="k1"),
                make_product("c", config_key="k2")]
    assert benchmark.missing_keys(products, {"k1": 999}) == ["k2"]


def test_load_msrp_skips_meta(tmp_path):
    path = tmp_path / "msrp.json"
    path.write_text(json.dumps({"_meta": {"note": "x"}, "k1": 1599}))
    assert benchmark.load_msrp(path) == {"k1": 1599}
