"""/maps management."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import select

from bot.core.permissions import require
from bot.core.ui import reply
from bot.db import SessionLocal
from bot.db.models import Map

DEFAULT_POOL = [
    "Ascent", "Bind", "Haven", "Split", "Lotus",
    "Sunset", "Icebox", "Abyss", "Pearl", "Fracture",
]


class MapsCog(commands.GroupCog, name="maps"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(description="List the guild map pool.")
    async def list(self, itx: discord.Interaction):
        async with SessionLocal() as s:
            rows = await s.execute(select(Map).where(Map.guild_id == itx.guild_id))
            maps = [r[0] for r in rows.all()]
        if not maps:
            return await reply(itx, "No maps configured. Admin: `/maps seed` to load defaults.")
        lines = [f"{'🟢' if m.enabled else '🔴'} {m.name}" for m in maps]
        await reply(itx, "\n".join(lines))

    @app_commands.command(description="Seed the default Valorant pool.")
    @require("admin")
    async def seed(self, itx: discord.Interaction):
        async with SessionLocal() as s:
            for name in DEFAULT_POOL:
                if not await s.get(Map, (itx.guild_id, name)):
                    s.add(Map(guild_id=itx.guild_id, name=name, enabled=True))
            await s.commit()
        await reply(itx, "Default pool seeded ✅")

    @app_commands.command(description="Add a map.")
    @require("admin")
    async def add(self, itx: discord.Interaction, name: str):
        async with SessionLocal() as s:
            if not await s.get(Map, (itx.guild_id, name)):
                s.add(Map(guild_id=itx.guild_id, name=name, enabled=True))
                await s.commit()
        await reply(itx, f"Added {name}.")

    @app_commands.command(description="Remove a map.")
    @require("admin")
    async def remove(self, itx: discord.Interaction, name: str):
        async with SessionLocal() as s:
            m = await s.get(Map, (itx.guild_id, name))
            if m:
                await s.delete(m)
                await s.commit()
        await reply(itx, f"Removed {name}.")

    @app_commands.command(description="Enable/disable a map.")
    @require("admin")
    async def toggle(self, itx: discord.Interaction, name: str):
        async with SessionLocal() as s:
            m = await s.get(Map, (itx.guild_id, name))
            if not m:
                return await reply(itx, "No such map.")
            m.enabled = not m.enabled
            state = m.enabled
            await s.commit()
        await reply(itx, f"{name} is now {'enabled' if state else 'disabled'}.")


async def setup(bot: commands.Bot):
    await bot.add_cog(MapsCog(bot))
