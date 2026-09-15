from scraper import config


def test_every_category_maps_to_a_known_family():
    assert set(config.CATEGORIES.values()) <= set(config.FAMILIES)


def test_target_categories_present():
    for slug in ("macbook-pro-14", "macbook-pro-16",
                 "macbook-air-13", "macbook-air-15"):
        assert slug in config.CATEGORIES


def test_no_old_or_used_categories():
    for slug in config.CATEGORIES:
        assert "-old" not in slug
        assert "-used" not in slug


def test_weights_sum_to_one():
    assert abs(sum(config.WEIGHTS.values()) - 1.0) < 1e-9


def test_exclude_slug_patterns_covers_iphone_se():
    assert any("iphone-se" in p for p in config.EXCLUDE_SLUG_PATTERNS)
