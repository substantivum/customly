"""Pure-logic tests (no Discord/DB needed). Run: pytest -q"""
from datetime import datetime, timezone

import pytest

from bot.core.actions import channel_slug, parse_start
from bot.core.naming import team_vc_name
from bot.services.custom import _overlaps
from bot.services.draft import alternate_order, pick_order, snake_order
from bot.services.veto import check_pool, veto_plan


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


def test_snake_order_follows_the_coin_toss():
    """The toss winner may take second pick — the whole order mirrors."""
    assert snake_order(8, "B") == ["B", "A", "A", "B", "B", "A", "A", "B"]


def test_alternate_order():
    assert alternate_order(6) == ["A", "B", "A", "B", "A", "B"]
    assert alternate_order(6, "B") == ["B", "A", "B", "A", "B", "A"]


@pytest.mark.parametrize("mode", ["snake", "alternate"])
@pytest.mark.parametrize("first", ["A", "B"])
@pytest.mark.parametrize("picks", [2, 4, 6, 8])
def test_every_draft_mode_splits_the_pool_evenly(mode, first, picks):
    """Teams are the same size whichever mode/first pick is in play — a queue is
    always an even number of players, so the non-captain pool is even too."""
    order = pick_order(mode, picks, first)
    assert order[0] == first
    assert order.count("A") == order.count("B") == picks // 2


def test_pick_order_rejects_unknown_mode():
    from bot.core.errors import BotError

    with pytest.raises(BotError):
        pick_order("auction", 4)


def _steps(fmt: str, pool_size: int) -> list[tuple[str, str | None]]:
    return [(s.action, s.side) for s in veto_plan(fmt, pool_size)]


def test_veto_bo1_follows_the_official_sequence():
    """Team A bans first, alternating to map 7, then Team A picks side."""
    assert _steps("BO1", 7) == [
        ("ban", "A"), ("ban", "B"),
        ("ban", "A"), ("ban", "B"),
        ("ban", "A"), ("ban", "B"),
        ("decider", None), ("side", "A"),
    ]


def test_veto_bo3_follows_the_official_sequence():
    """Each picked map's side goes to the team that did not pick it; the
    decider's goes to Team A, who did not ban last."""
    assert _steps("BO3", 7) == [
        ("ban", "A"), ("ban", "B"),
        ("pick", "A"), ("side", "B"),
        ("pick", "B"), ("side", "A"),
        ("ban", "A"), ("ban", "B"),
        ("decider", None), ("side", "A"),
    ]


def test_veto_bo5_follows_the_official_sequence():
    """No bans after the picks, so the decider's side falls to Team B — the
    team that did not choose the side on map 4."""
    assert _steps("BO5", 7) == [
        ("ban", "A"), ("ban", "B"),
        ("pick", "A"), ("side", "B"),
        ("pick", "B"), ("side", "A"),
        ("pick", "A"), ("side", "B"),
        ("pick", "B"), ("side", "A"),
        ("decider", None), ("side", "B"),
    ]


@pytest.mark.parametrize("fmt", ["BO3", "BO5"])
@pytest.mark.parametrize("pool_size", [2, 5, 6, 8, 10])
def test_bo3_and_bo5_need_exactly_the_competitive_seven(fmt, pool_size):
    """The published sequences are written for a 7-map pool; anything else
    would need invented steps."""
    with pytest.raises(ValueError):
        veto_plan(fmt, pool_size)
    with pytest.raises(ValueError):
        check_pool(fmt, pool_size)
    check_pool(fmt, 7)


@pytest.mark.parametrize("pool_size", range(2, 13))
def test_veto_bo1_bans_any_pool_down_to_one_map(pool_size):
    """BO1 isn't tied to 7: a smaller or larger pool still alternates to one."""
    plan = veto_plan("BO1", pool_size)
    assert [s.action for s in plan].count("ban") == pool_size - 1
    assert (plan[-2].action, plan[-1].action) == ("decider", "side")
    bans = [s.side for s in plan if s.action == "ban"]
    assert bans == ["A" if i % 2 == 0 else "B" for i in range(len(bans))]
    assert plan[-1].side != bans[-1]     # the last banner doesn't pick the side


def test_bo1_rejects_a_pool_too_small_to_veto():
    with pytest.raises(ValueError):
        veto_plan("BO1", 1)


# --------------------------------------------------------------- roster ------
def _split(ids: list[int], size: int) -> tuple[list[int], list[int]]:
    """The rule custom_svc.roster applies: join order, cut at the seat count."""
    return ids[:size], ids[size:]


def test_roster_caps_the_game_at_the_team_size():
    """A 3v3 has 6 seats; a 7th sign-up is a sub, not a 4th player on a side."""
    starters, waitlist = _split(list(range(1, 8)), 3 * 2)
    assert starters == [1, 2, 3, 4, 5, 6]
    assert waitlist == [7]


