from scraper import score, store
from tests.test_store import make_product


def test_percent_below_clamps_to_range():
    assert score.percent_below(50, 100) == 50.0
    assert score.percent_below(100, 100) == 0.0
    assert score.percent_below(200, 100) == 0.0     # above reference floors at 0
    assert score.percent_below(100, None) is None
    assert score.percent_below(100, 0) is None


def test_vs_apple_rewards_cheaper_than_benchmark():
    product = make_product("a", price=400000)
    scores = score.score_all([product], store.Database(), {"a": 500000})
    assert scores["a"].vs_apple == 20.0


def test_site_discount_signal():
    product = make_product("a", price=90000, old_price=100000)
    scores = score.score_all([product], store.Database(), {})
    assert scores["a"].site_discount == 10.0


def test_site_discount_is_none_when_old_equals_new():
    product = make_product("a", price=100000, old_price=100000)
    scores = score.score_all([product], store.Database(), {})
    assert scores["a"].site_discount is None


def test_vs_history_rewards_a_drop():
    db = store.Database()
    db.record_run("r1", [make_product("a", price=100000)], "2026-09-01T00:00:00",
                  "2026-09-01T00:01:00", 277.5, 0.55, "")
    product = make_product("a", price=80000)
    scores = score.score_all([product], db, {})
    assert scores["a"].vs_history == 20.0


def test_vs_peers_ranks_cheapest_highest():
    products = [make_product("a", price=100000, config_key="k"),
                make_product("b", price=200000, config_key="k"),
                make_product("c", price=300000, config_key="k")]
    scores = score.score_all(products, store.Database(), {})
    assert scores["a"].vs_peers == 100.0
    assert scores["c"].vs_peers == 0.0


def test_vs_peers_is_none_for_a_lone_product():
    scores = score.score_all([make_product("a", config_key="solo")],
                             store.Database(), {})
    assert scores["a"].vs_peers is None


def test_confidence_counts_available_signals():
    scores = score.score_all([make_product("a", price=100000, old_price=110000)],
                             store.Database(), {})
    assert scores["a"].confidence >= 1
    assert scores["a"].deal_score >= 0


def test_missing_signals_do_not_depress_score():
    """A product with only vs_apple=100 scores 100, not 30."""
    product = make_product("a", price=0 + 1, config_key="solo")
    scores = score.score_all([product], store.Database(), {"a": 1000000})
    assert scores["a"].vs_apple > 99
    assert scores["a"].deal_score > 99


def test_score_is_bounded():
    products = [make_product("a", price=1, config_key="k", old_price=10**9),
                make_product("b", price=10**9, config_key="k")]
    scores = score.score_all(products, store.Database(), {"a": 10**9})
    for s in scores.values():
        assert 0.0 <= s.deal_score <= 100.0
