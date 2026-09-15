import pytest

from scraper import config
from scraper.parse import ParseError, parse_category


def fixture(name):
    return (config.FIXTURE_DIR / name).read_text(encoding="utf-8")


def test_parse_category_extracts_fields_and_handles_edge_cases():
    macbooks = parse_category(fixture("macbook-pro-14.html"), "macbook-pro-14")
    assert len(macbooks) == 58
    assert len({p.slug for p in macbooks}) == 58  # unique within category

    first = macbooks[0]
    assert first.slug == (
        "macbook-pro-14-m5-mj3e4-10-core-cpu-10-core-gpu-32gb-1tb-silver"
    )
    assert first.url == f"https://applemac.pk/product/{first.slug}"
    assert first.name == (
        "Macbook Pro 14 M5 MJ3E4 10 Core CPU 10 Core GPU 32GB 1TB Silver"
    )
    assert first.price_attr == "772000"
    assert first.new_price_text == "PKR 772,000"
    assert first.old_price_text == "PKR  772,000"   # note the double space
    assert first.attrs["data-ram"] == "32GB"
    assert first.attrs["data-ssd"] == "1TB"
    assert first.attrs["data-processor"] == "M5"
    assert first.attrs["data-screensize"] == "14 Inches"
    assert first.category_slug == "macbook-pro-14"

    iphones = parse_category(fixture("iphone-17-pro-max.html"), "iphone-17-pro-max")
    assert len(iphones) == 4
    first_iphone = iphones[0]
    assert first_iphone.slug == "apple-iphone-17-pro-max-2tb"
    assert first_iphone.price_attr == "892999"
    assert first_iphone.attrs["data-storage"] == "2TB"
    assert first_iphone.attrs["data-ssd"] == "•"          # null placeholder
    assert first_iphone.attrs["data-screensize"] == "6.9‑inch"  # U+2011
    assert first_iphone.old_price_text == "PKR  930,000"

    assert parse_category(fixture("empty-category.html"), "iphone-16-series") == []

    with pytest.raises(ParseError):
        parse_category("<html><body><p>nothing here</p></body></html>", "x")


def test_deduplicates_across_cards_keeping_first():
    """Verify that cross-card deduplication keeps the first occurrence.

    Regression test: this fails if dedup-by-slug is removed from parse_category.
    """
    html = '''
    <html>
    <body>
    <div id="main_categoryinner">
        <div class="pdt" data-price="100">
            <a href="https://applemac.pk/product/test-slug">
                <img src="https://example.com/img1.jpg" />
            </a>
            <h3 class="product-title-name">First Card</h3>
            <span class="new-price">PKR 100</span>
        </div>
        <div class="pdt" data-price="200">
            <a href="https://applemac.pk/product/test-slug">
                <img src="https://example.com/img2.jpg" />
            </a>
            <h3 class="product-title-name">Second Card</h3>
            <span class="new-price">PKR 200</span>
        </div>
    </div>
    </body>
    </html>
    '''
    products = parse_category(html, "test-category")
    assert len(products) == 1
    assert products[0].slug == "test-slug"
    assert products[0].price_attr == "100"  # from first card
