"""Pure-logic tests (no Discord/DB needed). Run: pytest -q"""
from datetime import datetime, timezone

import pytest

from bot.core.actions import channel_slug, parse_start
from bot.services.custom import _overlaps
from bot.services.draft import snake_order
from bot.services.veto import MIN_POOL, veto_plan


def _t(h):
    return datetime(2026, 6, 24, h, 0, tzinfo=timezone.utc)


def test_overlap_true():
    # BO3 at 20:00 (3h -> 23:00) overlaps a BO1 at 22:00 (1h -> 23:00)
    assert _overlaps(_t(20), 3, _t(22), 1) is True


def test_overlap_false_adjacent():
    # 20:00+1h ends exactly at 21:00; next starts 21:00 -> no overlap
    assert _overlaps(_t(20), 1, _t(21), 3) is False


def test_snake_order():
    assert snake_order(8) == ["A", "B", "B", "A", "A", "B", "B", "A"]


def test_veto_bo1_alternates_to_one():
    plan = veto_plan("BO1", 7)
    bans = [s for s in plan if s.action == "ban"]
    assert len(bans) == 6
    assert plan[-1].action == "decider"


def test_veto_bo3_shape():
    plan = veto_plan("BO3", 7)
    actions = [s.action for s in plan]
    assert actions[:4] == ["ban", "ban", "pick", "pick"]
    assert actions[-1] == "decider"


def _run_veto(fmt: str, pool_size: int) -> list[str]:
    """Mirror VetoController.apply(): consume the pool step by step, including
    its auto-resolve of a trailing decider. Returns the maps that get played."""
    plan = veto_plan(fmt, pool_size)
    remaining = [f"m{i}" for i in range(pool_size)]
    picked: list[str] = []
    step = 0
    while step < len(plan):
        assert remaining, f"{fmt}/{pool_size}: pool exhausted at step {step}"
        if plan[step].action == "decider":
            assert len(remaining) == 1, (
                f"{fmt}/{pool_size}: stalled on the decider with "
                f"{len(remaining)} maps left and no captain on the clock"
            )
            picked.append(remaining.pop())
            step += 1
            continue
        chosen = remaining.pop(0)
        if plan[step].action == "pick":
            picked.append(chosen)
        step += 1
        if step < len(plan) and plan[step].action == "decider" and len(remaining) == 1:
            picked.append(remaining.pop())
            step += 1
    assert not remaining
    return picked


@pytest.mark.parametrize("fmt,maps_played", [("BO1", 1), ("BO3", 3), ("BO5", 5)])
@pytest.mark.parametrize("pool_size", range(2, 13))
def test_veto_consumes_any_pool_size(fmt, maps_played, pool_size):
    """Regression: BO5 used to be hard-coded to exactly 7 maps, so the seeded
    10-map pool stalled forever on a decider nobody could click."""
    if pool_size < MIN_POOL[fmt]:
        with pytest.raises(ValueError):
            veto_plan(fmt, pool_size)
        return
    assert len(_run_veto(fmt, pool_size)) == maps_played


# ------------------------------------------------------------ channel names ---
@pytest.mark.parametrize(
    "creator,name,expected",
    [
        ("Salta", "Friday 5v5", "salta-friday-5v5"),
        ("xX_Sniper_Xx", "Ranked Grind!!", "xx_sniper_xx-ranked-grind"),
        ("Салта", "Пятничка 5в5", "салта-пятничка-5в5"),
        ("  spaced  ", " -- name -- ", "spaced-name"),
        ("...", "???", "custom"),          # nothing usable -> fallback
        ("🎮", "🔥", "custom"),
    ],
)
def test_channel_slug(creator, name, expected):
    assert channel_slug(creator, name) == expected


def test_channel_slug_always_valid():
    """Discord rejects empty names and trims oddly; stay inside the rules."""
    slug = channel_slug("A" * 60, "B" * 60)
    assert 0 < len(slug) <= 90
    assert not slug.startswith("-") and not slug.endswith("-")
    assert "--" not in slug


# -------------------------------------------------------------- start times ---
def test_parse_start_hhmm_is_always_in_the_future():
    """A bare HH:MM that already passed today means tomorrow, never the past."""
    for hh in range(0, 24, 3):
        got = parse_start(f"{hh:02d}:00")
        assert got > datetime.now(timezone.utc)


def test_parse_start_iso_is_absolute():
    """A naive ISO time is read in server-local time, then stored as UTC."""
    from datetime import timedelta

    from bot.config import settings

    local = timezone(timedelta(hours=settings.tz_offset))
    got = parse_start("2030-06-24T20:00")
    assert got == datetime(2030, 6, 24, 20, 0, tzinfo=local).astimezone(timezone.utc)


def test_parse_start_rejects_garbage():
    from bot.core.errors import BotError

    with pytest.raises(BotError):
        parse_start("not a time")
