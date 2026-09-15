# applemac.pk Price Tracker — Design

**Date:** 2026-09-15
**Status:** Approved for planning

## Purpose

Track prices for a defined slice of the applemac.pk catalogue — MacBook Pro 14",
MacBook Pro 16", MacBook Air 13", MacBook Air 15", and current-generation iPhones —
so the operator can identify which listing represents the best buy at any moment.

The tool answers three questions:

1. What is available, and at what price, sorted cheapest first?
2. How has each price moved since previous runs?
3. Which listing is the best value right now, and why?

Output is an Excel workbook plus a local web dashboard. Everything runs on one
machine, offline except for the scrape itself.

## Non-goals

- No purchasing, cart interaction, or account access.
- No other retailers. Single-site tool.
- No hosting. The dashboard is local only.
- No Apple Watch, iPad, Mac desktop, or accessory categories.

## Site reconnaissance (verified 2026-09-15)

These facts were confirmed against the live site and drive the design.

- **Category pages are server-rendered.** Prices are present in the initial HTML.
  No JavaScript execution, headless browser, or API reverse-engineering is needed.
- **Pagination is client-side.** A single GET returns every product in a category.
  There is no `?page=` crawl to perform — which also keeps us clear of the
  `Disallow: /?page=` rule.
- **Product cards carry structured attributes.** Each card is a `div.pdt` with
  `data-price`, `data-ram`, `data-ssd`, `data-processor`, `data-cpu`, `data-gpu`,
  `data-screensize`, `data-color`, `data-storage`, `data-displaysize`.
  Specs do not need to be parsed out of free text.
- **Displayed price** lives in `div.product-price-4` as `span.new-price` and
  `span.old-price`, formatted `PKR 772,000`. On many cards the two are equal.
  `data-price` is the authoritative numeric value; `new-price` is a cross-check.
- **Identity.** The product URL slug (`/product/<slug>`) is stable and unique.
  It is the primary key across runs.

Verified live card counts:

| Category | Cards |
|---|---|
| `macbook-pro-14` | 58 |
| `macbook-pro-16` | 33 |
| `macbook-air-13` | 37 |
| `macbook-air-15` | 36 |
| `iphone-17-pro-max` | 4 |
| `iphone-air-series` | 3 |
| `iphone` (aggregate) | 29 |
| `iphone-16-series` | 0 |

### iPhone coverage requires leaf categories

The aggregate `/category/iphone` page is **not** complete (29 items), and some
series-level pages are empty (`iphone-16-series` → 0) while their leaf
categories are populated. iPhone coverage is therefore built as the **union of
leaf categories, deduplicated by slug**.

After each run the scraper cross-checks its collected slugs against the
`sitemap.xml` product list and reports any `/product/*iphone*` slug that no
category yielded. This catches new categories the operator has not configured
yet. It reports; it does not fail the run.

## robots.txt compliance

```
User-agent: *
Disallow: /index.php/   /?page=   /cart/   /public/
```

Category pages and the sitemap are permitted. The scraper touches no disallowed
path. Image URLs under `/public/` are recorded as strings only and never fetched.
Requests are spaced 1.5s apart with a descriptive User-Agent — roughly 14
requests per run, lighter than a person browsing the catalogue.

## Architecture

```
applemac.pk/
├─ run.bat                    one-click entry point
├─ requirements.txt
├─ scraper/
│   ├─ config.py              categories, weights, FX and duty settings
│   ├─ fetch.py               HTTP: rate limiting, retry, response caching
│   ├─ parse.py               HTML → Product records
│   ├─ normalize.py           spec parsing, model grouping
│   ├─ store.py               SQLite persistence and history queries
│   ├─ benchmark.py           Apple MSRP + FX → estimated landed PKR
│   ├─ score.py               deal scoring
│   ├─ excel.py               workbook builder
│   ├─ server.py              local HTTP server and dashboard API
│   └─ cli.py                 entry point, orchestration
├─ data/
│   ├─ prices.db              SQLite price history
│   ├─ apple_msrp.json        curated reference, operator-editable
│   ├─ fx_cache.json          last known USD→PKR rate
│   └─ latest.json            dashboard snapshot
├─ web/dashboard.html
├─ output/
│   ├─ applemac-prices-latest.xlsx
│   └─ archive/applemac-prices-YYYY-MM-DD.xlsx
├─ tests/
│   └─ fixtures/              saved category HTML
└─ docs/
```

Only `fetch.py` performs network I/O. Every other module is tested offline
against saved HTML fixtures.

**Dependencies:** `requests`, `beautifulsoup4`, `openpyxl`. Standard library
otherwise (`sqlite3`, `http.server`, `json`, `dataclasses`).

## Module contracts