def test_waitlist_promotes_in_join_order():
    """Deriving the split from join order means a leaver is replaced with no
    promotion bookkeeping: whoever is next simply becomes a starter."""
    ids, size = [1, 2, 3, 4, 5, 6, 7, 8], 6
    starters, waitlist = _split(ids, size)
    assert waitlist == [7, 8]
    ids.remove(3)                       # a starter drops out
    starters, waitlist = _split(ids, size)
    assert starters == [1, 2, 4, 5, 6, 7]   # 7 moved up
    assert waitlist == [8]


def test_waitlist_leaver_does_not_promote_anyone():
    ids, size = [1, 2, 3, 4, 5, 6, 7], 6
    ids.remove(7)                       # a sub drops out
    starters, waitlist = _split(ids, size)
    assert starters == [1, 2, 3, 4, 5, 6] and waitlist == []


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


# ----------------------------------------------------------- team vc names ---
@pytest.mark.parametrize(
    "custom_name,side,nick,expected",
    [
        ("Friday 5v5", "a", "Salta", "friday-5v5-a-salta"),
        ("Friday 5v5", "B", "Nex", "friday-5v5-b-nex"),
        ("Пятничка 5в5", "b", "Салта", "пятничка-5в5-b-салта"),
        ("Friday 5v5", "b", None, "friday-5v5-b"),   # captain left the server
        ("🔥", "a", "🎮", "team-a"),                  # nothing sluggable
    ],
)
def test_team_vc_name(custom_name, side, nick, expected):
    assert team_vc_name(custom_name, side, nick) == expected


def test_team_vc_name_always_valid():
    name = team_vc_name("X" * 80, "a", "Y" * 80)
    assert 0 < len(name) <= 95
    assert not name.startswith("-") and not name.endswith("-")


# ------------------------------------------------------------- coin toss -----
def test_coinflip_winner_is_whoever_called_right():
    from bot.core.controllers import CoinflipController

    for _ in range(200):
        c = CoinflipController(1, 111, 222)
        assert c.caller_side in ("A", "B")
        assert c.actor_id() == c.caller_id
        face = c.flip("heads")
        called_right = face == "heads"
        assert (c.winner_side == c.caller_side) is called_right
        # the toss winner is the one who now chooses their letter
        assert c.actor_id() == c.captain(c.winner_side)


@pytest.mark.parametrize("choice", ["A", "B"])
def test_coinflip_winner_takes_the_letter_they_chose(choice):
    """The toss buys the choice of letter; Team A opens the draft and the veto,
    so taking B is a real trade."""
    from bot.core.controllers import CoinflipController

    c = CoinflipController(1, 111, 222)
    c.flip("tails")
    won = c.captain(c.winner_side)
    lost = c.captain(other := ("B" if c.winner_side == "A" else "A"))
    assert c.choose_letter(choice) == choice
    assert c.captain(choice) == won
    assert c.captain("B" if choice == "A" else "A") == lost
    assert c.winner_side == choice           # labels follow the choice
    assert c.done and c.first_side == "A"    # Team A always opens the draft
    assert other in ("A", "B")


# --------------------------------------------------------- side selection ----
def _drive_veto(fmt: str, pool_size: int):
    """Run a whole veto: always take the first remaining map, always attack."""
    from bot.core.controllers import VetoController

    ctl = VetoController(7, fmt, [f"m{i}" for i in range(pool_size)], 111, 222)
    while not ctl.done:
        if ctl.current.action == "side":
            ctl.apply_side("attack")
        else:
            ctl.apply(ctl.remaining[0])
    return ctl


@pytest.mark.parametrize("fmt,pool_size", [("BO1", 7), ("BO1", 2), ("BO3", 7), ("BO5", 7)])
def test_every_played_map_gets_its_own_side_pick(fmt, pool_size):
    ctl = _drive_veto(fmt, pool_size)
    assert [m for m, _side, _choice in ctl.sides] == ctl.picked_maps
    assert all(choice == "attack" for _m, _side, choice in ctl.sides)
    assert ctl.decider_map == ctl.picked_maps[-1]


@pytest.mark.parametrize("fmt", ["BO3", "BO5"])
def test_the_team_that_picks_a_map_does_not_pick_its_side(fmt):
    ctl = _drive_veto(fmt, 7)
    pickers = [side for action, side, _m, _c in ctl.history if action == "pick"]
    sides = [side for _m, side, _c in ctl.sides]
    for picker, chooser in zip(pickers, sides):
        assert chooser != picker


def test_bo5_decider_side_goes_to_team_b():
    """BO5 ends on picks, not bans, so the alternation leaves it with B."""
    assert _drive_veto("BO5", 7).sides[-1][1] == "B"


