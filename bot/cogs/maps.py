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
from bot.services import maps as maps_svc


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
        lines = [f"{'🟢' if m.enabled else '🔴'} {m.name}"
                 f"{' ⭐ competitive' if m.competitive else ''}" for m in maps]
        await reply(itx, "\n".join(lines))

    @app_commands.command(description="Seed the default Valorant pool.")
    @require("admin")
    async def seed(self, itx: discord.Interaction):
        await maps_svc.seed(itx.guild_id)
        await reply(itx, "Default pool seeded ✅")

    @app_commands.command(
        description="Set the current competitive map pool (admin). Empty clears it."
    )
    @require("admin")
    @app_commands.describe(
        maps="Comma-separated maps in the active rotation — blank to clear the pool"
    )
    async def competitive(self, itx: discord.Interaction, maps: str = ""):
        in_pool, unknown = await maps_svc.set_competitive(itx.guild_id, maps.split(","))
        msg = (f"⭐ Competitive pool: **{', '.join(in_pool)}**"
               if in_pool else "Competitive pool cleared.")
        if unknown:
            msg += f"\nNot in this server's map list (ignored): {', '.join(unknown)}"
        await reply(itx, msg)

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
