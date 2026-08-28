"""Riot ID approval queue: a submitted Riot ID counts nowhere in the bot
(rank data, captain selection) until an admin approves it."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select

from bot.db import SessionLocal
from bot.db.models import User

log = logging.getLogger("customly.riot_approvals")


async def list_pending() -> list[User]:
    async with SessionLocal() as s:
        rows = await s.execute(
            select(User).where(User.riot_status == "pending").order_by(User.created_at)
        )
        pending = [r[0] for r in rows.all()]
        log.debug("%d pending riot id submission(s)", len(pending))
        return pending


async def resolve(user_id: int, reviewer_id: int, *, approve: bool) -> User | None:
    """None if it wasn't pending any more (already reviewed, or never submitted)."""
    async with SessionLocal() as s:
        u = await s.get(User, user_id)
        if not u or u.riot_status != "pending":
            log.info("riot resolve for %s dropped: not pending any more", user_id)
            return None
        u.riot_status = "approved" if approve else "denied"
        u.riot_reviewed_by = reviewer_id
        u.riot_reviewed_at = datetime.now(timezone.utc)
        await s.commit()
        await s.refresh(u)
        log.info("riot id %s -> %s for %s by reviewer %s",
                 u.riot_id, u.riot_status, user_id, reviewer_id)
        return u
