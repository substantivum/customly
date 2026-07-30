"""Map veto sequence generation for BO1 / BO3 / BO5."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class VetoStep:
    action: str      # "ban" | "pick" | "decider"
    side: str | None  # "A" | "B" | None for the auto decider


# Smallest pool each format can veto down to a full map list.
# BO1: 1 decider. BO3: 2 bans + 2 picks + decider. BO5: 2 bans + 4 picks + decider.
MIN_POOL = {"BO1": 2, "BO3": 5, "BO5": 7}


def veto_plan(fmt: str, pool_size: int) -> list[VetoStep]:
    """Return the ordered ban/pick plan. The final remaining map is the decider.

    Every plan consumes the pool down to exactly one map, whatever its size:
    the opening bans/picks are fixed per format and any surplus maps are banned
    off alternately before the decider.
    """
    if fmt not in MIN_POOL:
        raise ValueError(fmt)
    if pool_size < MIN_POOL[fmt]:
        raise ValueError(
            f"{fmt} needs at least {MIN_POOL[fmt]} maps in the pool (got {pool_size})."
        )

    if fmt == "BO1":
        opening = []
    elif fmt == "BO3":
        opening = [
            VetoStep("ban", "A"), VetoStep("ban", "B"),
            VetoStep("pick", "A"), VetoStep("pick", "B"),
        ]
    else:  # BO5
        opening = [
            VetoStep("ban", "A"), VetoStep("ban", "B"),
            VetoStep("pick", "A"), VetoStep("pick", "B"),
            VetoStep("pick", "A"), VetoStep("pick", "B"),
        ]

    # Ban the surplus down to the single decider map.
    surplus = pool_size - len(opening) - 1
    start = "A" if len(opening) % 2 == 0 else "B"
    return [
        *opening,
        *[VetoStep("ban", s) for s in _alt(start, surplus)],
        VetoStep("decider", None),
    ]


def _alt(start: str, n: int) -> list[str]:
    out, side = [], start
    for _ in range(max(0, n)):
        out.append(side)
        side = "B" if side == "A" else "A"
    return out