@pytest.mark.parametrize("fmt", ["BO1", "BO3", "BO5"])
def test_a_veto_is_not_done_until_the_last_side_is_chosen(fmt):
    """The decider auto-resolves once one map is left; the side after it still
    needs a captain, so the flow must not walk off to the lobby early."""
    from bot.core.controllers import VetoController

    ctl = VetoController(7, fmt, [f"m{i}" for i in range(7)], 111, 222)
    while ctl.current.action != "side" or ctl.remaining:
        if ctl.current.action == "side":
            ctl.apply_side("defence")
        else:
            ctl.apply(ctl.remaining[0])
    assert not ctl.done                      # decider gone, final side pending
    assert ctl.current_side_map == ctl.decider_map
    assert ctl.apply_side("defence") is True
    assert ctl.done


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


# ------------------------------------------------------------- ready check ---
def _check(starters, round_no=1):
    from datetime import timedelta

    from bot.core.controllers import ReadyCheckController

    return ReadyCheckController(
        1, "Friday 5v5", starters,
        datetime.now(timezone.utc) + timedelta(seconds=120), round_no,
    )


def test_ready_check_starts_with_nobody_answered():
    c = _check([1, 2, 3, 4])
    assert c.missing == [1, 2, 3, 4]
    assert not c.all_answered and not c.everyone_ready
    assert c.absent == [1, 2, 3, 4]


def test_ready_check_resolves_once_everyone_has_answered():
    """A decline is an answer — the check shouldn't sit out the clock for it."""
    c = _check([1, 2])
    c.mark(1, True)
    assert not c.all_answered
    c.mark(2, False)
    assert c.all_answered and not c.everyone_ready
    assert c.absent == [2]


def test_ready_check_passes_only_when_every_starter_is_ready():
    c = _check([1, 2, 3])
    for u in (1, 2, 3):
        assert not c.everyone_ready
        c.mark(u, True)
    assert c.everyone_ready and c.absent == []


def test_ready_check_lets_a_player_change_their_mind():
    c = _check([1, 2])
    c.mark(1, False)
    assert c.absent == [1, 2]
    c.mark(1, True)                 # "actually I can play"
    assert c.declined == set() and c.ready == {1}
    assert c.absent == [2]


def test_ready_check_absent_covers_both_silence_and_refusal():
    c = _check([1, 2, 3, 4])
    c.mark(1, True)
    c.mark(2, False)                # refused
    assert set(c.absent) == {2, 3, 4}   # 3 and 4 never answered
    assert c.missing == [3, 4]


def test_ready_check_ignores_people_who_are_not_playing():
    c = _check([1, 2])
    assert c.is_starter(1) and not c.is_starter(99)


# ------------------------------------------------------- captain selection ---
def test_captain_method_choices_exclude_manual():
    """`manual` names two players, so it can't be fixed before anyone signs up."""
    from bot.services.draft import CAPTAIN_METHOD_LABEL, CREATE_METHODS

    assert "manual" not in CREATE_METHODS
    assert all(m in CAPTAIN_METHOD_LABEL for m in CREATE_METHODS)


def test_choose_captains_by_rr_and_peak():
    from bot.services.draft import choose_captains

    players = [
        {"user_id": 1, "cur_rr": 10, "peak_rank": "Iron 1"},
        {"user_id": 2, "cur_rr": 90, "peak_rank": "Gold 3"},
        {"user_id": 3, "cur_rr": 50, "peak_rank": "Radiant"},
    ]
    assert set(choose_captains("highest_rr", players)) == {2, 3}
    assert set(choose_captains("highest_peak", players)) == {3, 2}
    assert len(set(choose_captains("random", players))) == 2


# --------------------------------------------------------------- ASAP start ---
def test_blank_start_means_asap():
    from bot.core.actions import is_asap

    for raw in ("", "   ", "ASAP", "asap", "Now", "immediately", None):
        assert is_asap(raw), raw
    for raw in ("20:00", "2030-06-24T20:00", "tomorrow"):
        assert not is_asap(raw), raw


def test_asap_parses_to_now_not_an_error():
    """ASAP still gets a real instant, so the overlap rule keeps working."""
    from bot.core.actions import parse_start

    before = datetime.now(timezone.utc)
    got = parse_start("")
    after = datetime.now(timezone.utc)
    assert before <= got <= after


def test_asap_customs_still_conflict_on_overlap():
    """Two ASAP customs start at the same instant, so they must clash."""
    now = datetime.now(timezone.utc)
    assert _overlaps(now, 1, now, 1) is True


def test_start_text_says_asap_instead_of_a_clock():
    from types import SimpleNamespace

    from bot.core.embeds import start_line, start_text

    when = datetime(2030, 6, 24, 20, 0, tzinfo=timezone.utc)
    asap = SimpleNamespace(start_time=when, start_asap=True)
    timed = SimpleNamespace(start_time=when, start_asap=False)

    assert "ASAP" in start_text(asap) and "ASAP" in start_line(asap)
    assert "<t:" not in start_text(asap)          # never a timestamp
    assert "<t:" in start_text(timed) and "ASAP" not in start_line(timed)
