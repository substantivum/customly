"""Map veto sequence generation for BO1 / BO3 / BO5.

Follows the published Riot map selection process. Team A acts first throughout;
the side on a picked map belongs to the team that did *not* pick it, and the
side on the decider goes to whoever did not act last.

BO3 and BO5 are the official sequences verbatim, which are written for the
7-map competitive pool — anything else would need invented steps, so it is
refused. BO1 is generated and runs on any pool of two or more; at seven maps it
reproduces the official BO1 sequence.
"""
from __future__ import annotations

from dataclasses import dataclass

from bot.core.errors import BotError
from bot.i18n import t


@dataclass
class VetoStep:
    action: str       # "ban" | "pick" | "decider" | "side"
    side: str | None  # "A" | "B" | None for the auto decider


FORMATS = ("BO1", "BO3", "BO5")
POOL_EXACT = {"BO3": 7, "BO5": 7}
POOL_MIN = {"BO1": 2}
# A VetoView renders one ban/pick button per remaining map; Discord caps a
# View at 25 components, so this must be enforced here, not mid-veto.
POOL_MAX = {"BO1": 25}

_SEQUENCES: dict[str, tuple[tuple[str, str | None], ...]] = {
    "BO3": (
        ("ban", "A"), ("ban", "B"),
        ("pick", "A"), ("side", "B"),
        ("pick", "B"), ("side", "A"),
        ("ban", "A"), ("ban", "B"),
        ("decider", None), ("side", "A"),
    ),
    "BO5": (
        ("ban", "A"), ("ban", "B"),
        ("pick", "A"), ("side", "B"),
        ("pick", "B"), ("side", "A"),
        ("pick", "A"), ("side", "B"),
        ("pick", "B"), ("side", "A"),
        ("decider", None), ("side", "B"),
    ),
}


def pool_requirement(fmt: str) -> str:
    """How big a pool the format wants, phrased for a captain to read."""
    if fmt in POOL_EXACT:
        return t("veto.pool.exact", n=POOL_EXACT[fmt])
    return t("veto.pool.min", n=POOL_MIN[fmt])


def check_pool(fmt: str, pool_size: int) -> None:
    """Raise unless a pool of `pool_size` can run a `fmt` veto."""
    if fmt not in FORMATS:
        raise BotError(t("error.veto_format", formats=", ".join(FORMATS)))
    ok = (
        pool_size == POOL_EXACT[fmt] if fmt in POOL_EXACT
        else pool_size >= POOL_MIN[fmt]
    )
    if not ok:
        msg = t("error.veto_pool", fmt=fmt, requirement=pool_requirement(fmt),
                n=pool_size)
        if fmt in POOL_EXACT:
            msg += t("error.veto_pool_hint")
        raise BotError(msg)
    if fmt in POOL_MAX and pool_size > POOL_MAX[fmt]:
        raise BotError(t("error.veto_pool_max", fmt=fmt, max=POOL_MAX[fmt], n=pool_size))


def veto_plan(fmt: str, pool_size: int) -> list[VetoStep]:
    """The ordered ban/pick/side plan. The last map standing is the decider."""
    check_pool(fmt, pool_size)
    if fmt in _SEQUENCES:
        return [VetoStep(action, side) for action, side in _SEQUENCES[fmt]]
    return _bo1_plan(pool_size)


def _bo1_plan(pool_size: int) -> list[VetoStep]:
    """Alternate bans from Team A down to one map, whose side then goes to the
    team that didn't ban last."""
    bans = [
        VetoStep("ban", "A" if i % 2 == 0 else "B") for i in range(pool_size - 1)
    ]
    return [
        *bans,
        VetoStep("decider", None),
        VetoStep("side", _other(bans[-1].side)),
    ]


def _other(side: str) -> str:
    return "B" if side == "A" else "A"
