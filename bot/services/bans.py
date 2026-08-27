"""Player bans: blocked from registering for any future games."""
from __future__ import annotations

from sqlalchemy import select

from bot.db import SessionLocal
from bot.db.models import Ban


async def is_banned(guild_id: int, user_id: int) -> bool:
    async with SessionLocal() as s:
        return (await s.get(Ban, (guild_id, user_id))) is not None


async def ban(guild_id: int, user_id: int, by: int, reason: str | None = None) -> bool:
    """Returns True if newly banned, False if already banned."""
    async with SessionLocal() as s:
        if await s.get(Ban, (guild_id, user_id)):
            return False
        s.add(Ban(guild_id=guild_id, user_id=user_id, banned_by=by, reason=reason))
        await s.commit()
        return True


async def unban(guild_id: int, user_id: int) -> bool:
    """Returns True if a ban was removed."""
    async with SessionLocal() as s:
        b = await s.get(Ban, (guild_id, user_id))
        if not b:
            return False
        await s.delete(b)
        await s.commit()
        return True


async def list_bans(guild_id: int) -> list[Ban]:
    async with SessionLocal() as s:
        rows = await s.execute(select(Ban).where(Ban.guild_id == guild_id))
        return [r[0] for r in rows.all()]
