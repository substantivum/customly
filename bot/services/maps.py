"""Guild map pool queries + the "current competitive pool" subset.

The competitive pool is just a flag on the guild's maps: admins tick whichever
maps Riot currently has in rotation, and custom creation can then take that
whole set in one click instead of re-picking it every time.
"""
from __future__ import annotations

from sqlalchemy import select

from bot.core import audit
from bot.db import SessionLocal
from bot.db.models import Map

DEFAULT_POOLS = {
    "valorant": [
        "Abyss", "Ascent", "Bind", "Breeze", "Corrode", "Haven", "Lotus", "Split", "Summit",
        "Sunset", "Icebox", "Pearl", "Fracture",
    ],
    "cs2": [
        "Ancient", "Anubis", "Dust II", "Inferno", "Mirage", "Nuke", "Train",
    ],
}

# What a user can type instead of a map list to mean "the competitive pool".
COMPETITIVE_TOKENS = {"competitive", "comp", "competitive pool", "current"}


async def all_maps(guild_id: int, game: str = "valorant") -> list[Map]:
    async with SessionLocal() as s:
        rows = await s.execute(
            select(Map).where(Map.guild_id == guild_id, Map.game == game)
            .order_by(Map.name)
        )
        return [r[0] for r in rows.all()]


async def enabled_maps(guild_id: int, game: str = "valorant") -> list[Map]:
    async with SessionLocal() as s:
        rows = await s.execute(
            select(Map).where(
                Map.guild_id == guild_id, Map.game == game, Map.enabled.is_(True)
            ).order_by(Map.name)
        )
        return [r[0] for r in rows.all()]


async def competitive_names(guild_id: int, game: str = "valorant") -> list[str]:
    """Names in the competitive pool that are also enabled — the only ones a
    custom could legally use."""
    async with SessionLocal() as s:
        rows = await s.execute(
            select(Map.name).where(
                Map.guild_id == guild_id,
                Map.game == game,
                Map.competitive.is_(True),
                Map.enabled.is_(True),
            ).order_by(Map.name)
        )
        return [r[0] for r in rows.all()]


async def set_competitive(
    guild_id: int, names: list[str], actor_id: int | None = None, game: str = "valorant"
) -> tuple[list[str], list[str]]:
    """Make the competitive pool exactly `names` (case-insensitive).

    Maps put in the pool are enabled too — an admin marking a map competitive
    means to play it, and a disabled map is rejected at custom creation.
    Returns (in_pool, unknown_names).
    """
    wanted = {n.strip().lower() for n in names if n.strip()}
    in_pool, seen = [], set()
    async with SessionLocal() as s:
        rows = await s.execute(
            select(Map).where(Map.guild_id == guild_id, Map.game == game)
        )
        for (m,) in rows.all():
            hit = m.name.lower() in wanted
            m.competitive = hit
            if hit:
                m.enabled = True
                in_pool.append(m.name)
                seen.add(m.name.lower())
        await s.commit()
    in_pool, unknown = sorted(in_pool), sorted(wanted - seen)
    if actor_id is not None:
        await audit.log(guild_id, actor_id, "maps_competitive", meta=",".join(in_pool))
    return in_pool, unknown


async def seed(guild_id: int, game: str = "valorant") -> list[str]:
    """Add any missing default maps for `game`. Returns the names added."""
    added = []
    async with SessionLocal() as s:
        for name in DEFAULT_POOLS.get(game, []):
            if not await s.get(Map, (guild_id, name)):
                s.add(Map(guild_id=guild_id, name=name, enabled=True, game=game))
                added.append(name)
        await s.commit()
    return added


async def add_map(
    guild_id: int, name: str, actor_id: int | None = None, game: str = "valorant"
) -> bool:
    """Add `name` to the pool if it isn't already there. Returns True if added."""
    async with SessionLocal() as s:
        if await s.get(Map, (guild_id, name)):
            return False
        s.add(Map(guild_id=guild_id, name=name, enabled=True, game=game))
        await s.commit()
    if actor_id is not None:
        await audit.log(guild_id, actor_id, "map_add", name)
    return True


async def remove_map(guild_id: int, name: str, actor_id: int | None = None) -> bool:
    """Remove `name` from the pool. Returns True if it existed."""
    async with SessionLocal() as s:
        m = await s.get(Map, (guild_id, name))
        if not m:
            return False
        await s.delete(m)
        await s.commit()
    if actor_id is not None:
        await audit.log(guild_id, actor_id, "map_remove", name)
    return True


async def toggle_map(guild_id: int, name: str, actor_id: int | None = None) -> bool | None:
    """Flip `name`'s enabled state. Returns the new state, or None if `name`
    isn't in the pool."""
    async with SessionLocal() as s:
        m = await s.get(Map, (guild_id, name))
        if not m:
            return None
        m.enabled = not m.enabled
        state = m.enabled
        await s.commit()
    if actor_id is not None:
        await audit.log(guild_id, actor_id, "map_toggle", name, enabled=state)
    return state
