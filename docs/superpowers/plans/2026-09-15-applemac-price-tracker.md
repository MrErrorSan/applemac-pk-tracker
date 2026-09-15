# applemac.pk Price Tracker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python scraper that tracks applemac.pk prices for MacBook Pro 14"/16", MacBook Air 13"/15" and current iPhones, keeps an append-only price history in git, produces a multi-sheet Excel workbook ranked by deal quality, and runs unattended daily via GitHub Actions with a dashboard on GitHub Pages.

**Architecture:** A pipeline of small, single-purpose modules — `fetch` → `parse` → `normalize` → `store` → `benchmark` → `score` → `excel`/`web`. Only `fetch` touches the network, so everything else is tested offline against committed HTML fixtures. Canonical state is append-only CSV in git; SQLite and Excel are regenerated artifacts.

**Tech Stack:** Python 3.13, `requests`, `beautifulsoup4`, `openpyxl`, `pytest`. Standard library for `sqlite3`, `http.server`, `csv`, `dataclasses`. GitHub Actions + GitHub Pages.

**Spec:** [`docs/superpowers/specs/2026-09-15-applemac-price-tracker-design.md`](../specs/2026-09-15-applemac-price-tracker-design.md)

## Global Constraints

- **Python 3.13**, standard library preferred. Only three third-party runtime packages: `requests`, `beautifulsoup4`, `openpyxl`. Plus `pytest` for tests.
- **Request politeness:** 1.5 s minimum between requests, descriptive `User-Agent`. Never fetch paths disallowed by robots.txt (`/index.php/`, `/?page=`, `/cart/`, `/public/`). Image URLs are stored as strings, never fetched.
- **Canonical storage is CSV in git.** `data/history.csv` is append-only — existing rows are never edited or deleted. SQLite and `.xlsx` are derived artifacts.
- **No network in tests** except the single opt-in `--live` test. Default `pytest` run must pass offline.
- **`•` (U+2022) is the site's null placeholder** in `data-*` attributes and must normalize to `None`.
- **`‑` (U+2011 non-breaking hyphen)** appears in iPhone attributes and must be normalized to ASCII `-` before parsing.
- **Failed runs must write nothing.** Abort, exit non-zero, leave previous data and dashboard intact.
- **Never label the Apple benchmark as an official price.** The column is `Est. Apple Landed` everywhere it appears.
- All money is **integer PKR**. No floats for currency.

---

## File Structure

| File | Responsibility |
|---|---|
| `scraper/config.py` | Category→family map, weights, tunables, paths. Pure data. |
| `scraper/fetch.py` | Rate-limited HTTP with retry. The only network module. |
| `scraper/parse.py` | HTML → `RawProduct`. No interpretation of values. |
| `scraper/normalize.py` | `RawProduct` → `Product`. All string→typed-value logic. |
| `scraper/store.py` | CSV load/save, `Database` queries, derived SQLite. |
| `scraper/benchmark.py` | Apple MSRP + FX → estimated landed PKR. |
| `scraper/score.py` | Five signals → composite deal score. |
| `scraper/excel.py` | Workbook builder. |
| `scraper/report.py` | `latest.json` / `history.json` for the dashboard. |
| `scraper/server.py` | Local dashboard server (live mode only). |
| `scraper/cli.py` | Orchestration, failure rules, argparse entry point. |
| `web/index.html` | Dual-mode dashboard (static + live). |
| `.github/workflows/scrape.yml` | Daily cron, commit, deploy Pages. |
| `.github/workflows/keepalive.yml` | Monthly no-op commit. |

Fixtures already committed at `tests/fixtures/`: `macbook-pro-14.html` (58 cards), `iphone-17-pro-max.html` (4 cards), `empty-category.html` (0 cards).

---

### Task 1: Project scaffolding and configuration

**Files:**
- Create: `requirements.txt`, `scraper/__init__.py`, `scraper/config.py`, `tests/__init__.py`, `pytest.ini`, `README.md`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `config.CATEGORIES: dict[str, str]` (category slug → family), `config.FAMILIES: tuple[str, ...]`, `config.WEIGHTS: dict[str, float]`, `config.DUTY_PERCENT: float`, `config.REQUEST_DELAY: float`, `config.USER_AGENT: str`, `config.BASE_URL: str`, `config.NULL_PLACEHOLDER: str`, and path constants `DATA_DIR`, `WEB_DIR`, `BUILD_DIR`, `FIXTURE_DIR`.

- [ ] **Step 1: Create `requirements.txt`**

```
requests>=2.32
beautifulsoup4>=4.12
openpyxl>=3.1
pytest>=8.0
```

- [ ] **Step 2: Create `pytest.ini`**

```ini
[pytest]
testpaths = tests
markers =
    live: hits the real network; deselected by default
addopts = -m "not live"
```

- [ ] **Step 3: Write the failing test**

Create `tests/test_config.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scraper'`

- [ ] **Step 5: Create `scraper/__init__.py` and `tests/__init__.py`**

Both empty files.

- [ ] **Step 6: Write `scraper/config.py`**

```python
"""Static configuration. Pure data, no logic."""
from pathlib import Path

BASE_URL = "https://applemac.pk"
USER_AGENT = (
    "applemac-price-tracker/1.0 "
    "(personal price tracker; contact via repository issues)"
)
REQUEST_DELAY = 1.5
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3

NULL_PLACEHOLDER = "•"  # the site's "no value" marker

FAMILIES = ("macbook_pro", "macbook_air", "iphone")

CATEGORIES = {
    "macbook-pro-14": "macbook_pro",
    "macbook-pro-16": "macbook_pro",
    "macbook-air-13": "macbook_air",
    "macbook-air-15": "macbook_air",
    "iphone-16": "iphone",
    "iphone-16-plus": "iphone",
    "iphone-16-pro": "iphone",
    "iphone-16-pro-max": "iphone",
    "iphone-16e": "iphone",
    "iphone-17": "iphone",
    "iphone-17-pro": "iphone",
    "iphone-17-pro-max": "iphone",
    "iphone-17e": "iphone",
    "iphone-18-pro": "iphone",
    "iphone-18-pro-max": "iphone",
    "iphone-air-series": "iphone",
    "iphone": "iphone",  # catch-all; contributes only slugs the leaves missed
}

# Deal-score weights. Must sum to 1.0.
WEIGHTS = {
    "vs_apple": 0.30,
    "vs_history": 0.25,
    "vs_peers": 0.20,
    "spec_value": 0.15,
    "site_discount": 0.10,
}

DUTY_PERCENT = 0.55  # tune until Est. Apple Landed matches observed reality
HISTORY_WINDOW_DAYS = 90
COUNT_DROP_ABORT_THRESHOLD = 0.20  # abort if a category shrinks >20%

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
WEB_DIR = ROOT / "web"
BUILD_DIR = ROOT / "build"
FIXTURE_DIR = ROOT / "tests" / "fixtures"
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `python -m pytest tests/test_config.py -v`
Expected: 4 passed

- [ ] **Step 8: Write `README.md`**

```markdown
# applemac.pk Price Tracker

Tracks MacBook Pro 14"/16", MacBook Air 13"/15" and current iPhone prices
from applemac.pk. Produces a ranked Excel workbook and a dashboard.

Runs daily via GitHub Actions; results publish to GitHub Pages.

## Local use

    pip install -r requirements.txt
    python -m scraper.cli run      # scrape, update history, rebuild outputs
    python -m scraper.cli serve    # dashboard at http://127.0.0.1:8000

Windows: double-click `run.bat`.

## Data

- `data/history.csv` — append-only price snapshots (canonical)
- `data/products.csv` — product identity and specs
- `data/apple_msrp.json` — Apple US MSRPs you maintain by hand

The SQLite database and Excel workbook under `web/downloads/` are
regenerated every run. Full history lives in git.

## Caveats

`Est. Apple Landed` is an estimate (US MSRP x live FX x duty %), not an
official or actual landed cost. Listed price does not guarantee stock.

## License

MIT. See `LICENSE`.
```

- [ ] **Step 9: Commit**

```bash
git add requirements.txt pytest.ini README.md scraper/ tests/
git commit -m "feat: project scaffolding and configuration"
```

---

### Task 2: HTTP fetching

**Files:**
- Create: `scraper/fetch.py`
- Test: `tests/test_fetch.py`

**Interfaces:**
- Consumes: `config.BASE_URL`, `config.USER_AGENT`, `config.REQUEST_DELAY`, `config.MAX_RETRIES`, `config.REQUEST_TIMEOUT`.
- Produces: `class FetchError(Exception)`, `class Fetcher` with `__init__(self, session=None, delay=None, cache_dir=None)`, `fetch_category(self, slug: str) -> str`, `fetch_fx(self, url: str) -> dict`, and `fetch_sitemap(self) -> str`.

`Fetcher` takes an injectable `session` so tests never touch the network.

- [ ] **Step 1: Write the failing test**

Create `tests/test_fetch.py`:

```python
import pytest
from scraper.fetch import Fetcher, FetchError


class FakeResponse:
    def __init__(self, text="<html></html>", status_code=200):
        self.text = text
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return {"ok": True}