### `config.py`
Holds `CATEGORIES` (slug → family mapping), scoring weights, `DUTY_PERCENT`,
`REQUEST_DELAY`, and path constants. Pure data, no logic.

Families: `macbook_pro` (14, 16), `macbook_air` (13, 15), `iphone` (new stock).
Categories whose slug contains `-old` or `-used` are excluded by configuration.

### `fetch.py`
`fetch_category(slug) -> str`

Rate-limited GET with retry on transient failures (3 attempts, exponential
backoff). Raises `FetchError` on permanent failure. Caches raw HTML per run
under `data/cache/<run_id>/` so parsing can be re-run and debugged without
re-hitting the site.

### `parse.py`
`parse_category(html, slug) -> list[RawProduct]`

Extracts every `div.pdt` card. `RawProduct` carries slug, URL, name, image URL,
`data-price`, displayed new/old price strings, and the raw spec attributes.

Returns an empty list for a genuinely empty category rather than raising —
deciding whether zero is a failure needs the previous run's counts, which
`parse.py` does not have. That judgement belongs to `cli.py`, per the failure
table below. `ParseError` is reserved for markup that no longer matches at all:
a page with listing containers but no recognizable `div.pdt` cards.

### `normalize.py`
`normalize(raw, family) -> Product`

Parses `"32GB"` → 32, `"1TB"` → 1024 (GB), `"10 Core CPU"` → 10,
`"14 Inches"` → 14.0. Derives `model_group`, the key used for peer comparison:
family + screen size + chip (e.g. `macbook_pro_14_m5_pro`), and `config_key`,
a tighter grouping that adds RAM and SSD for like-for-like comparison.

Unparseable specs become `None` rather than raising. The product still tracks;
it simply scores `None` on spec-dependent signals.

### `store.py`
SQLite, three tables:

```sql
runs      (run_id PK, started_at, finished_at, status,
           fx_rate, duty_percent, product_count, notes)

products  (slug PK, url, name, family, model_group, config_key,
           ram_gb, ssd_gb, chip, cpu_cores, gpu_cores,
           screen_size, color, image_url, first_seen, last_seen)

snapshots (id PK, run_id FK, slug FK, price, old_price, seen_at)
```

Snapshots are append-only; nothing is overwritten. `products` rows update in
place when specs or names change, with `last_seen` refreshed each run.

Query helpers: `price_history(slug)`, `previous_run()`, `median_price(slug, days)`,
`changes_since(run_id)`.

### `benchmark.py`
`apple_msrp.json` maps a config key to a USD MSRP:

```json
{
  "_meta": {
    "source": "Apple US online store",
    "checked": "2026-09-15",
    "note": "Update when Apple refreshes a lineup."
  },
  "macbook_pro_14_m5_16_512": 1599,
  "iphone_17_pro_max_256": 1199
}
```

The seed values must be verified against apple.com at implementation time
rather than recalled from memory. Any config with no entry scores `None` on the
vs-Apple signal and is flagged in the Summary sheet so gaps are visible.

`estimated_landed_pkr = usd_msrp * fx_rate * (1 + duty_percent)`

The USD→PKR rate is fetched from a free FX endpoint each run and cached; on
failure the last cached rate is reused and the run is annotated as using a
stale rate.

**This is explicitly an estimate.** Real landed cost varies with duty category,
PTA registration tax on phones, and import route. The column is labelled
**"Est. Apple Landed"**, never "Apple price", and the FX rate and duty percent
used are printed in the Summary sheet and in every workbook header so a number
can always be traced to its inputs.

### `score.py`
Five independent signals, each returning 0–100 or `None`:

| Signal | Definition |
|---|---|
| `vs_apple` | percent below Est. Apple Landed |
| `vs_history` | percent below the product's own 90-day median |
| `vs_peers` | percentile rank (cheapest = best) within `config_key` |
| `spec_value` | PKR per GB of RAM+SSD, ranked within `model_group` |
| `site_discount` | `(old_price - price) / old_price` |

`deal_score` is the weighted mean of available signals, renormalized over the
non-`None` ones so missing data lowers confidence rather than the score.
A `confidence` field records how many signals contributed.

All five component values appear as columns in the Excel sheets. A composite
that cannot be explained is not actionable, so the breakdown always travels
with the score.

### `excel.py`
Three device sheets, sorted ascending by price:

1. **MacBook Pro** — 14" and 16" combined
2. **MacBook Air** — 13" and 15" combined
3. **iPhone** — current generation only

Columns: Name (hyperlinked), Screen, Chip, RAM, SSD, CPU, GPU, Color, Price,
Old Price, Est. Apple Landed, vs Apple %, Δ Since Last Run, vs History, vs Peers,
Spec Value, **Deal Score**, Confidence, First Seen.

Formatting: frozen header row, autofilter, `#,##0` PKR number format, colour
scale on Deal Score, red/green on Δ Since Last Run.

