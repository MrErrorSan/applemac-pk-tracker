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

Output is an Excel workbook plus a web dashboard. The scrape runs unattended on
a daily schedule in GitHub Actions and publishes to GitHub Pages, so history
accumulates without the operator needing to remember anything. The identical
code also runs locally on demand.

## Non-goals

- No purchasing, cart interaction, or account access.
- No other retailers. Single-site tool.
- No server to administer. Hosting is GitHub Pages serving static files.
- No paid infrastructure. The whole system stays inside free tiers.
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
├─ run.bat                    one-click local entry point
├─ requirements.txt
├─ LICENSE                    MIT
├─ .github/workflows/
│   ├─ scrape.yml             daily cron + manual dispatch + Pages deploy
│   └─ keepalive.yml          monthly no-op commit (see Deployment)
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
├─ data/                    committed to git — the canonical record
│   ├─ history.csv            append-only price snapshots
│   ├─ products.csv           identity + specs
│   ├─ apple_msrp.json        curated reference, operator-editable
│   └─ fx_cache.json          last known USD→PKR rate
├─ web/                     published to GitHub Pages
│   ├─ index.html             dashboard
│   ├─ data/latest.json       current snapshot with scores
│   ├─ data/history.json      per-product series for sparklines
│   └─ downloads/
│       ├─ applemac-prices.xlsx
│       └─ prices.db          generated SQLite, for offline analysis
├─ build/                   gitignored scratch (raw HTML cache)
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
under `build/cache/<run_id>/` (gitignored) so parsing can be re-run and
debugged without re-hitting the site.

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

**Canonical storage is CSV in git, not the SQLite file.** Two committed files:

- `data/products.csv` — one row per slug: identity and specs, updated in place.
- `data/history.csv` — append-only, one row per product per run:
  `run_id, slug, price, old_price, seen_at`.

Text was chosen over a binary `.db` deliberately. A committed SQLite file
rewrites wholly on every run, so a year of daily commits bloats the repository
and yields diffs no human can read. Append-only CSV diffs show exactly which
prices moved, stay reviewable in ten years, and keep clone size small.

`data/runs.csv` records per-run metadata: `run_id, started_at, finished_at,
status, fx_rate, duty_percent, product_count, notes`.

SQLite is still used — built fresh in memory (or at
`web/downloads/prices.db`) from the CSVs at the start of each run, which makes
history queries easy to express and gives the operator a real database to
download. It is a derived artifact; deleting it loses nothing.

Schema of the derived database:

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

Load and save are the boundary: `load() -> Database` reads the CSVs, and
`save(db)` writes them back atomically (temp file then rename) so an interrupted
run cannot leave a truncated history.

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

Writes `web/downloads/applemac-prices.xlsx`, published with the dashboard and
downloadable from it. Dated archive copies are not kept as files — git history
already holds every prior version of the underlying CSVs, and any past
workbook can be regenerated from them.

### `server.py` and `web/index.html`

The dashboard is **one HTML file that works in two modes**, detected at load time
by whether `/api/latest` responds:

**Static mode (GitHub Pages).** Fetches `data/latest.json` and
`data/history.json` as plain files. Everything renders: deal cards, sortable
table, sparklines, weight sliders. Fully functional, read-only.

**Live mode (local `run.bat`).** `python -m scraper.cli serve` binds `127.0.0.1`
on a free port and opens the browser, adding a working **Refresh Prices** button.

| Route | Purpose |
|---|---|
| `GET /` | dashboard HTML |
| `GET /api/latest` | current snapshot with scores |
| `POST /api/refresh` | trigger a scrape, stream progress |
| `GET /api/history/<slug>` | price series for sparklines |
| `POST /api/open-excel` | open the workbook in the default handler |

Scoring-weight sliders re-rank client-side in both modes, with no re-scrape.
The server binds localhost only and is never exposed.

**Why the hosted dashboard has no refresh button.** Triggering a workflow from a
static page requires an API token in client-side JavaScript, where anyone can
read it. The hosted page instead links to the repository's *Run workflow*
button — one click, works from a phone, no credential exposed.

## Deployment and automation

One platform: GitHub. No other account or service is required.

```
.github/workflows/scrape.yml   (cron: daily + workflow_dispatch)
   ├─ checkout, install deps
   ├─ python -m scraper.cli run
   ├─ commit data/*.csv and web/ if anything changed
   └─ deploy web/ to GitHub Pages
```

**Repository is public**, which gives unlimited Actions minutes and free Pages
hosting. The operator accepted that the collected price history and dashboard
are publicly visible. The data itself is public retail pricing; what becomes
visible is the *analysis* — which listings are judged good value.

**Schedule: daily.** Verified against the free limits, the job is roughly 2
minutes and ~14 outbound requests, far inside every quota.

**Manual runs** via `workflow_dispatch` — a *Run workflow* button in the Actions
tab, usable from any device.

### The 60-day inactivity rule

In a public repository, scheduled workflows are disabled automatically after 60
days with no repository activity, and **only new commits reset that timer** —
tags, issues and merged PRs do not. Daily runs commit price data, so the
schedule sustains itself.

Reports persist, however, of workflows being disabled despite automated commits,
since commits made with `GITHUB_TOKEN` are not consistently treated as activity.
The mitigation is cheap, so it is included rather than gambled on:
`keepalive.yml` runs monthly and makes a trivial commit. GitHub also emails
before disabling, and re-enabling is one click.

### Backup

Every run is a commit, so `git clone` retrieves the complete history *and every
prior version of it* — strictly better than a periodic database export, and it
needs no discipline from the operator. The generated `prices.db` and `.xlsx`
are also downloadable directly from the dashboard.

### Local use is unchanged

`run.bat` still performs a full local scrape, writes the same CSVs and workbook,
and serves the live dashboard. The same `scraper.cli` entry point runs in CI and
locally — no CI-only code path exists, so what is tested locally is what runs
unattended.

## License

MIT, in `LICENSE` at the repository root.

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
run leaves `data/history.csv` exactly as it was.

**In CI this matters more than locally.** An aborted run must exit non-zero,
commit nothing, and leave the previous dashboard published — a visibly stale
dashboard is far better than a silently wrong one. The failure surfaces as a
red run in the Actions tab and an email from GitHub. The dashboard also displays
its data's age prominently, so a stale page announces itself rather than looking
current.

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
   rather than absorbed silently. Unattended running raises the stakes: a break
   means the schedule stops collecting until fixed, so failures must be noisy.
6. **Scheduled runs can be delayed** during periods of heavy GitHub Actions
   load, and heavily queued jobs may occasionally be dropped. At a daily
   cadence an occasional missed or late run is immaterial.
7. **The repository is public.** The price history and the deal analysis are
   visible to anyone, including the retailer being tracked.

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
2. `store` → history persists across runs as CSV
3. `excel` → usable workbook (**first genuinely useful milestone**)
4. `benchmark` + `score` → deal ranking
5. `server` + dashboard + `run.bat` → one-click local operation
6. `.github/workflows/` + Pages → unattended daily runs, hosted dashboard

Each stage leaves a working tool. Stopping after stage 3 still yields a sorted
price sheet. Stage 6 is what closes the data-gap problem, but it is deliberately
last: automating a scraper that has not been validated against real data would
just accumulate wrong history unattended.
