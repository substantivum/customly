"""Guild map pool queries + the "current competitive pool" subset.

The competitive pool is just a flag on the guild's maps: admins tick whichever
maps Riot currently has in rotation, and custom creation can then take that
whole set in one click instead of re-picking it every time.
"""
from __future__ import annotations

from sqlalchemy import select

from bot.db import SessionLocal
from bot.db.models import Map

DEFAULT_POOL = [
    "Ascent", "Bind", "Haven", "Split", "Lotus",
    "Sunset", "Icebox", "Abyss", "Pearl", "Fracture",
]

# What a user can type instead of a map list to mean "the competitive pool".
COMPETITIVE_TOKENS = {"competitive", "comp", "competitive pool", "current"}


async def all_maps(guild_id: int) -> list[Map]:
    async with SessionLocal() as s:
        rows = await s.execute(
            select(Map).where(Map.guild_id == guild_id).order_by(Map.name)
        )
        return [r[0] for r in rows.all()]


async def enabled_maps(guild_id: int) -> list[Map]:
    async with SessionLocal() as s:
        rows = await s.execute(
            select(Map).where(Map.guild_id == guild_id, Map.enabled.is_(True))
            .order_by(Map.name)
        )
        return [r[0] for r in rows.all()]


async def competitive_names(guild_id: int) -> list[str]:
    """Names in the competitive pool that are also enabled — the only ones a
    custom could legally use."""
    async with SessionLocal() as s:
        rows = await s.execute(
            select(Map.name).where(
                Map.guild_id == guild_id,
                Map.competitive.is_(True),
                Map.enabled.is_(True),
            ).order_by(Map.name)
        )
        return [r[0] for r in rows.all()]


async def set_competitive(guild_id: int, names: list[str]) -> tuple[list[str], list[str]]:
    """Make the competitive pool exactly `names` (case-insensitive).

    Maps put in the pool are enabled too — an admin marking a map competitive
    means to play it, and a disabled map is rejected at custom creation.
    Returns (in_pool, unknown_names).
    """
    wanted = {n.strip().lower() for n in names if n.strip()}
    in_pool, seen = [], set()
    async with SessionLocal() as s:
        rows = await s.execute(select(Map).where(Map.guild_id == guild_id))
        for (m,) in rows.all():
            hit = m.name.lower() in wanted
            m.competitive = hit
            if hit:
                m.enabled = True
                in_pool.append(m.name)
                seen.add(m.name.lower())
        await s.commit()
    return sorted(in_pool), sorted(wanted - seen)


async def seed(guild_id: int) -> list[str]:
    """Add any missing default maps. Returns the names added."""
    added = []
    async with SessionLocal() as s:
        for name in DEFAULT_POOL:
            if not await s.get(Map, (guild_id, name)):
                s.add(Map(guild_id=guild_id, name=name, enabled=True))
                added.append(name)
        await s.commit()
    return added