Two support sheets:

- **Summary** — run timestamp, FX rate, duty percent, per-family counts,
  MSRP coverage gaps, and the top 15 deals across all families.
- **Price Changes** — every product whose price moved since the previous run,
  with direction, absolute delta and percent, sorted by largest drop first.

Writes `output/applemac-prices-latest.xlsx` and a dated archive copy.

### `server.py` and `web/dashboard.html`
`run.bat` starts `python -m scraper.cli serve`, which binds `127.0.0.1` on a free
port and opens the browser.

Endpoints:

| Route | Purpose |
|---|---|
| `GET /` | dashboard HTML |
| `GET /api/latest` | current snapshot with scores |
| `POST /api/refresh` | trigger a scrape, stream progress |
| `GET /api/history/<slug>` | price series for sparklines |
| `POST /api/open-excel` | open the workbook in the default handler |

The dashboard shows last-run time, a **Refresh Prices** button with live
progress, top-deal cards, a sortable and filterable table, per-product price
sparklines, and sliders for the scoring weights that re-rank client-side
without re-scraping. Bound to localhost only.

## Failure handling

A silently partial scrape is the main risk: it would write a wrong history that
every later comparison inherits. The run is therefore transactional.

| Condition | Response |
|---|---|
| Category returns 0 cards **and had products in the previous run** | Abort run, keep previous data, report which category |
| Category returns 0 cards and was empty or unseen before | Skip with a note — an empty series page is a legitimate state |
| Category count drops >20% vs previous run | Abort, report, require `--force` to accept |
| HTTP failure after 3 retries | Abort, keep previous data |
| FX lookup fails | Continue with cached rate, annotate the run |
| Missing MSRP entry | Continue, `vs_apple` is `None`, list the gap in Summary |
| Unparseable spec field | Continue, field is `None`, product still tracked |

Snapshots are written only after every category parses successfully. A failed
run leaves `prices.db` exactly as it was.

## Testing

TDD with `pytest`. Saved category HTML in `tests/fixtures/` — one real page per
family, plus deliberately broken pages (empty listing, altered markup, missing
price attribute).

- `parse.py` — correct card count and field extraction from real fixtures;
  `ParseError` on the empty fixture.
- `normalize.py` — spec string parsing including malformed input.
- `store.py` — append-only behaviour, history queries, in-place product updates.
- `benchmark.py` — landed-price arithmetic, cached-rate fallback, missing entries.
- `score.py` — each signal independently; renormalization when signals are `None`.
- `excel.py` — workbook opens, sheets present, rows sorted ascending.

Network tests are excluded from the default run. One opt-in integration test
(`--live`) fetches a single real category to detect upstream markup changes.

## Known limitations

These are stated so the output is not over-trusted:

1. **History needs time.** `vs_history` and the sparklines are empty on the
   first run and become meaningful after roughly two weeks of daily runs. The
   other four signals work immediately.
2. **The Apple benchmark is an estimate**, not a landed cost. See `benchmark.py`.
3. **Listed price is not availability.** Category pages do not reliably indicate
   stock. A top-scoring deal may not be purchasable; confirm with the seller.
4. **MSRP data is manual.** New Apple configurations score `None` on `vs_apple`
   until added to `apple_msrp.json`. Gaps are surfaced, never hidden.
5. **Markup changes will break parsing.** This is expected and detected loudly
   rather than absorbed silently.

## Appendix: configured categories

The exact starting set. `iphone` is included as a catch-all and contributes only
slugs the leaf categories missed; duplicates collapse on slug.

| Family | Category slugs |
|---|---|
| `macbook_pro` | `macbook-pro-14`, `macbook-pro-16` |
| `macbook_air` | `macbook-air-13`, `macbook-air-15` |
| `iphone` | `iphone-16`, `iphone-16-plus`, `iphone-16-pro`, `iphone-16-pro-max`, `iphone-16e`, `iphone-17`, `iphone-17-pro`, `iphone-17-pro-max`, `iphone-17e`, `iphone-18-pro`, `iphone-18-pro-max`, `iphone-air-series`, `iphone` |

Excluded by rule: any slug containing `-old` or `-used`, plus `iphone-se`,
`iphone-14*` and `iphone-15*` as previous-generation stock. Empty categories
(`iphone-16-series` currently returns 0) are skipped with a note rather than
treated as a failure, since emptiness is a real state for a series page.

To track another line, add its slug here — no code change.

## Build order

1. `fetch` + `parse` + `normalize` → products on stdout
2. `store` → history persists across runs
3. `excel` → usable workbook (**first genuinely useful milestone**)
4. `benchmark` + `score` → deal ranking
5. `server` + dashboard + `run.bat` → one-click operation

Each stage leaves a working tool. Stopping after stage 3 still yields a sorted
price sheet.