class FakeSession:
    """Records calls and replays a queued list of responses or exceptions."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.headers = {}

    def get(self, url, timeout=None):
        self.calls.append(url)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def test_fetch_category_builds_correct_url():
    session = FakeSession([FakeResponse("<html>ok</html>")])
    fetcher = Fetcher(session=session, delay=0)
    html = fetcher.fetch_category("macbook-pro-14")
    assert html == "<html>ok</html>"
    assert session.calls == ["https://applemac.pk/category/macbook-pro-14"]


def test_fetch_retries_then_succeeds():
    session = FakeSession([RuntimeError("boom"), FakeResponse("<html>ok</html>")])
    fetcher = Fetcher(session=session, delay=0)
    assert fetcher.fetch_category("iphone-17") == "<html>ok</html>"
    assert len(session.calls) == 2


def test_fetch_raises_after_max_retries():
    session = FakeSession([RuntimeError("boom")] * 5)
    fetcher = Fetcher(session=session, delay=0)
    with pytest.raises(FetchError) as exc:
        fetcher.fetch_category("iphone-17")
    assert "iphone-17" in str(exc.value)


def test_caches_html_when_cache_dir_given(tmp_path):
    session = FakeSession([FakeResponse("<html>cached</html>")])
    fetcher = Fetcher(session=session, delay=0, cache_dir=tmp_path)
    fetcher.fetch_category("macbook-pro-14")
    assert (tmp_path / "macbook-pro-14.html").read_text(encoding="utf-8") ==         "<html>cached</html>"


def test_fetch_sitemap_uses_correct_url():
    session = FakeSession([FakeResponse("<urlset/>")])
    Fetcher(session=session, delay=0).fetch_sitemap()
    assert session.calls == ["https://applemac.pk/sitemap.xml"]


def test_user_agent_is_set():
    session = FakeSession([FakeResponse()])
    Fetcher(session=session, delay=0)
    assert "applemac-price-tracker" in session.headers["User-Agent"]


def test_rate_limit_waits_between_requests(monkeypatch):
    sleeps = []
    monkeypatch.setattr("scraper.fetch.time.sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr("scraper.fetch.time.monotonic", lambda: 0.0)
    session = FakeSession([FakeResponse(), FakeResponse()])
    fetcher = Fetcher(session=session, delay=1.5)
    fetcher.fetch_category("a")
    fetcher.fetch_category("b")
    assert any(s > 0 for s in sleeps), "second request should have waited"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_fetch.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scraper.fetch'`

- [ ] **Step 3: Write `scraper/fetch.py`**

```python
"""The only module that performs network I/O."""
import time

import requests

from . import config


class FetchError(Exception):
    """A URL could not be retrieved after all retries."""


class Fetcher:
    def __init__(self, session=None, delay=None, cache_dir=None):
        self.session = session if session is not None else requests.Session()
        self.session.headers["User-Agent"] = config.USER_AGENT
        self.delay = config.REQUEST_DELAY if delay is None else delay
        self.cache_dir = cache_dir
        self._last_request_at = None

    def _wait(self):
        if self.delay <= 0 or self._last_request_at is None:
            return
        elapsed = time.monotonic() - self._last_request_at
        remaining = self.delay - elapsed
        if remaining > 0:
            time.sleep(remaining)

    def _get(self, url):
        last_error = None
        for attempt in range(config.MAX_RETRIES):
            self._wait()
            try:
                response = self.session.get(url, timeout=config.REQUEST_TIMEOUT)
                response.raise_for_status()
                return response
            except Exception as error:  # noqa: BLE001 - retry any transport error
                last_error = error
                time.sleep(2 ** attempt)
            finally:
                self._last_request_at = time.monotonic()
        raise FetchError(f"{url} failed after {config.MAX_RETRIES} attempts: {last_error}")

    def fetch_category(self, slug):
        html = self._get(f"{config.BASE_URL}/category/{slug}").text
        if self.cache_dir is not None:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            (self.cache_dir / f"{slug}.html").write_text(html, encoding="utf-8")
        return html

    def fetch_sitemap(self):
        return self._get(f"{config.BASE_URL}/sitemap.xml").text

    def fetch_fx(self, url):
        return self._get(url).json()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_fetch.py -v`
Expected: 7 passed

- [ ] **Step 5: Add the opt-in live test**

Append to `tests/test_fetch.py`:

```python
@pytest.mark.live
def test_live_category_still_parses():
    """Detects upstream markup changes. Run with: pytest -m live"""
    fetcher = Fetcher()
    html = fetcher.fetch_category("macbook-pro-14")
    assert 'data-price="' in html, "card markup changed upstream"
```

- [ ] **Step 6: Verify the live test is deselected by default**

Run: `python -m pytest tests/test_fetch.py -v`
Expected: 7 passed, 1 deselected

- [ ] **Step 7: Commit**

```bash
git add scraper/fetch.py tests/test_fetch.py
git commit -m "feat: rate-limited HTTP fetcher with retry"
```

---

### Task 3: HTML parsing

**Files:**
- Create: `scraper/parse.py`
- Test: `tests/test_parse.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `@dataclass(frozen=True) RawProduct` with fields `slug: str`, `url: str`, `name: str`, `image_url: str | None`, `price_attr: str | None`, `new_price_text: str | None`, `old_price_text: str | None`, `attrs: dict[str, str]`, `category_slug: str`. Also `class ParseError(Exception)` and `parse_category(html: str, category_slug: str) -> list[RawProduct]`.

`parse.py` extracts strings verbatim. It interprets nothing — that is `normalize.py`'s job.

- [ ] **Step 1: Write the failing test**

Create `tests/test_parse.py`:

```python
import pytest

from scraper import config
from scraper.parse import ParseError, parse_category


def fixture(name):
    return (config.FIXTURE_DIR / name).read_text(encoding="utf-8")


def test_parses_all_macbook_cards():
    products = parse_category(fixture("macbook-pro-14.html"), "macbook-pro-14")
    assert len(products) == 58


def test_first_macbook_card_fields():
    first = parse_category(fixture("macbook-pro-14.html"), "macbook-pro-14")[0]
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


def test_parses_iphone_cards_with_different_attributes():
    products = parse_category(fixture("iphone-17-pro-max.html"), "iphone-17-pro-max")
    assert len(products) == 4
    first = products[0]
    assert first.slug == "apple-iphone-17-pro-max-2tb"
    assert first.price_attr == "892999"
    assert first.attrs["data-storage"] == "2TB"
    assert first.attrs["data-ssd"] == "•"          # null placeholder
    assert first.attrs["data-screensize"] == "6.9‑inch"  # U+2011
    assert first.old_price_text == "PKR  930,000"


def test_empty_category_returns_empty_list_not_error():
    assert parse_category(fixture("empty-category.html"), "iphone-16-series") == []


def test_unrecognisable_markup_raises_parse_error():
    with pytest.raises(ParseError):
        parse_category("<html><body><p>nothing here</p></body></html>", "x")


def test_slugs_are_unique_within_a_category():
    products = parse_category(fixture("macbook-pro-14.html"), "macbook-pro-14")
    slugs = [p.slug for p in products]
    assert len(slugs) == len(set(slugs))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_parse.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scraper.parse'`

- [ ] **Step 3: Write `scraper/parse.py`**

The listing container is `div#main_categoryinner`; each card is a `div` carrying
class `pdt`. Its presence is how we tell "empty category" from "markup changed".

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_parse.py -v`
Expected: 6 passed

If `test_first_macbook_card_fields` fails on `old_price_text`, check that
`get_text(strip=True)` preserves the interior double space — `strip=True` only
trims the ends, so `"PKR  772,000"` must survive intact.

- [ ] **Step 5: Commit**

```bash
git add scraper/parse.py tests/test_parse.py
git commit -m "feat: parse category HTML into RawProduct records"
```

---

### Task 4: Normalization

**Files:**
- Create: `scraper/normalize.py`
- Test: `tests/test_normalize.py`

**Interfaces:**
- Consumes: `parse.RawProduct`, `config.NULL_PLACEHOLDER`.
- Produces: `@dataclass(frozen=True) Product` with fields `slug, url, name, family, category_slug, image_url, price: int, old_price: int | None, ram_gb: int | None, storage_gb: int | None, chip: str | None, cpu_cores: int | None, gpu_cores: int | None, screen_size: float | None, color: str | None, model_group: str, config_key: str`. Helper functions `clean(value) -> str | None`, `parse_capacity(text) -> int | None`, `parse_cores(text) -> int | None`, `parse_screen_size(text) -> float | None`, `parse_price(text) -> int | None`, `slugify(text) -> str`, and `normalize(raw: RawProduct, family: str) -> Product | None`.

`normalize` returns `None` when the record has no usable price — such a row cannot participate in any comparison, so it is dropped with a count reported rather than stored as a hole.

- [ ] **Step 1: Write the failing test**

Create `tests/test_normalize.py`:

```python
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
    assert product.model_group == "macbook_pro_14_0_m5"
    assert product.config_key == "macbook_pro_14_0_m5_32_1024"


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_normalize.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scraper.normalize'`

- [ ] **Step 3: Write `scraper/normalize.py`**

```python
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
    if price is None:
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

    model_group = "_".join(
        part for part in (family, slugify(screen_size) if screen_size else None,
                          slugify(chip) if chip else None) if part
    )
    config_key = "_".join(
        part for part in (model_group,
                          str(ram_gb) if ram_gb else None,
                          str(storage_gb) if storage_gb else None) if part
    )

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_normalize.py -v`
Expected: 13 passed

- [ ] **Step 5: Commit**

```bash
git add scraper/normalize.py tests/test_normalize.py
git commit -m "feat: normalize raw cards into typed Product records"
```

---

### Task 5: CSV storage and derived SQLite

**Files:**
- Create: `scraper/store.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: `normalize.Product`.
- Produces: dataclasses `Snapshot(run_id, slug, price, old_price, seen_at)`, `Run(run_id, started_at, finished_at, status, fx_rate, duty_percent, product_count, notes)`, `Change(slug, old, new, delta, pct)`; class `Database` with `products: dict[str, dict]`, `history: list[Snapshot]`, `runs: list[Run]`, and methods `record_run(run_id, products, started_at, finished_at, fx_rate, duty_percent, notes)`, `price_history(slug) -> list[Snapshot]`, `previous_run() -> Run | None`, `latest_run() -> Run | None`, `median_price(slug, days, now=None) -> float | None`, `changes_since(run_id) -> list[Change]`, `category_counts(run_id) -> dict[str, int]`; module functions `load(data_dir) -> Database`, `save(db, data_dir) -> None`, `build_sqlite(db, path) -> None`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_store.py`:

```python
import datetime as dt
import sqlite3

from scraper import store
from scraper.normalize import Product


def make_product(slug="a", price=100000, old_price=None, config_key="grp_8_256"):
    return Product(
        slug=slug, url=f"https://applemac.pk/product/{slug}", name=slug.upper(),
        family="macbook_pro", category_slug="macbook-pro-14", image_url=None,
        price=price, old_price=old_price, ram_gb=8, storage_gb=256, chip="M4",
        cpu_cores=10, gpu_cores=10, screen_size=14.0, color="Silver",
        model_group="grp", config_key=config_key,
    )


def test_round_trip_preserves_data(tmp_path):
    db = store.Database()
    db.record_run("run1", [make_product()], "2026-09-01T00:00:00",
                  "2026-09-01T00:01:00", 277.5, 0.55, "")
    store.save(db, tmp_path)

    reloaded = store.load(tmp_path)
    assert list(reloaded.products) == ["a"]
    assert reloaded.history[0].price == 100000
    assert reloaded.runs[0].run_id == "run1"
    assert reloaded.runs[0].fx_rate == 277.5


def test_history_is_append_only(tmp_path):
    db = store.Database()
    db.record_run("run1", [make_product(price=100000)], "2026-09-01T00:00:00",
                  "2026-09-01T00:01:00", 277.5, 0.55, "")
    store.save(db, tmp_path)

    db = store.load(tmp_path)
    db.record_run("run2", [make_product(price=90000)], "2026-09-02T00:00:00",
                  "2026-09-02T00:01:00", 277.5, 0.55, "")
    store.save(db, tmp_path)

    reloaded = store.load(tmp_path)
    assert [s.price for s in reloaded.price_history("a")] == [100000, 90000]


def test_load_from_empty_directory(tmp_path):
    db = store.load(tmp_path)
    assert db.products == {}
    assert db.history == []
    assert db.previous_run() is None


def test_changes_since_reports_movement(tmp_path):
    db = store.Database()
    db.record_run("run1", [make_product(price=100000)], "2026-09-01T00:00:00",
                  "2026-09-01T00:01:00", 277.5, 0.55, "")
    db.record_run("run2", [make_product(price=90000)], "2026-09-02T00:00:00",
                  "2026-09-02T00:01:00", 277.5, 0.55, "")
    changes = db.changes_since("run2")
    assert len(changes) == 1
    assert changes[0].delta == -10000
    assert round(changes[0].pct, 2) == -10.0


def test_changes_since_ignores_unchanged_and_new_products():
    db = store.Database()
    db.record_run("run1", [make_product("a", 100000)], "2026-09-01T00:00:00",
                  "2026-09-01T00:01:00", 277.5, 0.55, "")
    db.record_run("run2", [make_product("a", 100000), make_product("b", 50000)],
                  "2026-09-02T00:00:00", "2026-09-02T00:01:00", 277.5, 0.55, "")
    assert db.changes_since("run2") == []


def test_median_price_respects_window():
    db = store.Database()
    now = dt.datetime(2026, 9, 15, tzinfo=dt.timezone.utc)
    old = (now - dt.timedelta(days=200)).isoformat()
    recent = (now - dt.timedelta(days=5)).isoformat()
    db.record_run("old", [make_product(price=500000)], old, old, 277.5, 0.55, "")
    db.record_run("new", [make_product(price=100000)], recent, recent, 277.5, 0.55, "")
    assert db.median_price("a", days=90, now=now) == 100000


def test_median_price_none_without_history():
    assert store.Database().median_price("nope", days=90) is None


def test_save_is_atomic_leaving_no_temp_files(tmp_path):
    db = store.Database()
    db.record_run("run1", [make_product()], "2026-09-01T00:00:00",
                  "2026-09-01T00:01:00", 277.5, 0.55, "")
    store.save(db, tmp_path)
    assert not list(tmp_path.glob("*.tmp"))


def test_build_sqlite_creates_queryable_database(tmp_path):
    db = store.Database()
    db.record_run("run1", [make_product()], "2026-09-01T00:00:00",
                  "2026-09-01T00:01:00", 277.5, 0.55, "")
    path = tmp_path / "prices.db"
    store.build_sqlite(db, path)

    con = sqlite3.connect(path)
    assert con.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0] == 1
    assert con.execute("SELECT price FROM snapshots").fetchone()[0] == 100000
    con.close()


def test_category_counts(tmp_path):
    db = store.Database()
    db.record_run("run1", [make_product("a"), make_product("b")],
                  "2026-09-01T00:00:00", "2026-09-01T00:01:00", 277.5, 0.55, "")
    assert db.category_counts("run1") == {"macbook-pro-14": 2}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scraper.store'`

- [ ] **Step 3: Write `scraper/store.py`**

```python
"""Canonical storage is append-only CSV in git. SQLite is a derived artifact."""
import csv
import datetime as dt
import sqlite3
import statistics
from dataclasses import asdict, dataclass, field

PRODUCT_FIELDS = [
    "slug", "url", "name", "family", "category_slug", "image_url",
    "ram_gb", "storage_gb", "chip", "cpu_cores", "gpu_cores",
    "screen_size", "color", "model_group", "config_key",
    "first_seen", "last_seen",
]
SNAPSHOT_FIELDS = ["run_id", "slug", "price", "old_price", "seen_at"]
RUN_FIELDS = ["run_id", "started_at", "finished_at", "status",
              "fx_rate", "duty_percent", "product_count", "notes"]


@dataclass
class Snapshot:
    run_id: str
    slug: str
    price: int
    old_price: int | None
    seen_at: str


@dataclass
class Run:
    run_id: str
    started_at: str
    finished_at: str
    status: str
    fx_rate: float | None
    duty_percent: float | None
    product_count: int
    notes: str


@dataclass
class Change:
    slug: str
    old: int
    new: int
    delta: int
    pct: float


@dataclass
class Database:
    products: dict = field(default_factory=dict)
    history: list = field(default_factory=list)
    runs: list = field(default_factory=list)

    def record_run(self, run_id, products, started_at, finished_at,
                   fx_rate, duty_percent, notes=""):
        for product in products:
            existing = self.products.get(product.slug)
            record = {f: getattr(product, f, None) for f in PRODUCT_FIELDS
                      if f not in ("first_seen", "last_seen")}
            record["first_seen"] = (existing or {}).get("first_seen", started_at)
            record["last_seen"] = started_at
            self.products[product.slug] = record
            self.history.append(Snapshot(run_id, product.slug, product.price,
                                         product.old_price, started_at))
        self.runs.append(Run(run_id, started_at, finished_at, "ok", fx_rate,
                             duty_percent, len(products), notes))

    def price_history(self, slug):
        return [s for s in self.history if s.slug == slug]

    def latest_run(self):
        return self.runs[-1] if self.runs else None

    def previous_run(self):
        return self.runs[-2] if len(self.runs) >= 2 else None

    def snapshots_for_run(self, run_id):
        return {s.slug: s for s in self.history if s.run_id == run_id}

    def median_price(self, slug, days, now=None):
        now = now or dt.datetime.now(dt.timezone.utc)
        cutoff = now - dt.timedelta(days=days)
        prices = []
        for snapshot in self.price_history(slug):
            try:
                seen = dt.datetime.fromisoformat(snapshot.seen_at)
            except ValueError:
                continue
            if seen.tzinfo is None:
                seen = seen.replace(tzinfo=dt.timezone.utc)
            if seen >= cutoff:
                prices.append(snapshot.price)
        return statistics.median(prices) if prices else None

    def changes_since(self, run_id):
        index = next((i for i, r in enumerate(self.runs) if r.run_id == run_id), None)
        if index is None or index == 0:
            return []
        current = self.snapshots_for_run(run_id)
        previous = self.snapshots_for_run(self.runs[index - 1].run_id)
        changes = []
        for slug, snapshot in current.items():
            before = previous.get(slug)
            if before is None or before.price == snapshot.price:
                continue
            delta = snapshot.price - before.price
            changes.append(Change(slug, before.price, snapshot.price, delta,
                                  delta / before.price * 100))
        return sorted(changes, key=lambda c: c.delta)

    def category_counts(self, run_id):
        counts = {}
        for slug in self.snapshots_for_run(run_id):
            category = self.products[slug]["category_slug"]
            counts[category] = counts.get(category, 0) + 1
        return counts


def _read_csv(path):
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _to_int(value):
    return int(value) if value not in (None, "", "None") else None


def _to_float(value):
    return float(value) if value not in (None, "", "None") else None


def load(data_dir):
    db = Database()
    for row in _read_csv(data_dir / "products.csv"):
        for key in ("ram_gb", "storage_gb", "cpu_cores", "gpu_cores"):
            row[key] = _to_int(row.get(key))
        row["screen_size"] = _to_float(row.get("screen_size"))
        db.products[row["slug"]] = row
    for row in _read_csv(data_dir / "history.csv"):
        db.history.append(Snapshot(row["run_id"], row["slug"],
                                   _to_int(row["price"]),
                                   _to_int(row["old_price"]), row["seen_at"]))
    for row in _read_csv(data_dir / "runs.csv"):
        db.runs.append(Run(row["run_id"], row["started_at"], row["finished_at"],
                           row["status"], _to_float(row["fx_rate"]),
                           _to_float(row["duty_percent"]),
                           _to_int(row["product_count"]) or 0, row["notes"]))
    return db


def _write_csv(path, fields, rows):
    """Write via temp file then rename, so an interruption cannot truncate."""
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({f: row.get(f) for f in fields})
    temp.replace(path)


def save(db, data_dir):
    data_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(data_dir / "products.csv", PRODUCT_FIELDS,
               sorted(db.products.values(), key=lambda r: r["slug"]))
    _write_csv(data_dir / "history.csv", SNAPSHOT_FIELDS,
               [asdict(s) for s in db.history])
    _write_csv(data_dir / "runs.csv", RUN_FIELDS, [asdict(r) for r in db.runs])


def build_sqlite(db, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    con = sqlite3.connect(path)
    con.execute(f"CREATE TABLE products ({', '.join(PRODUCT_FIELDS)})")
    con.execute(f"CREATE TABLE snapshots ({', '.join(SNAPSHOT_FIELDS)})")
    con.execute(f"CREATE TABLE runs ({', '.join(RUN_FIELDS)})")
    con.executemany(
        f"INSERT INTO products VALUES ({', '.join('?' * len(PRODUCT_FIELDS))})",
        [[r.get(f) for f in PRODUCT_FIELDS] for r in db.products.values()])
    con.executemany(
        f"INSERT INTO snapshots VALUES ({', '.join('?' * len(SNAPSHOT_FIELDS))})",
        [[getattr(s, f) for f in SNAPSHOT_FIELDS] for s in db.history])
    con.executemany(
        f"INSERT INTO runs VALUES ({', '.join('?' * len(RUN_FIELDS))})",
        [[getattr(r, f) for f in RUN_FIELDS] for r in db.runs])
    con.execute("CREATE INDEX idx_snapshots_slug ON snapshots(slug)")
    con.commit()
    con.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_store.py -v`
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add scraper/store.py tests/test_store.py
git commit -m "feat: append-only CSV storage with derived SQLite"
```

---

### Task 6: Apple benchmark and FX

**Files:**
- Create: `scraper/benchmark.py`, `data/apple_msrp.json`
- Test: `tests/test_benchmark.py`

**Interfaces:**
- Consumes: `normalize.Product`, `fetch.Fetcher`, `config.DUTY_PERCENT`.
- Produces: `FX_URL: str`, `load_msrp(path) -> dict`, `get_fx_rate(fetcher, cache_path) -> tuple[float, bool]` returning `(rate, is_stale)`, `landed_pkr(usd, fx_rate, duty_percent) -> int`, `benchmark_for(product, msrp, fx_rate, duty_percent) -> int | None`, `missing_keys(products, msrp) -> list[str]`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_benchmark.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_benchmark.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scraper.benchmark'`

- [ ] **Step 3: Write `scraper/benchmark.py`**

```python
"""Estimated Apple landed price. An estimate, never an official price."""
import datetime as dt
import json

FX_URL = "https://open.er-api.com/v6/latest/USD"


class BenchmarkError(Exception):
    """No exchange rate available, live or cached."""


def load_msrp(path):
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def get_fx_rate(fetcher, cache_path):
    """Return (usd_to_pkr, is_stale). Falls back to cache when live fails."""
    try:
        payload = fetcher.fetch_fx(FX_URL)
        rate = float(payload["rates"]["PKR"])
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps({
            "rate": rate,
            "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        }), encoding="utf-8")
        return rate, False
    except Exception:  # noqa: BLE001 - any failure falls back to cache
        if cache_path.exists():
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            return float(cached["rate"]), True
        raise BenchmarkError(
            "USD->PKR rate unavailable and no cached rate exists"
        )


def landed_pkr(usd, fx_rate, duty_percent):
    return int(round(usd * fx_rate * (1 + duty_percent)))


def benchmark_for(product, msrp, fx_rate, duty_percent):
    usd = msrp.get(product.config_key)
    if usd is None or not isinstance(usd, (int, float)):
        return None
    return landed_pkr(usd, fx_rate, duty_percent)


def missing_keys(products, msrp):
    """config_keys with no MSRP entry, deduplicated and sorted."""
    return sorted({p.config_key for p in products
                   if p.config_key not in msrp and not p.config_key.startswith("_")})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_benchmark.py -v`
Expected: 10 passed

- [ ] **Step 5: Create the MSRP seed file**

Create `data/apple_msrp.json` with the schema and no invented prices:

```json
{
  "_meta": {
    "source": "Apple US online store",
    "currency": "USD",
    "checked": "",
    "note": "Keys are config_key values produced by normalize.py. Run 'python -m scraper.cli msrp-gaps' after a scrape to list the exact keys to add. Verify every price against apple.com before entering it."
  }
}
```

**Do not invent MSRP values.** The file ships empty of prices; the operator
populates it using `msrp-gaps` output (added in Task 9) and real apple.com
figures. Every product scores `None` on `vs_apple` until then, which the
Summary sheet reports as a visible gap.

- [ ] **Step 6: Commit**

```bash
git add scraper/benchmark.py tests/test_benchmark.py data/apple_msrp.json
git commit -m "feat: Apple landed-price benchmark with live FX and cache fallback"
```

---

### Task 7: Deal scoring

**Files:**
- Create: `scraper/score.py`
- Test: `tests/test_score.py`

**Interfaces:**
- Consumes: `normalize.Product`, `store.Database`, `config.WEIGHTS`, `config.HISTORY_WINDOW_DAYS`.
- Produces: `@dataclass Scores` with fields `vs_apple: float | None`, `vs_history: float | None`, `vs_peers: float | None`, `spec_value: float | None`, `site_discount: float | None`, `deal_score: float`, `confidence: int`; functions `percent_below(price, reference) -> float | None`, `score_all(products, db, benchmarks, weights=None, now=None) -> dict[str, Scores]`.

Every signal returns 0–100 where higher is better. `deal_score` is the weighted
mean over available signals only, renormalized so missing data does not silently
depress a score. `confidence` counts contributing signals.

- [ ] **Step 1: Write the failing test**

Create `tests/test_score.py`:

```python
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
    scores = score.score_all([make_product("a", price=100000)],
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_score.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scraper.score'`

- [ ] **Step 3: Write `scraper/score.py`**

```python
"""Five independent signals, combined into one explainable deal score."""
from collections import defaultdict
from dataclasses import dataclass

from . import config

SIGNALS = ("vs_apple", "vs_history", "vs_peers", "spec_value", "site_discount")


@dataclass
class Scores:
    vs_apple: float | None
    vs_history: float | None
    vs_peers: float | None
    spec_value: float | None
    site_discount: float | None
    deal_score: float
    confidence: int


def percent_below(price, reference):
    """How far below `reference` the price sits, as 0-100. None if unusable."""
    if reference is None or reference <= 0:
        return None
    return max(0.0, min(100.0, (reference - price) / reference * 100))


def _rank_within_group(values):
    """Map value -> 0-100 where the lowest value scores 100."""
    if len(values) < 2:
        return None
    lowest, highest = min(values), max(values)
    if highest == lowest:
        return None
    return lambda v: (highest - v) / (highest - lowest) * 100


def score_all(products, db, benchmarks, weights=None, now=None):
    weights = weights or config.WEIGHTS

    peers = defaultdict(list)
    spec_groups = defaultdict(list)
    for product in products:
        peers[product.config_key].append(product.price)
        ratio = _spec_ratio(product)
        if ratio is not None:
            spec_groups[product.model_group].append(ratio)

    peer_rankers = {k: _rank_within_group(v) for k, v in peers.items()}
    spec_rankers = {k: _rank_within_group(v) for k, v in spec_groups.items()}

    results = {}
    for product in products:
        vs_apple = percent_below(product.price, benchmarks.get(product.slug))

        median = db.median_price(product.slug, config.HISTORY_WINDOW_DAYS, now=now)
        vs_history = percent_below(product.price, median)

        ranker = peer_rankers.get(product.config_key)
        vs_peers = ranker(product.price) if ranker else None

        ratio = _spec_ratio(product)
        spec_ranker = spec_rankers.get(product.model_group)
        spec_value = spec_ranker(ratio) if (spec_ranker and ratio is not None) else None

        site_discount = None
        if product.old_price and product.old_price > product.price:
            site_discount = percent_below(product.price, product.old_price)

        values = {
            "vs_apple": vs_apple, "vs_history": vs_history, "vs_peers": vs_peers,
            "spec_value": spec_value, "site_discount": site_discount,
        }
        available = {k: v for k, v in values.items() if v is not None}
        if available:
            total_weight = sum(weights[k] for k in available)
            deal_score = sum(v * weights[k] for k, v in available.items()) / total_weight
        else:
            deal_score = 0.0

        results[product.slug] = Scores(
            **values,
            deal_score=round(max(0.0, min(100.0, deal_score)), 1),
            confidence=len(available),
        )
    return results


def _spec_ratio(product):
    """PKR per GB of RAM+storage. Lower is better value."""
    capacity = (product.ram_gb or 0) + (product.storage_gb or 0)
    if capacity <= 0:
        return None
    return product.price / capacity
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_score.py -v`
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add scraper/score.py tests/test_score.py
git commit -m "feat: five-signal deal scoring with renormalized composite"
```

---

### Task 8: Excel workbook

**Files:**
- Create: `scraper/excel.py`
- Test: `tests/test_excel.py`

**Interfaces:**
- Consumes: `normalize.Product`, `score.Scores`, `store.Database`.
- Produces: `SHEETS: tuple[tuple[str, tuple[str, ...]], ...]` mapping sheet name → families, and `build_workbook(products, scores, db, meta, path) -> None` where `meta` is a dict with keys `run_id`, `generated_at`, `fx_rate`, `fx_stale`, `duty_percent`, `missing_msrp`, `benchmarks`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_excel.py`:

```python
import openpyxl

from scraper import excel, score, store
from tests.test_store import make_product


def build(tmp_path, products, db=None, benchmarks=None):
    db = db or store.Database()
    benchmarks = benchmarks or {}
    scores = score.score_all(products, db, benchmarks)
    meta = {"run_id": "r1", "generated_at": "2026-09-15T00:00:00",
            "fx_rate": 277.75, "fx_stale": False, "duty_percent": 0.55,
            "missing_msrp": ["some_key"], "benchmarks": benchmarks}
    path = tmp_path / "out.xlsx"
    excel.build_workbook(products, scores, db, meta, path)
    return openpyxl.load_workbook(path)


def test_workbook_has_expected_sheets(tmp_path):
    wb = build(tmp_path, [make_product()])
    assert wb.sheetnames == ["Summary", "MacBook Pro", "MacBook Air",
                             "iPhone", "Price Changes"]


def test_rows_sorted_cheapest_first(tmp_path):
    products = [make_product("expensive", price=900000),
                make_product("cheap", price=100000),
                make_product("mid", price=500000)]
    sheet = build(tmp_path, products)["MacBook Pro"]
    prices = [row[0] for row in sheet.iter_rows(min_row=2, min_col=9, max_col=9,
                                                values_only=True)]
    assert prices == sorted(prices)


def test_header_row_is_frozen_and_filtered(tmp_path):
    sheet = build(tmp_path, [make_product()])["MacBook Pro"]
    assert sheet.freeze_panes == "A2"
    assert sheet.auto_filter.ref is not None


def test_summary_records_fx_and_duty(tmp_path):
    text = "\n".join(
        str(cell)
        for row in build(tmp_path, [make_product()])["Summary"].iter_rows(values_only=True)
        for cell in row if cell is not None
    )
    assert "277.75" in text
    assert "55" in text


def test_summary_lists_per_family_counts(tmp_path):
    rows = list(build(tmp_path, [make_product()])["Summary"].iter_rows(values_only=True))
    labels = {str(r[0]).strip(): r[1] for r in rows if r and r[0]}
    assert labels["MacBook Pro"] == 1
    assert labels["iPhone"] == 0


def test_summary_lists_missing_msrp_keys(tmp_path):
    text = "\n".join(
        str(cell)
        for row in build(tmp_path, [make_product()])["Summary"].iter_rows(values_only=True)
        for cell in row if cell is not None
    )
    assert "some_key" in text


def test_benchmark_column_never_claims_to_be_official(tmp_path):
    wb = build(tmp_path, [make_product()])
    headers = [c.value for c in wb["MacBook Pro"][1]]
    assert "Est. Apple Landed" in headers
    assert "Apple Price" not in headers


def test_price_changes_sheet_lists_movement(tmp_path):
    db = store.Database()
    db.record_run("r0", [make_product("a", price=100000)], "2026-09-01T00:00:00",
                  "2026-09-01T00:01:00", 277.5, 0.55, "")
    db.record_run("r1", [make_product("a", price=90000)], "2026-09-02T00:00:00",
                  "2026-09-02T00:01:00", 277.5, 0.55, "")
    products = [make_product("a", price=90000)]
    scores = score.score_all(products, db, {})
    meta = {"run_id": "r1", "generated_at": "x", "fx_rate": 277.5,
            "fx_stale": False, "duty_percent": 0.55, "missing_msrp": [],
            "benchmarks": {}}
    path = tmp_path / "out.xlsx"
    excel.build_workbook(products, scores, db, meta, path)
    sheet = openpyxl.load_workbook(path)["Price Changes"]
    assert sheet.max_row >= 2
    assert "-10000" in str([c.value for c in sheet[2]])


def test_empty_family_still_produces_a_sheet(tmp_path):
    wb = build(tmp_path, [make_product()])
    assert wb["iPhone"].max_row >= 1  # header row exists even with no products
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_excel.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scraper.excel'`

- [ ] **Step 3: Write `scraper/excel.py`**

```python
"""Multi-sheet workbook. Columns 1-9 are identity and price; 10+ are analysis."""
from openpyxl import Workbook
from openpyxl.formatting.rule import ColorScaleRule
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter

SHEETS = (
    ("MacBook Pro", ("macbook_pro",)),
    ("MacBook Air", ("macbook_air",)),
    ("iPhone", ("iphone",)),
)

HEADERS = [
    "Name", "Screen", "Chip", "RAM (GB)", "Storage (GB)", "CPU", "GPU", "Color",
    "Price (PKR)", "Old Price", "Est. Apple Landed", "vs Apple %",
    "Δ Since Last Run", "vs History", "vs Peers", "Spec Value",
    "Deal Score", "Confidence", "First Seen",
]
PRICE_COLUMNS = (9, 10, 11, 13)
DEAL_SCORE_COLUMN = 17


def _style_header(sheet):
    for cell in sheet[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = (
        f"A1:{get_column_letter(sheet.max_column)}{max(sheet.max_row, 1)}"
    )
    widths = {1: 52, 2: 9, 3: 12, 9: 14, 10: 14, 11: 18, 13: 16, 17: 12, 19: 20}
    for index, width in widths.items():
        sheet.column_dimensions[get_column_letter(index)].width = width


def build_workbook(products, scores, db, meta, path):
    workbook = Workbook()
    workbook.remove(workbook.active)

    _build_summary(workbook, products, scores, meta)

    previous = {}
    if db.previous_run():
        previous = {s.slug: s.price
                    for s in db.snapshots_for_run(db.previous_run().run_id)}

    for sheet_name, families in SHEETS:
        sheet = workbook.create_sheet(sheet_name)
        sheet.append(HEADERS)
        rows = sorted((p for p in products if p.family in families),
                      key=lambda p: p.price)
        for product in rows:
            score_row = scores[product.slug]
            benchmark = meta["benchmarks"].get(product.slug)
            before = previous.get(product.slug)
            sheet.append([
                product.name, product.screen_size, product.chip, product.ram_gb,
                product.storage_gb, product.cpu_cores, product.gpu_cores,
                product.color, product.price, product.old_price, benchmark,
                score_row.vs_apple,
                product.price - before if before is not None else None,
                score_row.vs_history, score_row.vs_peers, score_row.spec_value,
                score_row.deal_score, score_row.confidence,
                db.products.get(product.slug, {}).get("first_seen"),
            ])
            sheet.cell(row=sheet.max_row, column=1).hyperlink = product.url
            sheet.cell(row=sheet.max_row, column=1).font = Font(
                color="0563C1", underline="single")

        for row in sheet.iter_rows(min_row=2):
            for column in PRICE_COLUMNS:
                row[column - 1].number_format = "#,##0"

        if sheet.max_row > 1:
            letter = get_column_letter(DEAL_SCORE_COLUMN)
            sheet.conditional_formatting.add(
                f"{letter}2:{letter}{sheet.max_row}",
                ColorScaleRule(start_type="min", start_color="FFFFFF",
                               end_type="max", end_color="63BE7B"))
        _style_header(sheet)

    _build_changes(workbook, db, meta)
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(path)


def _build_summary(workbook, products, scores, meta):
    sheet = workbook.create_sheet("Summary")
    sheet.append(["applemac.pk Price Tracker"])
    sheet["A1"].font = Font(bold=True, size=14)
    sheet.append([])
    sheet.append(["Run ID", meta["run_id"]])
    sheet.append(["Generated", meta["generated_at"]])
    sheet.append(["USD to PKR rate", meta["fx_rate"],
                  "STALE - cached rate used" if meta["fx_stale"] else "live"])
    sheet.append(["Import duty assumption (%)", round(meta["duty_percent"] * 100, 1)])
    sheet.append(["Products tracked", len(products)])
    for sheet_name, families in SHEETS:
        count = sum(1 for p in products if p.family in families)
        sheet.append([f"  {sheet_name}", count])
    sheet.append([])
    sheet.append(["'Est. Apple Landed' = US MSRP x FX x (1 + duty). "
                  "An estimate, not an official or actual landed price."])
    sheet.append([])

    sheet.append(["Top 15 deals"])
    sheet[f"A{sheet.max_row}"].font = Font(bold=True)
    sheet.append(["Name", "Family", "Price (PKR)", "Deal Score", "Confidence"])
    ranked = sorted(products, key=lambda p: scores[p.slug].deal_score, reverse=True)
    for product in ranked[:15]:
        sheet.append([product.name, product.family, product.price,
                      scores[product.slug].deal_score,
                      scores[product.slug].confidence])
        sheet.cell(row=sheet.max_row, column=3).number_format = "#,##0"

    sheet.append([])
    sheet.append([f"Configs with no Apple MSRP entry ({len(meta['missing_msrp'])})"])
    sheet[f"A{sheet.max_row}"].font = Font(bold=True)
    for key in meta["missing_msrp"]:
        sheet.append([key])
    sheet.column_dimensions["A"].width = 52
    sheet.column_dimensions["B"].width = 18


def _build_changes(workbook, db, meta):
    sheet = workbook.create_sheet("Price Changes")
    sheet.append(["Name", "Direction", "Previous", "Current", "Change", "Change %"])
    for change in db.changes_since(meta["run_id"]):
        product = db.products.get(change.slug, {})
        sheet.append([product.get("name", change.slug),
                      "DOWN" if change.delta < 0 else "UP",
                      change.old, change.new, change.delta, round(change.pct, 2)])
        for column in (3, 4, 5):
            sheet.cell(row=sheet.max_row, column=column).number_format = "#,##0"
    _style_header(sheet)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_excel.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add scraper/excel.py tests/test_excel.py
git commit -m "feat: multi-sheet Excel workbook with deal ranking"
```

---

### Task 9: Orchestration CLI with failure rules

**Files:**
- Create: `scraper/cli.py`, `scraper/report.py`
- Test: `tests/test_cli.py`, `tests/test_report.py`

**Interfaces:**
- Consumes: everything from Tasks 2–8.
- Produces: `class RunAborted(Exception)`; `collect(fetcher, db, categories, previous_counts=None, drop_threshold=None) -> tuple[list[Product], list[str]]` returning products and notes, raising `RunAborted` per the failure table; `coverage_gaps(sitemap_xml, collected_slugs, pattern="iphone") -> list[str]`; `run(fetcher=None, data_dir=None, web_dir=None, force=False) -> dict` (the meta dict); `main(argv=None) -> int`. In `report.py`: `write_latest(products, scores, db, meta, path)` and `write_history(db, path)`.

CLI commands: `run`, `serve`, `msrp-gaps`.

- [ ] **Step 1: Write the failing test for the failure rules**

Create `tests/test_cli.py`:

```python
import pytest

from scraper import cli, config, store
from tests.test_store import make_product


def fixture(name):
    return (config.FIXTURE_DIR / name).read_text(encoding="utf-8")


class StubFetcher:
    """Serves fixture HTML per category slug."""

    def __init__(self, pages, fx=None):
        self.pages = pages
        self.fx = fx or {"result": "success", "rates": {"PKR": 277.75}}

    def fetch_category(self, slug):
        if slug not in self.pages:
            return fixture("empty-category.html")
        return self.pages[slug]

    def fetch_fx(self, url):
        return self.fx

    def fetch_sitemap(self):
        return SITEMAP


SITEMAP = """<?xml version="1.0"?>
<urlset><url><loc>https://applemac.pk/product/apple-iphone-17-pro-max-2tb</loc></url>
<url><loc>https://applemac.pk/product/apple-iphone-99-unseen</loc></url>
<url><loc>https://applemac.pk/product/macbook-air-m4-ignored</loc></url></urlset>"""


