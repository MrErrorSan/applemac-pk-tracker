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
    """Map value -> 0-100 where the lowest value scores 100.

    Non-positive values are never real signal (a zero price, a zero spec
    ratio) and must not be allowed to set `lowest` — that would flatten
    every genuine value in the group toward 0. Defensive: normalize()
    already keeps zero prices out, but this guard holds even if one slips
    through another path.
    """
    usable = [v for v in values if v is not None and v > 0]
    if len(usable) < 2:
        return None
    lowest, highest = min(usable), max(usable)
    if highest == lowest:
        return None
    return lambda v: (highest - v) / (highest - lowest) * 100


def score_all(products, db, benchmarks, weights=None, now=None, exclude_run_id=None):
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

        median = db.median_price(product.slug, config.HISTORY_WINDOW_DAYS,
                                 now=now, exclude_run_id=exclude_run_id)
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
    """PKR per weighted GB (RAM weighted 64x vs storage). Lower is better value."""
    ram_gb = product.ram_gb or 0
    storage_gb = product.storage_gb or 0
    weighted_capacity = ram_gb * config.SPEC_RAM_WEIGHT + storage_gb
    if weighted_capacity <= 0:
        return None
    return product.price / weighted_capacity
