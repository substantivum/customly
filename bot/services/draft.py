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


# Methods that can be fixed when a custom is created. `manual` is missing on
# purpose: it names two specific players, and at creation nobody has signed up
# yet — it stays an override on `/match start`.
CREATE_METHODS = ("random", "highest_rr", "highest_peak")

CAPTAIN_METHOD_LABEL = {
    "random": "🎲 Random",
    "highest_rr": "📈 Highest RR",
    "highest_peak": "🏔 Highest peak rank",
    "manual": "✍️ Manually chosen",
    "volunteer": "🙋 Volunteers",
    "vote": "🗳 Voted",
}

CAPTAIN_METHOD_HELP = {
    "random": "two random players from the lobby",
    "highest_rr": "the two highest current RR — needs profiles filled in",
    "highest_peak": "the two highest peak ranks — needs profiles filled in",
}


def _other(side: str) -> str:
    return "B" if side == "A" else "A"


def snake_order(picks_needed: int, first: str = "A") -> list[str]:
    """Snake draft sides for the remaining (non-captain) players: A, BB, AA, BB …

    `first` is the side that won the right to pick first in the coin toss.
    """
    seq = [first]
    side, run = _other(first), 2
    while len(seq) < picks_needed:
        seq.extend([side] * run)
        side = _other(side)
    return seq[:picks_needed]


def alternate_order(picks_needed: int, first: str = "A") -> list[str]:
    """Straight one-by-one draft: A, B, A, B … — no double picks.

    The first pick is worth more here than in a snake, which is exactly why some
    organisers prefer it: the coin toss decides something real.
    """
    return [first if i % 2 == 0 else _other(first) for i in range(picks_needed)]


DRAFT_MODES = ("snake", "alternate")
DRAFT_MODE_LABEL = {
    "snake": "🐍 Snake (A, BB, AA, …)",
    "alternate": "🔁 One by one (A, B, A, B, …)",
}


def pick_order(mode: str, picks_needed: int, first: str = "A") -> list[str]:
    """Draft turn order for `mode` (`snake` | `alternate`)."""
    if mode not in DRAFT_MODES:
        raise BotError(f"Draft mode must be one of: {', '.join(DRAFT_MODES)}.")
    fn = alternate_order if mode == "alternate" else snake_order
    return fn(picks_needed, first)