def test_coverage_gaps_reports_iphone_slugs_no_category_yielded():
    gaps = cli.coverage_gaps(SITEMAP, {"apple-iphone-17-pro-max-2tb"})
    assert gaps == ["apple-iphone-99-unseen"]


def test_coverage_gaps_ignores_non_matching_products():
    gaps = cli.coverage_gaps(SITEMAP, set())
    assert "macbook-air-m4-ignored" not in gaps


def test_coverage_gaps_is_empty_when_everything_collected():
    assert cli.coverage_gaps(SITEMAP, {"apple-iphone-17-pro-max-2tb",
                                       "apple-iphone-99-unseen"}) == []


def test_collect_dedupes_slugs_across_categories():
    html = fixture("iphone-17-pro-max.html")
    fetcher = StubFetcher({"iphone-17-pro-max": html, "iphone": html})
    products, _ = cli.collect(
        fetcher, store.Database(),
        {"iphone-17-pro-max": "iphone", "iphone": "iphone"})
    assert len(products) == 4          # not 8
    assert len({p.slug for p in products}) == 4


def test_collect_allows_empty_category_never_seen_before():
    fetcher = StubFetcher({})
    products, notes = cli.collect(fetcher, store.Database(),
                                  {"iphone-16-series": "iphone"})
    assert products == []
    assert any("empty" in n for n in notes)


