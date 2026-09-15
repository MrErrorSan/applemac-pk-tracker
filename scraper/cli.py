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
    """A sanity check failed before anything was written. Nothing was written."""


class RunOutputsFailed(Exception):
    """The price history was already saved; a later output step then failed."""

    def __init__(self, step, original):
        self.step = step
        self.original = original
        super().__init__(
            f"{step} failed after the price history was saved: {original}"
        )


def _now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="microseconds")


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
        excluded = 0
        for raw in raw_products:
            if raw.slug in by_slug:      # leaf categories overlap the catch-all
                continue
            slug_lower = raw.slug.lower()
            if any(pattern in slug_lower for pattern in config.EXCLUDE_SLUG_PATTERNS):
                excluded += 1
                continue
            product = normalize(raw, family)
            if product is None:
                dropped += 1
                continue
            by_slug[raw.slug] = product
        if dropped:
            notes.append(f"{category_slug}: {dropped} rows had no usable price")
        if excluded:
            notes.append(f"{category_slug}: {excluded} rows excluded by slug pattern")

    return list(by_slug.values()), notes


ACCESSORY_SLUG_WORDS = (
    "case", "cover", "charger", "cable", "adapter", "protector", "glass",
    "holder", "stand", "magsafe", "strap", "skin", "film", "pouch", "lens",
    "band",
)


def coverage_gaps(sitemap_xml, collected_slugs, pattern=r"iphone-(?:\d|air)"):
    """Sitemap product slugs matching `pattern` that no category yielded.

    `pattern` is a regex (case-insensitive), matched with `re.search` — the
    default requires an `iphone-<digit>` or `iphone-air` shape so it catches
    handset slugs (e.g. "apple-iphone-17-pro-max-2tb") without also matching
    every accessory that merely contains the word "iphone" (e.g.
    "apple-18w-usb-c-iphone-charger"). The handset shape alone still admits
    accessories sold under a numbered iPhone line (e.g. "iphone-16-case-clear"),
    so slugs containing an accessory word are excluded after the pattern match.

    Reports only. A gap means a category is missing from config, not that the
    run is wrong, so this never aborts.
    """
    found = re.findall(r"<loc>[^<]*?/product/([^<]+)</loc>", sitemap_xml)
    gaps = set()
    for slug in found:
        slug = slug.rstrip("/")
        if not re.search(pattern, slug, re.IGNORECASE):
            continue
        if any(word in slug.lower() for word in ACCESSORY_SLUG_WORDS):
            continue
        if slug in collected_slugs:
            continue
        gaps.add(slug)
    return sorted(gaps)


def run(fetcher=None, data_dir=None, web_dir=None, force=False):
    started_at = _now()
    run_id = started_at.replace(":", "").replace("-", "").replace(".", "")

    data_dir = data_dir or config.DATA_DIR
    web_dir = web_dir or config.WEB_DIR
    fetcher = fetcher or Fetcher(cache_dir=config.BUILD_DIR / "cache" / run_id)

    db = store.load(data_dir)

    # Sub-second precision makes a collision unlikely, not impossible (clock
    # resolution varies by platform) — so guard explicitly against reusing an
    # id already present in the loaded history.
    existing_run_ids = {r.run_id for r in db.runs}
    if run_id in existing_run_ids:
        suffix = 1
        while f"{run_id}-{suffix}" in existing_run_ids:
            suffix += 1
        run_id = f"{run_id}-{suffix}"

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

    # From here on, data/history.csv already holds this run. A failure below
    # must be reported as such — never as "nothing was written" — because the
    # canonical record is safe even if these derived outputs are not.
    try:
        # Exclude this run's own just-saved snapshots from vs_history's
        # median — otherwise a first-ever run compares today's price
        # against itself and fabricates vs_history == 0.0 for everything.
        scores = score.score_all(products, db, benchmarks, exclude_run_id=run_id)
    except Exception as error:  # noqa: BLE001 - reclassified as post-save below
        raise RunOutputsFailed("score.score_all", error) from error

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

    try:
        excel.build_workbook(products, scores, db, meta,
                             web_dir / "downloads" / "applemac-prices.xlsx")
    except Exception as error:  # noqa: BLE001 - reclassified as post-save below
        raise RunOutputsFailed("excel.build_workbook", error) from error

    try:
        store.build_sqlite(db, web_dir / "downloads" / "prices.db")
    except Exception as error:  # noqa: BLE001 - reclassified as post-save below
        raise RunOutputsFailed("store.build_sqlite", error) from error

    try:
        report.write_latest(products, scores, db, meta, web_dir / "data" / "latest.json")
    except Exception as error:  # noqa: BLE001 - reclassified as post-save below
        raise RunOutputsFailed("report.write_latest", error) from error

    try:
        report.write_history(db, web_dir / "data" / "history.json")
    except Exception as error:  # noqa: BLE001 - reclassified as post-save below
        raise RunOutputsFailed("report.write_history", error) from error

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
        except RunOutputsFailed as error:
            print(f"RUN PARTIALLY FAILED: {error.step} failed: {error.original}",
                 file=sys.stderr)
            print("The price history WAS updated and saved: data/history.csv is "
                 "intact and correct.", file=sys.stderr)
            print("web/ outputs may be stale or missing; re-running will "
                 "regenerate them.", file=sys.stderr)
            return 1
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
