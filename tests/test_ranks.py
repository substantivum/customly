"""Pure-logic tests for the rank ordinal table and the HenrikDev response
parsers (no HTTP/DB needed). Run: pytest -q"""
from __future__ import annotations

import pytest

from bot.services.henrik import parse_account, parse_mmr
from bot.services.ranks import rank_value, shuffled_by_key

ORDERED_RANKS = [
    "Iron 1", "Iron 2", "Iron 3",
    "Bronze 1", "Bronze 2", "Bronze 3",
    "Silver 1", "Silver 2", "Silver 3",
    "Gold 1", "Gold 2", "Gold 3",
    "Platinum 1", "Platinum 2", "Platinum 3",
    "Diamond 1", "Diamond 2", "Diamond 3",
    "Ascendant 1", "Ascendant 2", "Ascendant 3",
    "Immortal 1", "Immortal 2", "Immortal 3",
    "Radiant",
]


def test_rank_value_is_strictly_increasing_through_every_tier():
    values = [rank_value(r) for r in ORDERED_RANKS]
    assert values == sorted(values)
    assert len(set(values)) == len(values)          # every rank is distinct
    assert values[0] == 1 and values[-1] == 25       # Iron 1 .. Radiant


def test_rank_value_distinguishes_sub_tiers():
    """The old dict only compared base tier — Immortal 1 and Immortal 3 were
    fully tied. The new table must not repeat that."""
    assert rank_value("Immortal 1") < rank_value("Immortal 2") < rank_value("Immortal 3")


@pytest.mark.parametrize("bad", [None, "", "Unranked", "Nonsense 9"])
def test_rank_value_unknown_or_unset_is_zero(bad):
    assert rank_value(bad) == 0


def test_rank_value_is_case_and_space_insensitive():
    assert rank_value("immortal 2") == rank_value("Immortal 2")
    assert rank_value("  Radiant  ") == rank_value("Radiant")


def test_shuffled_by_key_keeps_the_correct_order_when_nothing_ties():
    items = [{"id": 1, "v": 1}, {"id": 2, "v": 9}, {"id": 3, "v": 5}]
    for _ in range(50):
        ranked = shuffled_by_key(items, key=lambda p: p["v"])
        assert [p["id"] for p in ranked] == [2, 3, 1]


def test_shuffled_by_key_randomizes_among_ties():
    """Regression test: sorted() alone is stable, so ties used to always
    resolve to whichever item came first in the input."""
    items = [{"id": i, "v": 5} for i in range(5)]
    winners = {shuffled_by_key(items, key=lambda p: p["v"])[0]["id"] for _ in range(200)}
    assert len(winners) > 1


# ------------------------------------------------------------ henrik parsing --
ACCOUNT_PAYLOAD = {
    "status": 200,
    "data": {
        "puuid": "04bb9a05-e466-5cf3-bddb-6bc0c50ae15e",
        "region": "eu",
        "name": "Nrk",
        "tag": "sun",
        "account_level": 123,
    },
}

MMR_PAYLOAD = {
    "status": 200,
    "data": {
        "account": {"name": "Nrk", "tag": "sun", "puuid": "04bb9a05-e466-5cf3-bddb-6bc0c50ae15e"},
        "peak": {
            "season": {"id": "22d10d66-4d2a-a340-6c54-408c7bd53807", "short": "e8a2"},
            "ranking_schema": "ascendant",
            "tier": {"id": 27, "name": "Radiant"},
            "rr": 0,
        },
        "current": {
            "tier": {"id": 27, "name": "Radiant"},
            "rr": 795,
            "last_change": 21,
            "elo": 2895,
            "games_needed_for_rating": 1,
            "rank_protection_shields": 2,
            "leaderboard_placement": None,
        },
        "seasonal": [],
    },
}


def test_parse_account_pulls_puuid_region_name_tag():
    account = parse_account(ACCOUNT_PAYLOAD)
    assert account.puuid == "04bb9a05-e466-5cf3-bddb-6bc0c50ae15e"
    assert account.region == "eu"
    assert account.name == "Nrk" and account.tag == "sun"
    assert account.account_level == 123


def test_parse_mmr_pulls_current_and_peak():
    rank = parse_mmr(MMR_PAYLOAD)
    assert rank.cur_tier == "Radiant" and rank.cur_rr == 795
    assert rank.peak_tier == "Radiant" and rank.peak_rr == 0


def test_parse_mmr_survives_a_null_peak():
    """A brand-new account has no peak history yet — the API returns
    `"peak": null`, which must not raise."""
    payload = {"data": {**MMR_PAYLOAD["data"], "peak": None}}
    rank = parse_mmr(payload)
    assert rank.peak_tier is None and rank.peak_rr is None
    assert rank.cur_tier == "Radiant"