def test_collect_aborts_when_previously_populated_category_empties():
    db = store.Database()
    db.record_run("r0", [make_product("a")], "2026-09-01T00:00:00",
                  "2026-09-01T00:01:00", 277.5, 0.55, "")
    fetcher = StubFetcher({})
    with pytest.raises(cli.RunAborted) as exc:
        cli.collect(fetcher, db, {"macbook-pro-14": "macbook_pro"})
    assert "macbook-pro-14" in str(exc.value)


def test_collect_aborts_on_large_count_drop():
    db = store.Database()
    previous = [make_product(f"p{i}") for i in range(10)]
    db.record_run("r0", previous, "2026-09-01T00:00:00", "2026-09-01T00:01:00",
                  277.5, 0.55, "")
    fetcher = StubFetcher({"macbook-pro-14": fixture("iphone-17-pro-max.html")})
    with pytest.raises(cli.RunAborted) as exc:
        cli.collect(fetcher, db, {"macbook-pro-14": "macbook_pro"})
    assert "dropped" in str(exc.value).lower()


def test_failed_run_writes_nothing(tmp_path):
    db = store.Database()
    db.record_run("r0", [make_product("a")], "2026-09-01T00:00:00",
                  "2026-09-01T00:01:00", 277.5, 0.55, "")
    store.save(db, tmp_path)
    before = (tmp_path / "history.csv").read_text()

    class Broken:
        def fetch_category(self, slug):
            raise RuntimeError("network down")

        def fetch_fx(self, url):
            return {"result": "success", "rates": {"PKR": 277.75}}

    with pytest.raises(Exception):
        cli.run(fetcher=Broken(), data_dir=tmp_path, web_dir=tmp_path / "web")

    assert (tmp_path / "history.csv").read_text() == before


