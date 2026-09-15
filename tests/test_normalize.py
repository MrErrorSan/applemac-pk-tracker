import pytest

from scraper import config
from scraper.normalize import (
    Product, clean, normalize, parse_capacity, parse_cores,
    parse_price, parse_screen_size, slugify,
)
from scraper.parse import parse_category


def fixture(name):
    return (config.FIXTURE_DIR / name).read_text(encoding="utf-8")


def test_clean_and_parsing_helpers():
    # clean()
    assert clean("•") is None
    assert clean("") is None
    assert clean(None) is None
    assert clean("  Silver  ") == "Silver"
    assert clean("6.9‑inch") == "6.9-inch"   # non-breaking hyphen normalised

    # parse_capacity()
    assert parse_capacity("1TB") == 1024
    assert parse_capacity("512GB") == 512
    assert parse_capacity("8TB") == 8192
    assert parse_capacity("32GB") == 32
    assert parse_capacity("•") is None
    assert parse_capacity("banana") is None

    # parse_cores()
    assert parse_cores("10 Core CPU") == 10
    assert parse_cores("5‑core GPU") == 5
    assert parse_cores("6‑core CPU with 2 performance and 4 efficiency cores") == 6
    assert parse_cores("•") is None

    # parse_screen_size()
    assert parse_screen_size("14 Inches") == 14.0
    assert parse_screen_size("6.9‑inch") == 6.9
    assert parse_screen_size("•") is None

    # parse_price()
    assert parse_price("PKR 772,000") == 772000
    assert parse_price("PKR  930,000") == 930000
    assert parse_price(None) is None
    # Stripping non-digits must not launder a negative or fractional
    # amount into a plausible positive integer.
    assert parse_price("-500") is None
    assert parse_price("930.50") is None
    assert parse_price("PKR -1,000") is None
    assert parse_price("PKR") is None

    # slugify()
    assert slugify("M4 Pro") == "m4_pro"
    assert slugify("6.9-inch") == "6_9_inch"


@pytest.mark.parametrize("fixture_name, category_slug, family, expected", [
    ("macbook-pro-14.html", "macbook-pro-14", "macbook_pro", dict(
        price=772000, old_price=772000, ram_gb=32, storage_gb=1024,
        chip="M5", cpu_cores=10, gpu_cores=10, screen_size=14.0,
        color="Silver", family="macbook_pro",
    )),
    ("iphone-17-pro-max.html", "iphone-17-pro-max", "iphone", dict(
        price=892999, old_price=930000, storage_gb=2048,  # from data-storage, not data-ssd
        ram_gb=12, chip="A19 Pro", screen_size=6.9,
        color="Silver, Cosmic Orange, Deep Blue",
    )),
], ids=["macbook_uses_data_ssd_for_storage", "iphone_uses_data_storage_for_storage"])
def test_normalize_family_specific_fields(fixture_name, category_slug, family, expected):
    raw = parse_category(fixture(fixture_name), category_slug)[0]
    product = normalize(raw, family)
    for field, value in expected.items():
        assert getattr(product, field) == value, field


def test_model_group_config_key_and_fixture_normalization():
    raw = parse_category(fixture("macbook-pro-14.html"), "macbook-pro-14")[0]
    product = normalize(raw, "macbook_pro")
    assert product.model_group == "macbook_pro_scr14_0_chipm5"
    assert product.config_key == "macbook_pro_scr14_0_chipm5_ram32_ssd1024"

    products = [
        normalize(r, "macbook_pro")
        for r in parse_category(fixture("macbook-pro-14.html"), "macbook-pro-14")
    ]
    keys = {p.config_key for p in products if p}
    assert len(keys) < len(products), "some configs should collide for peer comparison"

    for name, fam in (("macbook-pro-14.html", "macbook_pro"),
                       ("iphone-17-pro-max.html", "iphone")):
        for raw in parse_category(fixture(name), name.replace(".html", "")):
            assert isinstance(normalize(raw, fam), Product)


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


@pytest.mark.parametrize("price_attr, new_price_text, description", [
    (None, None, "no price at all"),
    ("-500", None, "negative price"),
    ("0", None, 'data-price="0" marks an unannounced / made-to-order listing, not a free item'),
])
def test_normalize_returns_none_for_invalid_price(price_attr, new_price_text, description):
    raw = parse_category(fixture("macbook-pro-14.html"), "macbook-pro-14")[0]
    invalid = type(raw)(**{**raw.__dict__, "price_attr": price_attr,
                            "new_price_text": new_price_text})
    assert normalize(invalid, "macbook_pro") is None, description
