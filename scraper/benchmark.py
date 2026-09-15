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