def test_successful_run_appends_history_and_writes_outputs(tmp_path):
    fetcher = StubFetcher({"macbook-pro-14": fixture("macbook-pro-14.html")})
    web = tmp_path / "web"
    meta = cli.run(fetcher=fetcher, data_dir=tmp_path, web_dir=web)

    assert meta["product_count"] == 58
    assert (tmp_path / "history.csv").exists()
    assert (web / "data" / "latest.json").exists()
    assert (web / "downloads" / "applemac-prices.xlsx").exists()
    assert (web / "downloads" / "prices.db").exists()


def test_two_runs_accumulate_history(tmp_path):
    fetcher = StubFetcher({"macbook-pro-14": fixture("macbook-pro-14.html")})
    web = tmp_path / "web"
    cli.run(fetcher=fetcher, data_dir=tmp_path, web_dir=web)
    cli.run(fetcher=fetcher, data_dir=tmp_path, web_dir=web)
    db = store.load(tmp_path)
    assert len(db.runs) == 2
    assert len(db.history) == 116
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scraper.cli'`

- [ ] **Step 3: Write `scraper/report.py`**

```python
"""JSON the dashboard reads. Same data in static and live mode."""
import json
from dataclasses import asdict


def write_latest(products, scores, db, meta, path):
    previous = {}
    if db.previous_run():
        previous = {s.slug: s.price
                    for s in db.snapshots_for_run(db.previous_run().run_id)}

    rows = []
    for product in sorted(products, key=lambda p: p.price):
        score_row = scores[product.slug]
        before = previous.get(product.slug)
        rows.append({
            **asdict(product),
            "benchmark": meta["benchmarks"].get(product.slug),
            "delta": product.price - before if before is not None else None,
            "scores": asdict(score_row),
            "first_seen": db.products.get(product.slug, {}).get("first_seen"),
        })

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "meta": {k: v for k, v in meta.items() if k != "benchmarks"},
        "products": rows,
    }, indent=1), encoding="utf-8")


def write_history(db, path):
    series = {}
    for snapshot in db.history:
        series.setdefault(snapshot.slug, []).append(
            [snapshot.seen_at, snapshot.price])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(series), encoding="utf-8")
```

