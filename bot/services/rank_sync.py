"""Keeps User.cur_rank/cur_rr/peak_rank fresh from HenrikDev, approved
players only. A Henrik outage must never block /profile or captain
selection, so every failure here falls back to the last-known DB values."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from bot.core.embeds import as_utc
from bot.db import SessionLocal
from bot.db.models import User
from bot.services import henrik

log = logging.getLogger("customly.rank_sync")

RANK_TTL = timedelta(minutes=10)


def _stale(u: User) -> bool:
    if not u.rank_updated_at:
        return True
    return datetime.now(timezone.utc) - as_utc(u.rank_updated_at) > RANK_TTL


async def refresh_rank(user_id: int, *, force: bool = False) -> User | None:
    """Best-effort: never raises. Returns the (possibly just-refreshed) row,
    or None if there's no row at all."""
    async with SessionLocal() as s:
        u = await s.get(User, user_id)
        if not u or u.riot_status != "approved" or not u.riot_id or not u.riot_puuid:
            log.debug("rank refresh no-op for %s: not an approved, registered player", user_id)
            return u
        if not force and not _stale(u):
            log.debug("rank refresh skipped for %s: cache still fresh", user_id)
            return u
        try:
            rank = await henrik.fetch_mmr_by_puuid(u.riot_region or "na", u.riot_puuid)
        except henrik.HenrikError as e:
            log.info("rank refresh skipped for %s: %s", user_id, e)
            return u
        u.cur_rank, u.cur_rr = rank.cur_tier, rank.cur_rr
        # A brand-new account's null peak shouldn't erase a previously-known one.
        u.peak_rank = rank.peak_tier or u.peak_rank
        u.rank_updated_at = datetime.now(timezone.utc)
        await s.commit()
        await s.refresh(u)
        log.info("rank refreshed for %s: cur=%s (%s RR) peak=%s",
                 user_id, u.cur_rank, u.cur_rr, u.peak_rank)
        return u
