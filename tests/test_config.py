from scraper import config


def test_every_category_maps_to_a_known_family_and_excludes_old_or_used():
    """Every configured category must resolve to a real family, and no slug
    should sneak in an -old/-used variant (a real spec rule, not a tautology)."""
    assert set(config.CATEGORIES.values()) <= set(config.FAMILIES)
    for slug in config.CATEGORIES:
        assert "-old" not in slug
        assert "-used" not in slug
