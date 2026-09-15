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