- [ ] **Step 4: Write `scraper/cli.py`**

```python
"""Orchestration. Failure here must never corrupt the stored history."""
import argparse
import datetime as dt
import re
import sys

from . import benchmark, config, excel, report, score, store
from .fetch import Fetcher
from .normalize import normalize
from .parse import parse_category


class RunAborted(Exception):
    """A sanity check failed; nothing is written."""


def _now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def collect(fetcher, db, categories, previous_counts=None, drop_threshold=None):
    """Fetch and normalize every category. Raises RunAborted on bad data."""
    if previous_counts is None:
        previous_run = db.latest_run()
        previous_counts = (db.category_counts(previous_run.run_id)
                           if previous_run else {})
    if drop_threshold is None:
        drop_threshold = config.COUNT_DROP_ABORT_THRESHOLD

    by_slug = {}
    notes = []
    for category_slug, family in categories.items():
        html = fetcher.fetch_category(category_slug)
        raw_products = parse_category(html, category_slug)
        seen_before = previous_counts.get(category_slug, 0)

        if not raw_products:
            if seen_before > 0:
                raise RunAborted(
                    f"{category_slug}: returned 0 products but had "
                    f"{seen_before} last run"
                )
            notes.append(f"{category_slug}: empty")
            continue

        if seen_before:
            drop = (seen_before - len(raw_products)) / seen_before
            if drop > drop_threshold:
                raise RunAborted(
                    f"{category_slug}: count dropped {drop:.0%} "
                    f"({seen_before} -> {len(raw_products)}); use --force to accept"
                )

        dropped = 0
        for raw in raw_products:
            if raw.slug in by_slug:      # leaf categories overlap the catch-all
                continue
            product = normalize(raw, family)
            if product is None:
                dropped += 1
                continue
            by_slug[raw.slug] = product
        if dropped:
            notes.append(f"{category_slug}: {dropped} rows had no usable price")

    return list(by_slug.values()), notes


def coverage_gaps(sitemap_xml, collected_slugs, pattern="iphone"):
    """Sitemap product slugs matching `pattern` that no category yielded.

    Reports only. A gap means a category is missing from config, not that the
    run is wrong, so this never aborts.
    """
    found = re.findall(r"<loc>[^<]*?/product/([^<]+)</loc>", sitemap_xml)
    return sorted({slug.rstrip("/") for slug in found
                   if pattern in slug and slug.rstrip("/") not in collected_slugs})


def run(fetcher=None, data_dir=None, web_dir=None, force=False):
    started_at = _now()
    run_id = started_at.replace(":", "").replace("-", "")

    data_dir = data_dir or config.DATA_DIR
    web_dir = web_dir or config.WEB_DIR
    fetcher = fetcher or Fetcher(cache_dir=config.BUILD_DIR / "cache" / run_id)

    db = store.load(data_dir)
    products, notes = collect(fetcher, db, config.CATEGORIES,
                              drop_threshold=1.0 if force else None)

    if not products:
        raise RunAborted("no products collected from any category")

    try:
        gaps = coverage_gaps(fetcher.fetch_sitemap(), {p.slug for p in products})
        if gaps:
            notes.append(
                f"{len(gaps)} iPhone products in the sitemap matched no "
                f"configured category (e.g. {', '.join(gaps[:3])})"
            )
    except Exception as error:  # noqa: BLE001 - coverage check never fails a run
        notes.append(f"sitemap coverage check skipped: {error}")

    fx_rate, fx_stale = benchmark.get_fx_rate(fetcher, data_dir / "fx_cache.json")
    if fx_stale:
        notes.append("FX rate is stale (cached)")

    msrp = benchmark.load_msrp(data_dir / "apple_msrp.json")
    benchmarks = {}
    for product in products:
        value = benchmark.benchmark_for(product, msrp, fx_rate, config.DUTY_PERCENT)
        if value is not None:
            benchmarks[product.slug] = value

    # Everything succeeded — only now is history written.
    db.record_run(run_id, products, started_at, _now(), fx_rate,
                  config.DUTY_PERCENT, "; ".join(notes))
    store.save(db, data_dir)

    scores = score.score_all(products, db, benchmarks)
    meta = {
        "run_id": run_id,
        "generated_at": started_at,
        "fx_rate": fx_rate,
        "fx_stale": fx_stale,
        "duty_percent": config.DUTY_PERCENT,
        "missing_msrp": benchmark.missing_keys(products, msrp),
        "product_count": len(products),
        "notes": notes,
        "benchmarks": benchmarks,
    }

    excel.build_workbook(products, scores, db, meta,
                         web_dir / "downloads" / "applemac-prices.xlsx")
    store.build_sqlite(db, web_dir / "downloads" / "prices.db")
    report.write_latest(products, scores, db, meta, web_dir / "data" / "latest.json")
    report.write_history(db, web_dir / "data" / "history.json")
    return meta


def _msrp_gaps():
    db = store.load(config.DATA_DIR)
    msrp = benchmark.load_msrp(config.DATA_DIR / "apple_msrp.json")
    keys = sorted({r["config_key"] for r in db.products.values()
                   if r["config_key"] not in msrp})
    if not keys:
        print("No gaps: every tracked config has an MSRP entry.")
        return 0
    print(f"{len(keys)} configs have no Apple MSRP. Add to data/apple_msrp.json:\n")
    for key in keys:
        print(f'  "{key}": 0,')
    print("\nReplace each 0 with the real Apple US price in USD.")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="scraper.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="scrape and rebuild outputs")
    run_parser.add_argument("--force", action="store_true",
                            help="accept large product-count drops")

    serve_parser = subparsers.add_parser("serve", help="local dashboard")
    serve_parser.add_argument("--port", type=int, default=8000)
    serve_parser.add_argument("--no-browser", action="store_true")

    subparsers.add_parser("msrp-gaps", help="list configs missing an Apple MSRP")

    args = parser.parse_args(argv)

    if args.command == "run":
        try:
            meta = run(force=args.force)
        except Exception as error:  # noqa: BLE001 - top level reports and exits
            print(f"RUN FAILED: {error}", file=sys.stderr)
            print("Nothing was written; previous data is intact.", file=sys.stderr)
            return 1
        print(f"OK: {meta['product_count']} products, run {meta['run_id']}")
        for note in meta["notes"]:
            print(f"  note: {note}")
        return 0

    if args.command == "serve":
        from .server import serve
        serve(port=args.port, open_browser=not args.no_browser)
        return 0

    return _msrp_gaps()


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Write `tests/test_report.py`**

```python
import json

from scraper import report, score, store
from tests.test_store import make_product


def test_latest_json_is_sorted_and_complete(tmp_path):
    products = [make_product("b", price=200000), make_product("a", price=100000)]
    db = store.Database()
    scores = score.score_all(products, db, {})
    meta = {"run_id": "r1", "generated_at": "x", "fx_rate": 277.5,
            "fx_stale": False, "duty_percent": 0.55, "missing_msrp": [],
            "product_count": 2, "notes": [], "benchmarks": {"a": 150000}}
    path = tmp_path / "latest.json"
    report.write_latest(products, scores, db, meta, path)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert [p["slug"] for p in payload["products"]] == ["a", "b"]
    assert payload["products"][0]["benchmark"] == 150000
    assert "scores" in payload["products"][0]
    assert "benchmarks" not in payload["meta"]


def test_history_json_groups_by_slug(tmp_path):
    db = store.Database()
    db.record_run("r1", [make_product("a", price=100000)], "2026-09-01T00:00:00",
                  "2026-09-01T00:01:00", 277.5, 0.55, "")
    db.record_run("r2", [make_product("a", price=90000)], "2026-09-02T00:00:00",
                  "2026-09-02T00:01:00", 277.5, 0.55, "")
    path = tmp_path / "history.json"
    report.write_history(db, path)
    series = json.loads(path.read_text(encoding="utf-8"))
    assert [point[1] for point in series["a"]] == [100000, 90000]
