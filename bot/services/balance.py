"""Optional rank balancing (§10). Only meaningful when rank/RR present."""
from __future__ import annotations

import itertools

from bot.services.ranks import rank_value as _tier


def score(cur_rank: str | None, rr: int | None, peak_rank: str | None) -> float:
    return _tier(cur_rank) + (rr or 0) / 100 + 0.3 * _tier(peak_rank)


# Brute-forced over every combination of half the players — only safe because
# callers cap team size at 5 (bot.services.custom.MAX_TEAM), so `players` is at
# most 10 long. Guard against silently going exponential if that assumption
# ever changes elsewhere.
MAX_PLAYERS = 16


def balance(players: list[tuple[int, float]]) -> tuple[list[int], list[int]]:
    """players = [(user_id, score)]. Returns two equal halves minimizing |Σdiff|."""
    n = len(players)
    if n > MAX_PLAYERS:
        raise ValueError(
            f"balance() is brute-force over C(n, n/2) combinations; "
            f"{n} players exceeds the {MAX_PLAYERS}-player cap"
        )
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
