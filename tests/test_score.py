from scraper import score, store
from scraper.normalize import Product
from tests.test_store import make_product


def _product(slug, price, ram_gb=8, storage_gb=256, model_group="m1"):
    return Product(
        slug=slug, url=f"http://{slug}", name=slug.upper(), family="macbook_pro",
        category_slug="macbook-pro-14", image_url=None,
        price=price, old_price=None, ram_gb=ram_gb, storage_gb=storage_gb, chip="M4",
        cpu_cores=10, gpu_cores=10, screen_size=14.0, color="Silver",
        model_group=model_group, config_key=f"{model_group}_{ram_gb}_{storage_gb}",
    )


def test_scoring_signals():
    # percent_below
    assert score.percent_below(50, 100) == 50.0
    assert score.percent_below(100, 100) == 0.0
    assert score.percent_below(200, 100) == 0.0     # above reference floors at 0
    assert score.percent_below(100, None) is None
    assert score.percent_below(100, 0) is None

    # vs_apple
    product = make_product("a", price=400000)
    scores = score.score_all([product], store.Database(), {"a": 500000})
    assert scores["a"].vs_apple == 20.0

    # site_discount
    product = make_product("a", price=90000, old_price=100000)
    scores = score.score_all([product], store.Database(), {})
    assert scores["a"].site_discount == 10.0
    product = make_product("a", price=100000, old_price=100000)
    scores = score.score_all([product], store.Database(), {})
    assert scores["a"].site_discount is None

    # vs_history: rewards a drop, none on the run's own snapshot, and uses
    # prior history rather than the current run when that run is excluded.
    db = store.Database()
    db.record_run("r1", [make_product("a", price=100000)], "2026-09-01T00:00:00",
                  "2026-09-01T00:01:00", 277.5, 0.55, "")
    scores = score.score_all([make_product("a", price=80000)], db, {})
    assert scores["a"].vs_history == 20.0

    db2 = store.Database()
    db2.record_run("r1", [make_product("a", price=100000)], "2026-09-01T00:00:00",
                   "2026-09-01T00:01:00", 277.5, 0.55, "")
    scores2 = score.score_all([make_product("a", price=100000)], db2, {}, exclude_run_id="r1")
    assert scores2["a"].vs_history is None
    assert scores2["a"].confidence == 0

    db2.record_run("r2", [make_product("a", price=80000)], "2026-09-02T00:00:00",
                   "2026-09-02T00:01:00", 277.5, 0.55, "")
    scores3 = score.score_all([make_product("a", price=80000)], db2, {}, exclude_run_id="r2")
    assert scores3["a"].vs_history == 20.0

    # vs_peers: ranks cheapest highest, and a zero-priced peer must not
    # flatten the real members' range.
    products = [make_product("a", price=100000, config_key="k"),
                make_product("b", price=200000, config_key="k"),
                make_product("c", price=300000, config_key="k")]
    scores = score.score_all(products, store.Database(), {})
    assert scores["a"].vs_peers == 100.0
    assert scores["c"].vs_peers == 0.0

    products = [make_product("a", price=0, config_key="k"),
                make_product("b", price=100000, config_key="k"),
                make_product("c", price=300000, config_key="k")]
    scores = score.score_all(products, store.Database(), {})
    assert scores["b"].vs_peers == 100.0
    assert scores["c"].vs_peers == 0.0


def test_confidence_bounds_and_spec_value():
    # confidence counts exactly the available signals
    scores = score.score_all([make_product("a", price=100000, old_price=110000)],
                             store.Database(), {})
    assert scores["a"].confidence == 1  # exactly one signal: site_discount
    assert scores["a"].deal_score >= 0

    # deal_score always stays in [0, 100], including extreme inputs
    products = [make_product("a", price=1, config_key="k", old_price=10**9),
                make_product("b", price=10**9, config_key="k")]
    scores = score.score_all(products, store.Database(), {"a": 10**9})
    for s in scores.values():
        assert 0.0 <= s.deal_score <= 100.0

    # spec_value: more storage per rupee scores higher within a model_group,
    # but a lone product in its model_group can't be ranked.
    a = _product("a", price=500000, ram_gb=8, storage_gb=256)
    b = _product("b", price=500000, ram_gb=8, storage_gb=512)
    scores = score.score_all([a, b], store.Database(), {})
    assert scores["b"].spec_value > scores["a"].spec_value

    solo = Product(
        slug="solo", url="http://solo", name="Solo", family="macbook_pro",
        category_slug="macbook-pro-14", image_url=None,
        price=500000, old_price=None, ram_gb=8, storage_gb=256, chip="M4",
        cpu_cores=10, gpu_cores=10, screen_size=14.0, color="Silver",
        model_group="solo_group", config_key="solo_group_8_256",
    )
    scores = score.score_all([solo], store.Database(), {})
    assert scores["solo"].spec_value is None

    # _rank_within_group: a non-positive value must not compress the real
    # members' range, and fewer than two usable values yields no ranker.
    ranker = score._rank_within_group([0, 100, 200, 300])
    assert ranker is not None
    assert ranker(100) == 100.0
    assert ranker(300) == 0.0
    assert ranker(200) == 50.0
    assert score._rank_within_group([0, 100]) is None
    assert score._rank_within_group([0, 0]) is None


def test_vs_peers_is_none_for_a_lone_product():
    scores = score.score_all([make_product("a", config_key="solo")],
                             store.Database(), {})
    assert scores["a"].vs_peers is None


def test_missing_signals_do_not_depress_score():
    """A product with only vs_apple=100 scores 100, not a fraction of it —
    this fails against the old summing implementation that divided by the
    number of possible signals rather than the number of available ones."""
    product = make_product("a", price=0 + 1, config_key="solo")
    scores = score.score_all([product], store.Database(), {"a": 1000000})
    assert scores["a"].vs_apple > 99
    assert scores["a"].deal_score > 99


def test_zero_signals_yields_zero_confidence_and_score():
    """Product with no benchmark, no history, no peers, no old_price gets confidence=0."""
    scores = score.score_all([make_product("a", price=100000)],
                             store.Database(), {})
    assert scores["a"].confidence == 0
    assert scores["a"].deal_score == 0.0


def test_spec_value_does_not_penalize_higher_ram():
    """More RAM does not lower spec_value when price is proportionate — this
    fails against an implementation that simply sums RAM and storage."""
    a = _product("a", price=500000, ram_gb=16, storage_gb=256)
    b = _product("b", price=640000, ram_gb=24, storage_gb=256)
    scores = score.score_all([a, b], store.Database(), {})
    # b has 50% more RAM for 28% more price, roughly proportionate.
    # Should not be penalized compared to a.
    assert scores["b"].spec_value >= scores["a"].spec_value
