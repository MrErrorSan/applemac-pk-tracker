from scraper import config
from scraper.normalize import (
    Product, clean, normalize, parse_capacity, parse_cores,
    parse_price, parse_screen_size, slugify,
)
from scraper.parse import parse_category


def fixture(name):
    return (config.FIXTURE_DIR / name).read_text(encoding="utf-8")


def test_clean_maps_placeholder_to_none():
    assert clean("•") is None
    assert clean("") is None
    assert clean(None) is None
    assert clean("  Silver  ") == "Silver"


def test_clean_normalises_non_breaking_hyphen():
    assert clean("6.9‑inch") == "6.9-inch"


def test_parse_capacity():
    assert parse_capacity("1TB") == 1024
    assert parse_capacity("512GB") == 512
    assert parse_capacity("8TB") == 8192
    assert parse_capacity("32GB") == 32
    assert parse_capacity("•") is None
    assert parse_capacity("banana") is None


def test_parse_cores_handles_both_site_formats():
    assert parse_cores("10 Core CPU") == 10
    assert parse_cores("5‑core GPU") == 5
    assert parse_cores("6‑core CPU with 2 performance and 4 efficiency cores") == 6
    assert parse_cores("•") is None


def test_parse_screen_size_handles_both_site_formats():
    assert parse_screen_size("14 Inches") == 14.0
    assert parse_screen_size("6.9‑inch") == 6.9
    assert parse_screen_size("•") is None


def test_parse_price_handles_double_space_and_commas():
    assert parse_price("PKR 772,000") == 772000
    assert parse_price("PKR  930,000") == 930000
    assert parse_price(None) is None
    assert parse_price("PKR") is None


def test_slugify():
    assert slugify("M4 Pro") == "m4_pro"
    assert slugify("6.9-inch") == "6_9_inch"


def test_normalize_macbook_uses_data_ssd_for_storage():
    raw = parse_category(fixture("macbook-pro-14.html"), "macbook-pro-14")[0]
    product = normalize(raw, "macbook_pro")
    assert product.price == 772000
    assert product.old_price == 772000
    assert product.ram_gb == 32
    assert product.storage_gb == 1024
    assert product.chip == "M5"
    assert product.cpu_cores == 10
    assert product.gpu_cores == 10
    assert product.screen_size == 14.0
    assert product.color == "Silver"
    assert product.family == "macbook_pro"


def test_normalize_iphone_uses_data_storage_for_storage():
    raw = parse_category(fixture("iphone-17-pro-max.html"), "iphone-17-pro-max")[0]
    product = normalize(raw, "iphone")
    assert product.price == 892999
    assert product.old_price == 930000
    assert product.storage_gb == 2048        # from data-storage, not data-ssd
    assert product.ram_gb == 12
    assert product.chip == "A19 Pro"
    assert product.screen_size == 6.9
    assert product.color == "Silver, Cosmic Orange, Deep Blue"


def test_model_group_and_config_key_are_stable():
    raw = parse_category(fixture("macbook-pro-14.html"), "macbook-pro-14")[0]
    product = normalize(raw, "macbook_pro")
    assert product.model_group == "macbook_pro_scr14_0_chipm5"
    assert product.config_key == "macbook_pro_scr14_0_chipm5_ram32_ssd1024"


def test_config_key_prevents_collision_when_ram_or_storage_missing():
    """Ensure config_key is unambiguous even when RAM or storage is missing."""
    raw = parse_category(fixture("macbook-pro-14.html"), "macbook-pro-14")[0]

    # Product with RAM but no storage
    ram_only = type(raw)(**{**raw.__dict__, "attrs": {**raw.attrs, "data-ssd": None, "data-storage": None}})
    product_ram_only = normalize(ram_only, "macbook_pro")

    # Product with storage but no RAM
    storage_only = type(raw)(**{**raw.__dict__, "attrs": {**raw.attrs, "data-ram": None}})
    product_storage_only = normalize(storage_only, "macbook_pro")

    # Keys must be different to prevent ambiguity
    assert product_ram_only.config_key != product_storage_only.config_key, \
        f"config_key collision: ram_only={product_ram_only.config_key}, storage_only={product_storage_only.config_key}"


def test_products_with_same_config_share_a_config_key():
    products = [
        normalize(r, "macbook_pro")
        for r in parse_category(fixture("macbook-pro-14.html"), "macbook-pro-14")
    ]
    keys = {p.config_key for p in products if p}
    assert len(keys) < len(products), "some configs should collide for peer comparison"


def test_normalize_returns_none_without_a_price():
    raw = parse_category(fixture("macbook-pro-14.html"), "macbook-pro-14")[0]
    priceless = type(raw)(**{**raw.__dict__, "price_attr": None,
                             "new_price_text": None})
    assert normalize(priceless, "macbook_pro") is None


def test_every_fixture_product_normalizes():
    for name, family in (("macbook-pro-14.html", "macbook_pro"),
                         ("iphone-17-pro-max.html", "iphone")):
        for raw in parse_category(fixture(name), name.replace(".html", "")):
            assert isinstance(normalize(raw, family), Product)
