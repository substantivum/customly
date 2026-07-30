"""Captain selection + snake-draft ordering."""
from __future__ import annotations

import random

from bot.core.errors import BotError

CaptainMethod = str  # random|manual|highest_rr|highest_peak|volunteer|vote

_PEAK = {
    "radiant": 10, "immortal": 9, "ascendant": 8, "diamond": 7, "platinum": 6,
    "gold": 5, "silver": 4, "bronze": 3, "iron": 2,
}


def _peak_val(p: dict) -> int:
    pr = p.get("peak_rank")
    if not pr:
        return 0
    return _PEAK.get(pr.split()[0].lower(), 0)


def choose_captains(
    method: CaptainMethod,
    players: list[dict],            # [{user_id, cur_rr, peak_rank}]
    manual: tuple[int, int] | None = None,
    volunteers: list[int] | None = None,
    votes: dict[int, int] | None = None,
) -> tuple[int, int]:
    if method == "manual":
        if not manual:
            raise BotError("Manual method needs two captain picks.")
        return manual
    if method == "random":
        a, b = random.sample([p["user_id"] for p in players], 2)
        return a, b
    if method == "highest_rr":
        ranked = sorted(players, key=lambda p: p.get("cur_rr") or -1, reverse=True)
        return ranked[0]["user_id"], ranked[1]["user_id"]
    if method == "highest_peak":
        ranked = sorted(players, key=_peak_val, reverse=True)
        return ranked[0]["user_id"], ranked[1]["user_id"]
    if method == "volunteer":
        vs = volunteers or []
        if len(vs) < 2:
            raise BotError("Need at least two volunteers.")
        return vs[0], vs[1]
    if method == "vote":
        if not votes:
            raise BotError("No votes recorded.")
        top = sorted(votes.items(), key=lambda kv: kv[1], reverse=True)
        return top[0][0], top[1][0]
    raise BotError(f"Unknown captain method: {method}")


def snake_order(picks_needed: int) -> list[str]:
    """Snake draft sides for the remaining (non-captain) players: A, BB, AA, BB ..."""
    seq = ["A"]
    side, run = "B", 2
    while len(seq) < picks_needed:
        seq.extend([side] * run)
        side = "A" if side == "B" else "B"
    return seq[:picks_needed]
