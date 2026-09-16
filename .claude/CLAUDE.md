# Working in this repository

Instructions for any AI agent making changes here. Read this before touching code.

This project tracks prices on applemac.pk and tells its owner which listing is the
best buy. Someone spends real money on the numbers it prints. That single fact
drives every rule below.

## The one rule everything else serves

**Never present absent or uncertain data as a finding.**

A wrong number here does not look wrong. It looks like a price. The failure mode
is not a crash — it is a plausible figure that sends the owner to the wrong
purchase. Every guard in this codebase exists because that already happened
during development:

- A signal with no data returns `None`, never `0`, never a guess.
- The composite deal score is renormalised over *available* signals only, so
  missing data lowers `confidence` rather than silently depressing the score.
- Products with zero available signals are excluded from "Top deals" entirely.
- `data/apple_msrp.json` holds only hand-verified prices. **Never add a price you
  have not directly observed on apple.com.** Not an estimate, not an
  interpolation from a nearby config, not one recalled from memory. A missing
  entry is correct behaviour; a guessed one is the worst possible outcome.
- The Apple benchmark is labelled `Est. Apple Landed` everywhere. Never call it an
  official or actual price.

## Architecture

A one-way pipeline. Only `fetch` touches the network, which is why everything
else is tested offline against committed HTML fixtures.

```
fetch → parse → normalize → store → benchmark → score → excel / report → server
```

| Module | Responsibility |
|---|---|
| `config.py` | Categories, weights, tunables, paths. Pure data — no logic. |
| `fetch.py` | Rate-limited HTTP with retry. The **only** network module. |
| `parse.py` | HTML → `RawProduct`. Extracts strings verbatim, interprets nothing. |
| `normalize.py` | `RawProduct` → `Product`. **All** string-to-value logic lives here. |
| `store.py` | Append-only CSV load/save, history queries, derived SQLite. |
| `benchmark.py` | Apple MSRP + live FX → estimated landed PKR. |
| `score.py` | Five signals → one explainable composite. |
| `excel.py` | The multi-sheet workbook. |
| `report.py` | `latest.json` / `history.json` for the dashboard. |
| `server.py` | Local dashboard server. Binds `127.0.0.1` only. |
| `cli.py` | Orchestration, abort rules, entry point. |

Keep the boundaries. Interpretation belongs in `normalize`, not `parse`.
Network belongs in `fetch`, nowhere else.

## Invariants you must not break

**A failed run writes nothing.** Every category is fetched, parsed and
sanity-checked before `record_run`/`save`. If anything aborts, `data/history.csv`
is byte-identical to its prior state and the process exits non-zero.
`test_failed_run_writes_nothing` and its partial-success sibling are the most
important tests in the suite.

**`data/history.csv` is append-only.** Existing rows are never edited or deleted.
SQLite and Excel are regenerated artifacts — delete them freely; never rewrite
history.

**`store.save` runs BEFORE output generation, deliberately.** If Excel generation
fails, the scrape is still preserved. Do not reorder this. A post-save failure
raises `RunOutputsFailed` so the user is told the history *was* written — never
print a blanket "nothing was written" claim.

**`save()` writes products.csv before history.csv, deliberately.** `category_counts`
indexes `self.products[slug]` unguarded. Do not reorder.

**`pytest` lives in `[dependency-groups]`, not `[project.optional-dependencies]`.**
`uv sync` skips extras by default, so moving it would leave CI with no pytest and
silently kill the daily job. The comment in `pyproject.toml` says so; heed it.

## Site-specific traps

These are real, verified against the live site, and easy to reintroduce:

- `•` (U+2022) is the site's null placeholder in `data-*` attributes → `None`.
- `‑` (U+2011, non-breaking hyphen) appears in iPhone attributes. Normalise to
  ASCII `-` before parsing or the core/screen regexes fail.
- **Capacity lives in different attributes per product type**: MacBooks use
  `data-ssd`; iPhones use `data-storage`. Try `data-ssd`, fall back.
- `data-price="0"` means unannounced or made-to-order, **not free**. Non-positive
  prices are rejected as unusable.
- Screen size is `"14 Inches"` on MacBooks but `"6.9‑inch"` on iPhones.
- Old price often equals new price. That is "no discount data", not a 0% discount.
- Each card contains its product URL twice (image anchor + title anchor).
  Intra-card duplication is collapsed by `find()`; cross-card dedup is separate
  and tested.
- iPhone category pages go empty when stock lapses. An empty category is a
  legitimate state; an empty category that had products last run is an abort.

## Politeness — non-negotiable

This scrapes a real small business. ~17 requests per run, 1.5s apart, descriptive
User-Agent. Never fetch a robots.txt-disallowed path (`/index.php/`, `/?page=`,
`/cart/`, `/public/`). Never loop a live scrape while debugging — use the
committed fixtures. There is exactly one `@pytest.mark.live` test and it is
deselected by default; keep it that way.

## Testing philosophy

**Fewer, higher-value tests.** The suite is ~50 and should stay near there. It was
trimmed from 127 deliberately: an open-source repo should not drown a reader in
tests that restate constants.

Write a test when it pins behaviour that could silently regress — especially
anything invisible in a browser: scoring maths, key construction, the
write-nothing guarantee, type fidelity through CSV. Do **not** write a test that
asserts a constant equals itself, or that a function returns the right type when
another test already asserts its exact value.

The bar: **would this test fail against a plausibly broken implementation?** If
not, delete it. When you fix a bug, add the test that would have caught it, and
verify it actually fails against the old behaviour before you keep it.

`-m smoke` runs a browser check of the rendered dashboard; `-m live` hits the real
site. Both are deselected by default. A browser confirms the page renders — it
cannot see a wrong number that looks right, which is why the unit tests exist.

## Conventions

- Python 3.13, managed with `uv`. Runtime deps are exactly `requests`,
  `beautifulsoup4`, `openpyxl`. Adding a fourth needs a real justification.
- All money is integer PKR. No floats for currency.
- Run things as `uv run python -m pytest` / `uv run python -m scraper.cli run`.
  `uv run pytest` can fall back to a pytest on PATH and hide a broken environment.
- **Never add `Co-Authored-By` or any Claude/Anthropic attribution trailer to
  commits or PR descriptions.** The owner has scrubbed these before.
- Do not push, create remotes, or enable Pages without being asked. Publishing is
  the owner's decision.

## Verifying your work

Report what you observed, not what you intended. Running a command and reading
its exit status is not the same as verifying the thing it was supposed to prove —
a green test run once hid a completely broken CI environment here because pytest
was resolving from PATH rather than the project venv.

Check the artefact: read the file's bytes, print the resolved path, inspect the
generated workbook. If you claim something is in a particular form, look at it.
