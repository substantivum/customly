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
from bot.i18n import t
from bot.i18n.translator import L
from bot.services import maps as maps_svc

# Same on/off indicators the panel's map screen uses.
MAP_ON, MAP_OFF = "\U0001f7e2", "\U0001f534"


class MapsCog(commands.GroupCog, name="maps"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(description=L("cmd.maps.list.desc"))
    async def list(self, itx: discord.Interaction):
        async with SessionLocal() as s:
            rows = await s.execute(select(Map).where(Map.guild_id == itx.guild_id))
            maps = [r[0] for r in rows.all()]
        if not maps:
            return await reply(itx, t("maps.none_configured"))
        lines = [
            t("maps.list_line_comp" if m.competitive else "maps.list_line",
              dot=MAP_ON if m.enabled else MAP_OFF, name=m.name)
            for m in maps
        ]
        await reply(itx, "\n".join(lines))

    @app_commands.command(description=L("cmd.maps.seed.desc"))
    @require("admin")
    async def seed(self, itx: discord.Interaction):
        await maps_svc.seed(itx.guild_id)
        await reply(itx, t("maps.seeded_ok"))

    @app_commands.command(description=L("cmd.maps.competitive.desc"))
    @require("admin")
    @app_commands.describe(maps=L("cmd.maps.competitive.maps"))
    async def competitive(self, itx: discord.Interaction, maps: str = ""):
        in_pool, unknown = await maps_svc.set_competitive(itx.guild_id, maps.split(","))
        msg = (t("maps.comp_set", maps=", ".join(in_pool)) if in_pool
               else t("maps.comp_cleared"))
        if unknown:
            msg += t("maps.comp_unknown", maps=", ".join(unknown))
        await reply(itx, msg)

    @app_commands.command(description=L("cmd.maps.add.desc"))
    @require("admin")
    async def add(self, itx: discord.Interaction, name: str):
        async with SessionLocal() as s:
            if not await s.get(Map, (itx.guild_id, name)):
                s.add(Map(guild_id=itx.guild_id, name=name, enabled=True))
                await s.commit()
        await reply(itx, t("maps.added_cmd", name=name))

    @app_commands.command(description=L("cmd.maps.remove.desc"))
    @require("admin")
    async def remove(self, itx: discord.Interaction, name: str):
        async with SessionLocal() as s:
            m = await s.get(Map, (itx.guild_id, name))
            if m:
                await s.delete(m)
                await s.commit()
        await reply(itx, t("maps.removed", name=name))

    @app_commands.command(description=L("cmd.maps.toggle.desc"))
    @require("admin")
    async def toggle(self, itx: discord.Interaction, name: str):
        async with SessionLocal() as s:
            m = await s.get(Map, (itx.guild_id, name))
            if not m:
                return await reply(itx, t("maps.no_such"))
            m.enabled = not m.enabled
            state = m.enabled
            await s.commit()
        await reply(itx, t("maps.toggled", name=name,
                           state=t("common.enabled" if state else "common.disabled")))


async def setup(bot: commands.Bot):
    await bot.add_cog(MapsCog(bot))
