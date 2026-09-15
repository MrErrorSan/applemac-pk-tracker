"""JSON the dashboard reads. Same data in static and live mode."""
import json
from dataclasses import asdict


def write_latest(products, scores, db, meta, path):
    previous = {}
    if db.previous_run():
        previous = {s.slug: s.price
                    for s in db.snapshots_for_run(db.previous_run().run_id).values()}

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
