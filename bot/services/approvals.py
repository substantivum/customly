"""Rank-identity approval queue, across all three games.

A submitted identity — a Riot ID, a Faceit nickname, a Dota friend id — counts
nowhere in the bot (rank data, captain selection) until an admin approves it
here. There's no OAuth proving a Discord user owns any of these accounts, so a
human is the trust step. One queue, one screen; each pending item carries which
game it's for.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import or_, select

from bot.db import SessionLocal
from bot.db.models import User

log = logging.getLogger("customly.approvals")

# game -> (status column, reviewed_by column, reviewed_at column, identity attr)
_FIELDS = {
    "valorant": ("riot_status", "riot_reviewed_by", "riot_reviewed_at", "riot_id"),
    "cs2": ("cs2_status", "cs2_reviewed_by", "cs2_reviewed_at", "cs2_nick"),
    "dota2": ("dota_status", "dota_reviewed_by", "dota_reviewed_at", "dota_friend_id"),
}
GAMES = tuple(_FIELDS)


@dataclass
class Pending:
    user_id: int
    game: str
    identity: str


def _identity(u: User, game: str) -> str:
    return getattr(u, _FIELDS[game][3]) or ""


async def list_pending() -> list[Pending]:
    """Every pending identity, oldest submitter first. A player pending in two
    games appears twice (once per game)."""
    async with SessionLocal() as s:
        rows = await s.execute(
            select(User).where(or_(
                User.riot_status == "pending",
                User.cs2_status == "pending",
                User.dota_status == "pending",
            )).order_by(User.created_at)
        )
        out: list[Pending] = []
        for (u,) in rows.all():
            for game, (status_col, *_rest) in _FIELDS.items():
                if getattr(u, status_col) == "pending":
                    out.append(Pending(u.user_id, game, _identity(u, game)))
        log.debug("%d pending identity submission(s)", len(out))
        return out


async def resolve(user_id: int, game: str, reviewer_id: int, *, approve: bool) -> User | None:
    """None if that game wasn't pending any more (already reviewed, or gone)."""
    if game not in _FIELDS:
        return None
    status_f, by_f, at_f, _ = _FIELDS[game]
    async with SessionLocal() as s:
        u = await s.get(User, user_id)
        if not u or getattr(u, status_f) != "pending":
            log.info("%s resolve for %s dropped: not pending any more", game, user_id)
            return None
        setattr(u, status_f, "approved" if approve else "denied")
        setattr(u, by_f, reviewer_id)
        setattr(u, at_f, datetime.now(timezone.utc))
        await s.commit()
        await s.refresh(u)
        log.info("%s identity -> %s for %s by reviewer %s",
                 game, getattr(u, status_f), user_id, reviewer_id)
        return u
