"""Optional rank balancing (§10). Only meaningful when rank/RR present."""
from __future__ import annotations

import itertools

TIER = {
    "radiant": 10, "immortal": 9, "ascendant": 8, "diamond": 7, "platinum": 6,
    "gold": 5, "silver": 4, "bronze": 3, "iron": 2,
}


def _tier(rank: str | None) -> int:
    if not rank:
        return 0
    return TIER.get(rank.split()[0].lower(), 0)


def score(cur_rank: str | None, rr: int | None, peak_rank: str | None) -> float:
    return _tier(cur_rank) + (rr or 0) / 100 + 0.3 * _tier(peak_rank)


def balance(players: list[tuple[int, float]]) -> tuple[list[int], list[int]]:
    """players = [(user_id, score)]. Returns two equal halves minimizing |Σdiff|."""
    n = len(players)
    half = n // 2
    ids = [p[0] for p in players]
    scores = {p[0]: p[1] for p in players}
    best, best_diff = None, float("inf")
    for combo in itertools.combinations(ids, half):
        a = set(combo)
        sa = sum(scores[i] for i in a)
        sb = sum(scores[i] for i in ids if i not in a)
        d = abs(sa - sb)
        if d < best_diff:
            best, best_diff = a, d
    team_a = [i for i in ids if i in best]
    team_b = [i for i in ids if i not in best]
    return team_a, team_b
