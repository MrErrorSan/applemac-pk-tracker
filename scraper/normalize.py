"""RawProduct to Product. All string-to-value interpretation lives here."""
import re
from dataclasses import dataclass

from . import config

NON_BREAKING_HYPHEN = "‑"


@dataclass(frozen=True)
class Product:
    slug: str
    url: str
    name: str
    family: str
    category_slug: str
    image_url: str | None
    price: int
    old_price: int | None
    ram_gb: int | None
    storage_gb: int | None
    chip: str | None
    cpu_cores: int | None
    gpu_cores: int | None
    screen_size: float | None
    color: str | None
    model_group: str
    config_key: str


def clean(value):
    """Trim, normalise odd hyphens, and map the site's placeholder to None."""
    if value is None:
        return None
    text = value.replace(NON_BREAKING_HYPHEN, "-").strip()
    if not text or text == config.NULL_PLACEHOLDER:
        return None
    return text


def parse_capacity(text):
    """'1TB' -> 1024, '512GB' -> 512. Returns GB."""
    text = clean(text)
    if text is None:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)\s*(TB|GB)", text, re.IGNORECASE)
    if match is None:
        return None
    value = float(match.group(1))
    if match.group(2).upper() == "TB":
        value *= 1024
    return int(value)


def parse_cores(text):
    """'10 Core CPU' -> 10, '6-core CPU with 2 performance...' -> 6."""
    text = clean(text)
    if text is None:
        return None
    match = re.search(r"(\d+)\s*[-\s]?\s*core", text, re.IGNORECASE)
    return int(match.group(1)) if match else None


def parse_screen_size(text):
    """'14 Inches' -> 14.0, '6.9-inch' -> 6.9."""
    text = clean(text)
    if text is None:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)", text)
    return float(match.group(1)) if match else None


def parse_price(text):
    """'PKR  930,000' -> 930000."""
    text = clean(text)
    if text is None:
        return None
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else None


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "_", str(text).lower()).strip("_")


def normalize(raw, family):
    price = None
    if raw.price_attr:
        price = parse_price(raw.price_attr)
    if price is None:
        price = parse_price(raw.new_price_text)
    if price is None or price <= 0:
        # A non-positive price means the site has no real price to show
        # (data-price="0" marks unannounced / made-to-order listings). That
        # is the same "no usable price" case as a price that failed to
        # parse at all — never a real PKR 0 deal.
        return None

    old_price = parse_price(raw.old_price_text)
    attrs = raw.attrs

    # MacBooks put capacity in data-ssd; iPhones put it in data-storage.
    storage_gb = parse_capacity(attrs.get("data-ssd"))
    if storage_gb is None:
        storage_gb = parse_capacity(attrs.get("data-storage"))

    chip = clean(attrs.get("data-processor"))
    screen_size = parse_screen_size(attrs.get("data-screensize"))
    ram_gb = parse_capacity(attrs.get("data-ram"))

    screen_str = slugify(screen_size) if screen_size else "na"
    chip_str = slugify(chip) if chip else "na"
    ram_str = str(ram_gb) if ram_gb else "na"
    storage_str = str(storage_gb) if storage_gb else "na"

    model_group = f"{family}_scr{screen_str}_chip{chip_str}"
    config_key = f"{model_group}_ram{ram_str}_ssd{storage_str}"

    return Product(
        slug=raw.slug,
        url=raw.url,
        name=raw.name,
        family=family,
        category_slug=raw.category_slug,
        image_url=raw.image_url,
        price=price,
        old_price=old_price,
        ram_gb=ram_gb,
        storage_gb=storage_gb,
        chip=chip,
        cpu_cores=parse_cores(attrs.get("data-cpu")),
        gpu_cores=parse_cores(attrs.get("data-gpu")),
        screen_size=screen_size,
        color=clean(attrs.get("data-color")),
        model_group=model_group,
        config_key=config_key,
    )