```

- [ ] **Step 6: Run all tests**

Run: `python -m pytest -v`
Expected: all pass (10 in `test_cli.py`, 2 in `test_report.py`, plus earlier tasks)

- [ ] **Step 7: Run it for real, once**

Run: `python -m scraper.cli run`
Expected: `OK: <n> products, run <id>`, and `data/history.csv`,
`web/data/latest.json`, `web/downloads/applemac-prices.xlsx` all created.

Open the workbook and confirm the three device sheets are sorted cheapest first.
Then run `python -m scraper.cli msrp-gaps` and confirm it prints paste-ready keys.

- [ ] **Step 8: Commit**

```bash
git add scraper/cli.py scraper/report.py tests/test_cli.py tests/test_report.py
git add data/ web/
git commit -m "feat: orchestration CLI with abort-on-bad-data guarantees"
```

---

### Task 10: Dual-mode dashboard

**Files:**
- Create: `web/index.html`, `scraper/server.py`, `run.bat`
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: `config.WEB_DIR`, `cli.run`.
- Produces: `make_handler(web_dir)` and `serve(port=8000, open_browser=True, web_dir=None, server_class=None)`.

The dashboard detects its mode by probing `/api/latest`: present → live mode with
a working refresh button; absent (GitHub Pages) → static mode reading
`data/latest.json`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_server.py`:

```python
import json
import threading
import urllib.error
import urllib.request
from http.server import HTTPServer

import pytest

from scraper import server


@pytest.fixture
def live_server(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "index.html").write_text("<html>dashboard</html>", encoding="utf-8")
    (tmp_path / "data" / "latest.json").write_text(
        json.dumps({"meta": {"run_id": "r1"}, "products": []}), encoding="utf-8")

    httpd = HTTPServer(("127.0.0.1", 0), server.make_handler(tmp_path))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()


def get(url):
    with urllib.request.urlopen(url, timeout=5) as response:
        return response.status, response.read().decode("utf-8")


def test_serves_dashboard_at_root(live_server):
    status, body = get(f"{live_server}/")
    assert status == 200
    assert "dashboard" in body


def test_api_latest_returns_json(live_server):
    status, body = get(f"{live_server}/api/latest")
    assert status == 200
    assert json.loads(body)["meta"]["run_id"] == "r1"


def test_unknown_path_is_404(live_server):
    with pytest.raises(urllib.error.HTTPError) as exc:
        get(f"{live_server}/nope.txt")
    assert exc.value.code == 404


def test_directory_traversal_is_blocked(live_server):
    with pytest.raises(urllib.error.HTTPError) as exc:
        get(f"{live_server}/../../etc/passwd")
    assert exc.value.code in (400, 403, 404)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_server.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scraper.server'`

- [ ] **Step 3: Write `scraper/server.py`**

```python
"""Local dashboard server. Binds 127.0.0.1 only; never exposed."""
import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from . import config

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
}


def make_handler(web_dir):
    web_dir = Path(web_dir).resolve()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # keep the console readable

        def _send(self, status, body, content_type="application/json"):
            payload = body if isinstance(body, bytes) else body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _safe_path(self, path):
            candidate = (web_dir / path.lstrip("/")).resolve()
            if not str(candidate).startswith(str(web_dir)):
                return None
            return candidate

        def do_GET(self):
            route = self.path.split("?")[0]
            if route in ("/", "/index.html"):
                return self._send(200, (web_dir / "index.html").read_bytes(),
                                  CONTENT_TYPES[".html"])
            if route == "/api/latest":
                target = web_dir / "data" / "latest.json"
                if not target.exists():
                    return self._send(404, '{"error":"no data yet"}')
                return self._send(200, target.read_bytes())
            if route == "/api/history":
                target = web_dir / "data" / "history.json"
                if not target.exists():
                    return self._send(404, '{"error":"no history yet"}')
                return self._send(200, target.read_bytes())

            target = self._safe_path(route)
            if target is None or not target.is_file():
                return self._send(404, '{"error":"not found"}')
            suffix = target.suffix.lower()
            return self._send(200, target.read_bytes(),
                              CONTENT_TYPES.get(suffix, "application/octet-stream"))

        def do_POST(self):
            if self.path != "/api/refresh":
                return self._send(404, '{"error":"not found"}')
            from .cli import run
            try:
                meta = run(web_dir=web_dir)
            except Exception as error:  # noqa: BLE001 - reported to the browser
                return self._send(500, json.dumps({"error": str(error)}))
            return self._send(200, json.dumps({
                "ok": True,
                "product_count": meta["product_count"],
                "run_id": meta["run_id"],
            }))

    return Handler


def serve(port=8000, open_browser=True, web_dir=None, server_class=HTTPServer):
    web_dir = web_dir or config.WEB_DIR
    httpd = server_class(("127.0.0.1", port), make_handler(web_dir))
    url = f"http://127.0.0.1:{httpd.server_port}"
    print(f"Dashboard: {url}   (Ctrl+C to stop)")
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        httpd.shutdown()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_server.py -v`
Expected: 4 passed

- [ ] **Step 5: Write `web/index.html`**

A single self-contained file. No CDN dependencies — it must work offline.

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>applemac.pk Price Tracker</title>
<style>
:root { --bg:#f6f6f7; --fg:#1d1d1f; --muted:#6e6e73; --card:#fff;
        --line:#e3e3e6; --good:#1a7f37; --bad:#c0392b; --accent:#0071e3; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#161617; --fg:#f5f5f7; --muted:#9a9a9e; --card:#1f1f21;
          --line:#303033; --good:#3fb950; --bad:#f85149; --accent:#2997ff; }
}
* { box-sizing:border-box; }
body { margin:0; padding:24px 16px; background:var(--bg); color:var(--fg);
       font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
.wrap { max-width:1400px; margin:0 auto; }
h1 { font-size:22px; margin:0 0 4px; }
.sub { color:var(--muted); margin-bottom:20px; }
.stale { background:#c0392b; color:#fff; padding:8px 12px; border-radius:8px;
         margin-bottom:16px; }
.bar { display:flex; gap:8px; flex-wrap:wrap; align-items:center;
       margin-bottom:18px; }
button, select, input[type=search] { font:inherit; padding:7px 12px;
  border:1px solid var(--line); border-radius:8px; background:var(--card);
  color:var(--fg); }
button.primary { background:var(--accent); color:#fff; border-color:transparent;
  cursor:pointer; }
button.primary:disabled { opacity:.5; cursor:default; }
.cards { display:grid; gap:12px; margin-bottom:24px;
  grid-template-columns:repeat(auto-fill,minmax(260px,1fr)); }
.card { background:var(--card); border:1px solid var(--line); border-radius:12px;
        padding:14px; }
.card .name { font-weight:600; margin-bottom:6px; }
.card .price { font-size:19px; font-weight:700; }
.score { display:inline-block; padding:2px 8px; border-radius:99px;
         background:var(--good); color:#fff; font-size:12px; font-weight:600; }
.tablewrap { overflow-x:auto; background:var(--card);
             border:1px solid var(--line); border-radius:12px; }
table { border-collapse:collapse; width:100%; min-width:900px; }
th, td { padding:8px 10px; text-align:left; border-bottom:1px solid var(--line);
         white-space:nowrap; }
th { cursor:pointer; user-select:none; font-size:12px; color:var(--muted);
     position:sticky; top:0; background:var(--card); }
td.num, th.num { text-align:right; }
.down { color:var(--good); } .up { color:var(--bad); }
a { color:var(--accent); text-decoration:none; }
.muted { color:var(--muted); }
#log { white-space:pre-wrap; font-family:ui-monospace,monospace; font-size:12px;
       color:var(--muted); margin-top:8px; }
</style>
</head>
<body>
<div class="wrap">
  <h1>applemac.pk Price Tracker</h1>
  <div class="sub" id="subtitle">Loading…</div>
  <div id="staleWarning"></div>

  <div class="bar">
    <button class="primary" id="refresh" hidden>Refresh Prices</button>
    <select id="family">
      <option value="">All families</option>
      <option value="macbook_pro">MacBook Pro</option>
      <option value="macbook_air">MacBook Air</option>
      <option value="iphone">iPhone</option>
    </select>
    <input type="search" id="search" placeholder="Filter by name…">
    <a id="xlsx" href="downloads/applemac-prices.xlsx">Excel</a>
    <a id="db" href="downloads/prices.db">Database</a>
  </div>
  <div id="log"></div>

  <h2 style="font-size:16px;">Top deals</h2>
  <div class="cards" id="cards"></div>

  <div class="tablewrap">
    <table>
      <thead><tr id="head"></tr></thead>
      <tbody id="rows"></tbody>
    </table>
  </div>
</div>

<script>
const COLUMNS = [
  {key:"name",     label:"Product",          type:"text"},
  {key:"price",    label:"Price",            type:"money"},
  {key:"delta",    label:"Δ Last Run",       type:"delta"},
  {key:"benchmark",label:"Est. Apple Landed",type:"money"},
  {key:"chip",     label:"Chip",             type:"text"},
  {key:"ram_gb",   label:"RAM",              type:"num"},
  {key:"storage_gb",label:"Storage",         type:"num"},
  {key:"deal",     label:"Deal Score",       type:"num"},
];

let state = {products:[], meta:{}, sort:"deal", dir:-1, live:false};

const pkr = n => n == null ? "—" : "PKR " + n.toLocaleString("en-US");

async function boot() {
  let payload = null;
  try {
    const live = await fetch("api/latest", {cache:"no-store"});
    if (live.ok) { payload = await live.json(); state.live = true; }
  } catch (e) { /* static mode */ }
  if (!payload) {
    try {
      payload = await (await fetch("data/latest.json", {cache:"no-store"})).json();
    } catch (e) {
      document.getElementById("subtitle").textContent =
        "No data yet. Run the scraper to populate the dashboard.";
      return;
    }
  }
  state.products = payload.products || [];
  state.meta = payload.meta || {};
  document.getElementById("refresh").hidden = !state.live;
  render();
}

function ageWarning(generatedAt) {
  if (!generatedAt) return "";
  const days = (Date.now() - new Date(generatedAt)) / 86400000;
  if (days < 3) return "";
  return `<div class="stale">Data is ${Math.floor(days)} days old —
          the last scheduled run may have failed.</div>`;
}

function render() {
  const m = state.meta;
  document.getElementById("subtitle").innerHTML =
    `${state.products.length} products · updated ${m.generated_at || "—"}
     · USD→PKR ${m.fx_rate ?? "—"}${m.fx_stale ? " (stale)" : ""}
     · duty ${m.duty_percent != null ? Math.round(m.duty_percent*100) + "%" : "—"}
     <span class="muted">· “Est. Apple Landed” is an estimate, not an official price</span>`;
  document.getElementById("staleWarning").innerHTML = ageWarning(m.generated_at);

  const head = document.getElementById("head");
  head.innerHTML = COLUMNS.map(c =>
    `<th class="${c.type === "text" ? "" : "num"}" data-key="${c.key}">${c.label}</th>`
  ).join("");
  head.querySelectorAll("th").forEach(th => th.onclick = () => {
    const key = th.dataset.key;
    state.dir = state.sort === key ? -state.dir : -1;
    state.sort = key;
    renderRows();
  });

  const ranked = [...state.products]
    .sort((a,b) => b.scores.deal_score - a.scores.deal_score).slice(0,6);
  document.getElementById("cards").innerHTML = ranked.map(p => `
    <div class="card">
      <div class="name"><a href="${p.url}" target="_blank" rel="noopener">${p.name}</a></div>
      <div class="price">${pkr(p.price)}</div>
      <div class="muted" style="margin:6px 0;">
        ${p.benchmark ? "Est. Apple Landed " + pkr(p.benchmark) : "No Apple benchmark"}
      </div>
      <span class="score">Deal ${p.scores.deal_score}</span>
      <span class="muted"> · ${p.scores.confidence}/5 signals</span>
    </div>`).join("");

  renderRows();
}

function renderRows() {
  const family = document.getElementById("family").value;
  const term = document.getElementById("search").value.toLowerCase();
  const value = (p, key) => key === "deal" ? p.scores.deal_score : p[key];

  const rows = state.products
    .filter(p => !family || p.family === family)
    .filter(p => !term || p.name.toLowerCase().includes(term))
    .sort((a,b) => {
      const x = value(a, state.sort), y = value(b, state.sort);
      if (x == null) return 1;
      if (y == null) return -1;
      return (x > y ? 1 : x < y ? -1 : 0) * state.dir;
    });

  document.getElementById("rows").innerHTML = rows.map(p => `<tr>${
    COLUMNS.map(c => {
      const v = value(p, c.key);
      if (c.type === "money") return `<td class="num">${pkr(v)}</td>`;
      if (c.type === "delta") {
        if (v == null || v === 0) return `<td class="num muted">—</td>`;
        return `<td class="num ${v < 0 ? "down" : "up"}">
                ${v < 0 ? "▼" : "▲"} ${pkr(Math.abs(v))}</td>`;
      }
      if (c.key === "name")
        return `<td><a href="${p.url}" target="_blank" rel="noopener">${p.name}</a></td>`;
      return `<td class="${c.type === "num" ? "num" : ""}">${v ?? "—"}</td>`;
    }).join("")
  }</tr>`).join("");
}

document.getElementById("family").onchange = renderRows;
document.getElementById("search").oninput = renderRows;
document.getElementById("refresh").onclick = async () => {
  const button = document.getElementById("refresh");
  const log = document.getElementById("log");
  button.disabled = true;
  button.textContent = "Scraping… (about 30s)";
  log.textContent = "";
  try {
    const response = await fetch("api/refresh", {method:"POST"});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "run failed");
    log.textContent = `Done: ${result.product_count} products.`;
    await boot();
  } catch (error) {
    log.textContent = "FAILED: " + error.message +
      "\nPrevious data is intact.";
  } finally {
    button.disabled = false;
    button.textContent = "Refresh Prices";
  }
};

