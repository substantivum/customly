"""Captain selection + snake-draft ordering."""
from __future__ import annotations

import random

from bot.core.errors import BotError
from bot.i18n import t
from bot.services import ranks

CaptainMethod = str  # random|manual|highest_rr|highest_peak|highest_wins_peak|highest_wins_rr|volunteer|vote

# Methods that actually consume rank data, and so need refreshed ranks
# before picking (see bot.core.actions._players_meta).
RANK_METHODS = ("highest_rr", "highest_peak", "highest_wins_peak", "highest_wins_rr")


def _peak_val(p: dict) -> int:
    return ranks.rank_value(p.get("peak_rank"))


def _wins_val(p: dict) -> int:
    return p.get("wins") or 0


def has_enough_rank_data(method: CaptainMethod, players: list[dict]) -> bool:
    """Whether `method` has real data to act on. `highest_peak`/`highest_rr`
    are meaningless with fewer than 2 players carrying that data — otherwise
    it's just a random pick among a pile of zeros, indistinguishable from
    `random` but without telling anyone that's what happened. The
    `highest_wins_*` methods don't need this: `wins` always exists (0 for a
    fresh player), so an all-zero field just degrades to a random pick among
    ties, which is expected behavior for a wins-based ranking, not broken
    data. Every other method doesn't consume rank data at all."""
    if method == "highest_peak":
        return sum(1 for p in players if p.get("peak_rank")) >= 2
    if method == "highest_rr":
        return sum(1 for p in players if p.get("cur_rr") is not None) >= 2
    return True


def series_winner(map_winners: list[str]) -> str | None:
    """Which side ('A'/'B') won a BO1/BO3/BO5 series from its recorded
    per-map winners, or None if it can't be determined — no maps reported
    yet, or the custom was force-ended before either side had a majority."""
    a, b = map_winners.count("A"), map_winners.count("B")
    if a == b:
        return None
    return "A" if a > b else "B"


def choose_captains(
    method: CaptainMethod,
    players: list[dict],            # [{user_id, cur_rr, peak_rank}]
    manual: tuple[int, int] | None = None,
    volunteers: list[int] | None = None,
    votes: dict[int, int] | None = None,
) -> tuple[int, int]:
    if method == "manual":
        if not manual:
            raise BotError(t("error.manual_two"))
        return manual
    if method == "random":
        ids = [p["user_id"] for p in players]
        if len(ids) < 2:
            raise BotError(t("error.need_two_players"))
        a, b = random.sample(ids, 2)
        return a, b
    if method == "highest_rr":
        ranked = ranks.shuffled_by_key(players, key=lambda p: p.get("cur_rr") or -1)
        return ranked[0]["user_id"], ranked[1]["user_id"]
    if method == "highest_peak":
        ranked = ranks.shuffled_by_key(players, key=_peak_val)
        return ranked[0]["user_id"], ranked[1]["user_id"]
    if method == "highest_wins_peak":
        ranked = ranks.shuffled_by_key(players, key=lambda p: (_wins_val(p), _peak_val(p)))
        return ranked[0]["user_id"], ranked[1]["user_id"]
    if method == "highest_wins_rr":
        ranked = ranks.shuffled_by_key(
            players, key=lambda p: (_wins_val(p), p.get("cur_rr") or -1)
        )
        return ranked[0]["user_id"], ranked[1]["user_id"]
    if method == "volunteer":
        vs = volunteers or []
        if len(vs) < 2:
            raise BotError(t("error.volunteers"))
        return vs[0], vs[1]
    if method == "vote":
        if not votes:
            raise BotError(t("error.no_votes"))
        if len(votes) < 2:
            raise BotError(t("error.need_two_candidates"))
        top = sorted(votes.items(), key=lambda kv: kv[1], reverse=True)
        return top[0][0], top[1][0]
    raise BotError(t("error.unknown_captain", method=method))


# Methods that can be fixed when a custom is created. `manual` is missing on
# purpose: it names two specific players, and at creation nobody has signed up
# yet — it stays an override on `/match start`.
CREATE_METHODS = (
    "random", "highest_rr", "highest_peak", "highest_wins_peak", "highest_wins_rr",
)

# Catalog keys rather than finished text: a label is only correct once the
# reader's language is known, which is at render time, not at import time.
CAPTAIN_METHOD_KEY = {
    "random": "captain.random",
    "highest_rr": "captain.highest_rr",
    "highest_peak": "captain.highest_peak",
    "highest_wins_peak": "captain.highest_wins_peak",
    "highest_wins_rr": "captain.highest_wins_rr",
    "manual": "captain.manual",
    "volunteer": "captain.volunteer",
    "vote": "captain.vote",
}

CAPTAIN_HELP_KEY = {
    "random": "captain.help.random",
    "highest_rr": "captain.help.highest_rr",
    "highest_peak": "captain.help.highest_peak",
    "highest_wins_peak": "captain.help.highest_wins_peak",
    "highest_wins_rr": "captain.help.highest_wins_rr",
}


def captain_label(method: str) -> str:
    """How a captain method reads to a player, in the current language."""
    key = CAPTAIN_METHOD_KEY.get(method)
    return t(key) if key else method


def captain_help(method: str) -> str:
    key = CAPTAIN_HELP_KEY.get(method)
    return t(key) if key else ""


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
DRAFT_MODE_KEY = {
    "snake": "draft.mode.snake",
    "alternate": "draft.mode.alternate",
}


def draft_mode_label(mode: str) -> str:
    key = DRAFT_MODE_KEY.get(mode)
    return t(key) if key else mode


def pick_order(mode: str, picks_needed: int, first: str = "A") -> list[str]:
    """Draft turn order for `mode` (`snake` | `alternate`)."""
    if mode not in DRAFT_MODES:
        raise BotError(t("error.draft_mode", modes=", ".join(DRAFT_MODES)))
    fn = alternate_order if mode == "alternate" else snake_order
    return fn(picks_needed, first)
