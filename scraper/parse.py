"""HTML to RawProduct. Extracts strings verbatim; interprets nothing."""
from dataclasses import dataclass

from bs4 import BeautifulSoup


class ParseError(Exception):
    """The page no longer matches the structure we know how to read."""


@dataclass(frozen=True)
class RawProduct:
    slug: str
    url: str
    name: str
    image_url: str | None
    price_attr: str | None
    new_price_text: str | None
    old_price_text: str | None
    attrs: dict
    category_slug: str


def _text_or_none(node):
    return node.get_text(strip=True) if node is not None else None


def parse_category(html, category_slug):
    soup = BeautifulSoup(html, "html.parser")

    listing = soup.find(id="main_categoryinner")
    if listing is None:
        raise ParseError(
            f"{category_slug}: no #main_categoryinner listing container found"
        )

    cards = listing.find_all(
        lambda tag: tag.name == "div" and "pdt" in (tag.get("class") or [])
    )

    products = []
    seen = set()
    for card in cards:
        link = card.find("a", href=lambda h: h and "/product/" in h)
        if link is None:
            continue
        url = link["href"]
        slug = url.rstrip("/").split("/product/")[-1]
        if slug in seen:
            continue
        seen.add(slug)

        title = card.find("h3", class_="product-title-name")
        image = card.find("img")
        products.append(
            RawProduct(
                slug=slug,
                url=url,
                name=_text_or_none(title) or "",
                image_url=image["src"] if image and image.has_attr("src") else None,
                price_attr=card.get("data-price"),
                new_price_text=_text_or_none(card.find("span", class_="new-price")),
                old_price_text=_text_or_none(card.find("span", class_="old-price")),
                attrs={k: v for k, v in card.attrs.items() if k.startswith("data-")},
                category_slug=category_slug,
            )
        )
    return products
