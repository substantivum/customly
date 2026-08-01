"""Registry of posted control boards.

The boards are *live* messages — their embeds are redrawn whenever a custom is
created, filled, started or torn down — so the bot has to remember where they
are. One row per (guild, tier).
"""
from __future__ import annotations

from sqlalchemy import select

from bot.db import SessionLocal
from bot.db.models import PanelBoard

TIERS = ("player", "admin", "superadmin")


async def save(
    guild_id: int, tier: str, channel_id: int, message_id: int, posted_by: int | None = None
) -> tuple[int, int] | None:
    """Record a freshly posted board. Returns the (channel_id, message_id) of the
    board it replaced, so the caller can delete the old message."""
    async with SessionLocal() as s:
        row = await s.get(PanelBoard, (guild_id, tier))
        previous = (row.channel_id, row.message_id) if row else None
        if row is None:
            row = PanelBoard(guild_id=guild_id, tier=tier,
                             channel_id=channel_id, message_id=message_id)
            s.add(row)
        else:
            row.channel_id, row.message_id = channel_id, message_id
        row.posted_by = posted_by
        await s.commit()
    return previous


async def boards(guild_id: int) -> list[PanelBoard]:
    async with SessionLocal() as s:
        rows = await s.execute(
            select(PanelBoard).where(PanelBoard.guild_id == guild_id)
        )
        return [r[0] for r in rows.all()]


async def forget(guild_id: int, tier: str) -> None:
    """Drop a board we can no longer reach (deleted message or channel)."""
    async with SessionLocal() as s:
        row = await s.get(PanelBoard, (guild_id, tier))
        if row:
            await s.delete(row)
            await s.commit()