boot();
</script>
</body>
</html>
```

- [ ] **Step 6: Write `run.bat`**

```bat
@echo off
cd /d "%~dp0"
echo Installing dependencies if needed...
python -m pip install -q -r requirements.txt
echo Scraping current prices...
python -m scraper.cli run
if errorlevel 1 (
  echo.
  echo Scrape failed. Previous data is intact. Opening the dashboard anyway.
  echo.
)
python -m scraper.cli serve
pause
```

- [ ] **Step 7: Verify manually**

Run: `python -m scraper.cli serve`
Confirm: the browser opens, the table renders, the **Refresh Prices** button
appears and works, and sorting by clicking a header works.

Then open `web/index.html` directly from disk (`file://`) and confirm it still
renders using `data/latest.json` with the refresh button hidden — that is static
mode, exactly what GitHub Pages serves.

- [ ] **Step 8: Commit**

```bash
git add scraper/server.py web/index.html run.bat tests/test_server.py
git commit -m "feat: dual-mode dashboard with local server and one-click runner"
```

---

### Task 11: GitHub Actions automation and Pages

**Files:**
- Create: `.github/workflows/scrape.yml`, `.github/workflows/keepalive.yml`
- Modify: `README.md`

**Interfaces:**
- Consumes: `python -m scraper.cli run`.
- Produces: nothing importable. This task automates what already works.

- [ ] **Step 1: Write `.github/workflows/scrape.yml`**

```yaml
name: Scrape prices

on:
  schedule:
    - cron: "17 3 * * *"   # 08:17 PKT daily; off-the-hour to avoid peak queueing
  workflow_dispatch:

permissions:
  contents: write
  pages: write
  id-token: write

concurrency:
  group: scrape
  cancel-in-progress: false

jobs:
  scrape:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
          cache: pip

      - run: pip install -r requirements.txt

      - name: Run test suite
        run: python -m pytest -q

      - name: Scrape
        run: python -m scraper.cli run

      - name: Commit updated data
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add data/ web/
          if git diff --staged --quiet; then
            echo "No changes to commit."
          else
            git commit -m "chore: price data $(date -u +%Y-%m-%d)"
            git push
          fi

      - uses: actions/configure-pages@v5
      - uses: actions/upload-pages-artifact@v3
        with:
          path: web
      - id: deployment
        uses: actions/deploy-pages@v4
```

Note the ordering: tests run **before** the scrape, so a broken parser fails the
job without touching data. If the scrape aborts, `cli.py` exits non-zero, the job
stops, nothing is committed, and the previously deployed dashboard stays up.

- [ ] **Step 2: Write `.github/workflows/keepalive.yml`**

```yaml
name: Keepalive

# Public repositories disable scheduled workflows after 60 days without
# repository activity, and only commits reset that timer. Daily scrape
# commits normally suffice, but commits made with GITHUB_TOKEN are not
# always counted. This monthly commit is the cheap insurance.

on:
  schedule:
    - cron: "0 6 1 * *"   # 1st of each month
  workflow_dispatch:

permissions:
  contents: write

jobs:
  keepalive:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          date -u +"%Y-%m-%dT%H:%M:%SZ" > .keepalive
          git add .keepalive
          git commit -m "chore: keepalive" || exit 0
          git push
```

- [ ] **Step 3: Push and enable Pages**

```bash
git add .github/
git commit -m "ci: daily scrape workflow with Pages deploy and keepalive"
git push -u origin main
```

Then in the repository on GitHub:
1. **Settings → Pages → Source → GitHub Actions**.
2. **Actions → Scrape prices → Run workflow** to trigger the first run manually.

- [ ] **Step 4: Verify the automation end to end**

Confirm all four:
1. The workflow run is green.
2. A `chore: price data …` commit appeared.
3. The Pages URL serves the dashboard with real data.
4. The Excel and Database links download working files.

If Pages 404s, confirm Settings → Pages source is set to **GitHub Actions**, not
a branch.

- [ ] **Step 5: Verify a failing scrape is safe**

Temporarily break the parser to prove the guarantee holds:

```bash
git checkout -b test-failure
# In scraper/parse.py, change find(id="main_categoryinner") to
# find(id="does-not-exist"), then commit and run the workflow on this branch.
```

Expected: the job fails red, **no data commit appears**, and the deployed
dashboard still shows the previous run. Then delete the branch — this is a
verification exercise, not a change to keep.

```bash
git checkout main && git branch -D test-failure
```

- [ ] **Step 6: Add the Pages URL and automation notes to `README.md`**

Insert after the title:

```markdown
**Live dashboard:** https://<username>.github.io/<repo>/

Scrapes daily at 03:17 UTC (08:17 PKT). To run on demand, use
**Actions → Scrape prices → Run workflow** — works from a phone.
```

- [ ] **Step 7: Commit**

```bash
git add README.md
git commit -m "docs: dashboard URL and automation notes"
git push
```

---

### Task 12: Populate Apple MSRP data

**Files:**
- Modify: `data/apple_msrp.json`

**Interfaces:**
- Consumes: `python -m scraper.cli msrp-gaps`.
- Produces: a populated MSRP table, activating the `vs_apple` signal.

This task is deliberately last: it needs real `config_key` values, which only
exist after a successful run.

- [ ] **Step 1: List the gaps**

Run: `python -m scraper.cli msrp-gaps`
Expected: paste-ready lines such as `"macbook_pro_14_0_m5_32_1024": 0,`

- [ ] **Step 2: Fill in real Apple US prices**

For each key, look up the **current** price on apple.com for the matching
configuration and replace the `0`. Verify each one against apple.com —
**do not estimate, interpolate, or recall prices from memory.** A wrong MSRP
silently corrupts the `vs_apple` signal on every future run.

Where no Apple equivalent exists (a configuration Apple never sold, or a
bundle), leave the key out entirely. Absent scores `None`, which is honest;
a guessed number is not.

Set `_meta.checked` to today's date.

- [ ] **Step 3: Re-run and sanity-check the benchmark**

Run: `python -m scraper.cli run`

Open the workbook and compare `Est. Apple Landed` against `Price (PKR)` for a
few products you know well. If the estimate is consistently far from what these
actually cost in Pakistan, adjust `DUTY_PERCENT` in `scraper/config.py` and
re-run. This is a calibration dial, not a constant to get right on paper.

- [ ] **Step 4: Confirm the signal is active**

Run: `python -m scraper.cli msrp-gaps`
Expected: noticeably fewer gaps, and `vs Apple %` populated in the workbook.

- [ ] **Step 5: Commit**

```bash
git add data/apple_msrp.json scraper/config.py
git commit -m "data: Apple US MSRP reference and calibrated duty rate"
git push
```

---

## Verification Checklist

Run before calling this done:

- [ ] `python -m pytest -v` — all pass, live test deselected
- [ ] `python -m pytest -m live -v` — passes against the real site
- [ ] `python -m scraper.cli run` twice — history accumulates, no duplicate rows
- [ ] `data/history.csv` grows; no existing row is ever modified
- [ ] Workbook opens; three device sheets sorted cheapest first; `Est. Apple Landed` header present; no header claims to be an official Apple price
- [ ] Dashboard works both from `file://` (static) and `cli serve` (live)
- [ ] A deliberately broken parser fails the run and writes nothing
- [ ] Actions run is green, commits data, and deploys Pages
