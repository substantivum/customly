"""/stats — minimal; full accrual/Elo/tournaments are stubbed (see README)."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import select

from bot.core.embeds import VAL_RED
from bot.core.ui import reply
from bot.db import SessionLocal
from bot.db.models import PlayerStats


class StatsCog(commands.GroupCog, name="stats"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(description="Your stats.")
    async def me(self, itx: discord.Interaction):
        async with SessionLocal() as s:
            ps = await s.get(PlayerStats, (itx.guild_id, 0, itx.user.id))
        if not ps:
            return await reply(itx, "No stats yet.")
        e = discord.Embed(title="Your stats", color=VAL_RED)
        e.add_field(name="Played", value=ps.played)
        e.add_field(name="W/L", value=f"{ps.wins}/{ps.losses}")
        e.add_field(name="MVPs", value=ps.mvps)
        await reply(itx, embed=e)

    @app_commands.command(description="Wins leaderboard.")
    async def leaderboard(self, itx: discord.Interaction):
        async with SessionLocal() as s:
            rows = await s.execute(
                select(PlayerStats).where(PlayerStats.guild_id == itx.guild_id)
                .order_by(PlayerStats.wins.desc()).limit(10)
            )
            top = [r[0] for r in rows.all()]
        if not top:
            return await reply(itx, "No stats yet.")
        lines = [f"{i+1}. <@{p.user_id}> — {p.wins} wins" for i, p in enumerate(top)]
        await reply(itx, "\n".join(lines))


async def setup(bot: commands.Bot):
    await bot.add_cog(StatsCog(bot))
