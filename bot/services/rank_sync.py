"""Keeps each game's cached rank fresh from its API — approved players only.

One refresher per game (Valorant→Henrik, CS2→Faceit, Dota→OpenDota), all
best-effort: an API outage must never block /profile or captain selection, so
every failure falls back to the last-known DB values.

`captain_metrics` is the game-agnostic bridge to captain selection: it turns
whichever rank a game stores into two numbers (current, peak) that
`bot.services.draft` ranks players by, so `highest_rr`/`highest_peak` mean "best
current / best peak rank" whatever the game.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from bot.core.embeds import as_utc
from bot.db import SessionLocal
from bot.db.models import User
from bot.services import faceit, henrik, opendota, ranks

log = logging.getLogger("customly.rank_sync")

RANK_TTL = timedelta(minutes=10)


def _stale_at(dt: datetime | None) -> bool:
    if not dt:
        return True
    return datetime.now(timezone.utc) - as_utc(dt) > RANK_TTL


# --------------------------------------------------------------- Valorant ----
async def refresh_rank(user_id: int, *, force: bool = False) -> User | None:
    """Valorant rank via HenrikDev. Never raises; returns the row (or None)."""
    async with SessionLocal() as s:
        u = await s.get(User, user_id)
        if not u or u.riot_status != "approved" or not u.riot_id or not u.riot_puuid:
            return u
        if not force and not _stale_at(u.rank_updated_at):
            return u
        try:
            rank = await henrik.fetch_mmr_by_puuid(u.riot_region or "na", u.riot_puuid)
        except henrik.HenrikError as e:
            log.info("valorant rank refresh skipped for %s: %s", user_id, e)
            return u
        u.cur_rank, u.cur_rr = rank.cur_tier, rank.cur_rr
        # A brand-new account's null peak shouldn't erase a previously-known one.
        u.peak_rank = rank.peak_tier or u.peak_rank
        u.rank_updated_at = datetime.now(timezone.utc)
        await s.commit()
        await s.refresh(u)
        log.info("valorant rank refreshed for %s: cur=%s (%s RR) peak=%s",
                 user_id, u.cur_rank, u.cur_rr, u.peak_rank)
        return u


# -------------------------------------------------------------------- CS2 ----
async def refresh_cs2(user_id: int, *, force: bool = False) -> User | None:
    """CS2 skill level + elo via Faceit."""
    async with SessionLocal() as s:
        u = await s.get(User, user_id)
        if not u or u.cs2_status != "approved" or not u.cs2_faceit_id:
            return u
        if not force and not _stale_at(u.cs2_updated_at):
            return u
        try:
            p = await faceit.fetch_player_by_id(u.cs2_faceit_id)
        except faceit.FaceitError as e:
            log.info("cs2 rank refresh skipped for %s: %s", user_id, e)
            return u
        u.cs2_level, u.cs2_elo = p.level, p.elo
        u.cs2_updated_at = datetime.now(timezone.utc)
        await s.commit()
        await s.refresh(u)
        log.info("cs2 rank refreshed for %s: level=%s elo=%s", user_id, u.cs2_level, u.cs2_elo)
        return u


# ------------------------------------------------------------------- Dota ----
async def refresh_dota(user_id: int, *, force: bool = False) -> User | None:
    """Dota rank medal via OpenDota."""
    async with SessionLocal() as s:
        u = await s.get(User, user_id)
        if not u or u.dota_status != "approved" or not u.dota_friend_id:
            return u
        if not force and not _stale_at(u.dota_updated_at):
            return u
        try:
            p = await opendota.fetch_player(int(u.dota_friend_id))
        except (opendota.DotaError, ValueError) as e:
            log.info("dota rank refresh skipped for %s: %s", user_id, e)
            return u
        # rank_tier can legitimately be null (unranked); keep the old one only if
        # the fresh read gave nothing at all.
        u.dota_rank_tier = p.rank_tier if p.rank_tier is not None else u.dota_rank_tier
        u.dota_leaderboard = p.leaderboard_rank
        u.dota_updated_at = datetime.now(timezone.utc)
        await s.commit()
        await s.refresh(u)
        log.info("dota rank refreshed for %s: rank_tier=%s", user_id, u.dota_rank_tier)
        return u


# -------------------------------------------------------------- dispatch ----
_REFRESHERS = {"valorant": refresh_rank, "cs2": refresh_cs2, "dota2": refresh_dota}


async def refresh_for_game(user_id: int, game: str, *, force: bool = False) -> User | None:
    fn = _REFRESHERS.get(game, refresh_rank)
    return await fn(user_id, force=force)


async def refresh_all(user_id: int, *, force: bool = False) -> User | None:
    """Refresh every game the player is approved in. Returns the final row."""
    u = None
    for fn in _REFRESHERS.values():
        u = await fn(user_id, force=force)
    return u


def captain_metrics(u: User | None, game: str) -> dict:
    """(cur_score, peak_score) for captain ranking, in the game's own units —
    only for an *approved* identity, else both None so the method degrades to a
    random pick (see draft.has_enough_rank_data)."""
    if not u:
        return {"cur_score": None, "peak_score": None}
    if game == "cs2":
        ok = u.cs2_status == "approved"
        return {"cur_score": u.cs2_elo if ok else None,
                "peak_score": u.cs2_elo if ok else None}
    if game == "dota2":
        ok = u.dota_status == "approved"
        return {"cur_score": u.dota_rank_tier if ok else None,
                "peak_score": u.dota_rank_tier if ok else None}
    ok = u.riot_status == "approved"          # valorant / default
    return {"cur_score": u.cur_rr if ok else None,
            "peak_score": ranks.rank_value(u.peak_rank) if (ok and u.peak_rank) else None}
