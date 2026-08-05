"""/stats — minimal; full accrual/Elo/tournaments are stubbed (see README)."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import select

from bot.core.embeds import EMBED_COLOR
from bot.core.ui import reply
from bot.db import SessionLocal
from bot.db.models import PlayerStats
from bot.i18n import t
from bot.i18n.translator import L


class StatsCog(commands.GroupCog, name="stats"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(description=L("cmd.stats.me.desc"))
    async def me(self, itx: discord.Interaction):
        async with SessionLocal() as s:
            ps = await s.get(PlayerStats, (itx.guild_id, 0, itx.user.id))
        if not ps:
            return await reply(itx, t("stats.none"))
        e = discord.Embed(title=t("stats.title"), color=EMBED_COLOR)
        e.add_field(name=t("stats.played"), value=ps.played)
        e.add_field(name=t("stats.wl"), value=f"{ps.wins}/{ps.losses}")
        e.add_field(name=t("stats.mvps"), value=ps.mvps)
        await reply(itx, embed=e)

    @app_commands.command(description=L("cmd.stats.leaderboard.desc"))
    async def leaderboard(self, itx: discord.Interaction):
        async with SessionLocal() as s:
            rows = await s.execute(
                select(PlayerStats).where(PlayerStats.guild_id == itx.guild_id)
                .order_by(PlayerStats.wins.desc()).limit(10)
            )
            top = [r[0] for r in rows.all()]
        if not top:
            return await reply(itx, t("stats.none"))
        lines = [t("stats.leader_line", rank=i + 1, user_id=p.user_id, wins=p.wins)
                 for i, p in enumerate(top)]
        await reply(itx, "\n".join(lines))


async def setup(bot: commands.Bot):
    await bot.add_cog(StatsCog(bot))
