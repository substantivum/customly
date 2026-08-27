"""Full Valorant rank ordinal (Iron 1 .. Radiant), shared by draft.py
(captain selection) and balance.py (rank balancing) — replaces two
duplicated base-tier-only dicts that couldn't tell Immortal 1 from
Immortal 3. Also the tie-aware random-pick helper both use.
"""
from __future__ import annotations

import random

_BASE_TIERS = (
    "iron", "bronze", "silver", "gold", "platinum",
    "diamond", "ascendant", "immortal",
)


def _build_rank_order() -> dict[str, int]:
    order: dict[str, int] = {}
    ordinal = 1
    for base in _BASE_TIERS:
        for sub in (1, 2, 3):
            order[f"{base} {sub}"] = ordinal
            ordinal += 1
    order["radiant"] = ordinal  # no sub-tier
    return order


RANK_ORDER: dict[str, int] = _build_rank_order()


def rank_value(rank: str | None) -> int:
    """Full ordinal for e.g. 'Immortal 2', or 0 if unknown/unset."""
    if not rank:
        return 0
    return RANK_ORDER.get(rank.strip().lower(), 0)


def shuffled_by_key(items: list, key) -> list:
    """Stable sort by `key` (desc), ties broken randomly.

    Shuffle first, then a *stable* sort: within any group of equal keys the
    shuffle's order survives, so ties come out randomized while the overall
    ranking stays correct.
    """
    pool = list(items)
    random.shuffle(pool)
    return sorted(pool, key=key, reverse=True)
