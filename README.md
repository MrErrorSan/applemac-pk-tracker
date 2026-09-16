# applemac.pk Price Tracker

A price tracker for [applemac.pk](https://applemac.pk), a Pakistani Apple
reseller. It watches MacBook Pro 14"/16", MacBook Air 13"/15", and current
iPhones, keeps an append-only price history in git, ranks every listing by
a deal score, and serves the result as a dashboard. It runs itself daily
via GitHub Actions and publishes to GitHub Pages — no server to maintain.

**Live dashboard:** <https://mrerrorsan.github.io/applemac-pk-tracker/>

## Why

A catalogue page tells you today's price. It can't tell you whether that
price is actually good, or whether it just dropped. This tool answers both:
it compares every listing against Apple's own US pricing, against the
product's own price history, and against similarly-configured listings on
the same site — then ranks everything by a single, explainable deal score.

## Quick start

Requires [uv](https://docs.astral.sh/uv/) (Python is pinned via
`requires-python` and installed automatically by uv if needed).

```
uv sync
uv run python -m scraper.cli run      # scrape, update history, rebuild outputs
uv run python -m scraper.cli serve    # dashboard at http://127.0.0.1:8000
```

On Windows, double-clicking `run.bat` does both steps and opens the browser.

The dashboard works in two modes from the same HTML file: **live**, when
served locally by `scraper.cli serve` (adds a working *Refresh Prices*
button), and **static**, when served as plain files from GitHub Pages
(read-only, but fully functional).

## How the deal score works

Every listing is scored on five independent signals, each 0–100 where
higher is better:

| Signal | What it measures |
|---|---|
| `vs_apple` | How far below the estimated Apple US landed price it sits |
| `vs_history` | How far below the product's own 90-day median price it sits |
| `vs_peers` | Percentile rank against identically-configured listings on the site |
| `spec_value` | PKR per GB of RAM+SSD, ranked against similar models |
| `site_discount` | The site's own advertised discount (list vs. sale price) |

A signal that can't be computed — no Apple MSRP on file, no price history
yet, no peer to compare against — is `None`, never guessed. The composite
`deal_score` is the weighted mean of whichever signals *are* available,
renormalized over just those, with a `confidence` count (0–5) recorded
alongside it. A deal score of 80 built from one signal is much weaker
evidence than the same 80 built from four — check `confidence` before
trusting a score.

## The Apple benchmark is an estimate, not a fact

`Est. Apple Landed` = US Apple MSRP × the current USD→PKR rate × a
configurable duty assumption. **It is an estimate**, not an official or
actual landed cost — real import cost depends on duty category, PTA
registration tax, and import route, none of which this tool has visibility
into. Treat it as a rough yardstick, not ground truth.

`data/apple_msrp.json` currently holds 88 hand-verified Apple prices, and
39 tracked configurations still have no entry. A blank `Est. Apple Landed`
means *no verified Apple price exists yet for that exact configuration* —
it is not a signal that the listing is a bargain. Run

```
uv run python -m scraper.cli msrp-gaps
```

to list which configs are missing so they can be added.

## Data model

Canonical storage is append-only CSV, committed to git:

- `data/history.csv` — one row per product per run: price, old price, timestamp
- `data/products.csv` — identity and specs, updated in place
- `data/apple_msrp.json` — the curated Apple MSRP reference (hand-maintained)

The SQLite database and Excel workbook under `web/downloads/` are
**regenerated from the CSVs on every run** — they are derived artifacts,
not the source of truth. CSV was chosen deliberately over a committed
binary database: it diffs cleanly (a price change is one visible line),
stays human-readable indefinitely, keeps the repository small, and every
run becomes a normal, reviewable git commit — so `git log` is the backup.

## Architecture

Only `fetch.py` touches the network. Everything else is tested offline
against saved HTML fixtures in `tests/fixtures/`.

| Module | Responsibility |
|---|---|
| `fetch.py` | Rate-limited HTTP GET with retry; the only network I/O |
| `parse.py` | Raw HTML → product records (prices, specs, identity) |
| `normalize.py` | Interprets spec strings (`"1TB"` → 1024 GB) into typed fields |
| `store.py` | CSV persistence, history queries, in-memory SQLite build |
| `benchmark.py` | Apple MSRP + live FX rate → estimated landed PKR |
| `score.py` | The five deal-score signals and their weighted composite |
| `excel.py` | Builds the ranked, formatted Excel workbook |
| `report.py` | Writes the JSON the dashboard reads (`latest.json`, `history.json`) |
| `server.py` | Local dashboard server: static files + a small refresh API |
| `cli.py` | Orchestrates a run; the transactional boundary described below |

## Safety properties

- A failed run **writes nothing** and exits non-zero — `data/history.csv`
  is only touched after every category has parsed successfully.
- A run **aborts** if a previously non-empty category returns zero
  products, or if any category's product count drops more than 20% —
  both usually mean the site's markup changed, not that stock vanished.
- The tool **never invents an Apple price**: missing MSRP data means
  `vs_apple` is `None`, surfaced as a visible gap, never a guess.
- A product with no usable signals is never silently ranked as if it were
  average — its `confidence` is 0 and that is visible.

## Politeness

Roughly 17 requests per run, spaced 1.5 seconds apart, with a descriptive
User-Agent identifying the tool. No `robots.txt`-disallowed path is ever
fetched. If you extend this tool, please keep it that way — the goal is to
be lighter on the site than a person browsing the catalogue.

## Testing

```
uv run python -m pytest              # offline suite (default)
uv run python -m pytest -m live      # one opt-in test that hits the real site
uv run python -m pytest -m smoke     # browser test against a local dashboard
```

The default run touches neither the network nor a browser. `-m live` fetches
a single real category page to detect upstream markup changes. `-m smoke`
renders the dashboard in a real browser against locally-built fixture data
to check the things a human would notice by looking — row ordering, that
deal cards never show a zero price, and that a hostile product name can't
inject HTML into the page.

## Configuration

Everything tunable lives in `scraper/config.py`: which categories are
tracked, the deal-score weights, `DUTY_PERCENT` (dial this in against
observed reality), and `SPEC_RAM_WEIGHT` (Apple's relative pricing of RAM
vs. storage upgrades, used to compare configs on a per-GB basis).

## License

MIT — see [`LICENSE`](LICENSE).

This is an independent project, not affiliated with or endorsed by Apple
Inc. or applemac.pk.
