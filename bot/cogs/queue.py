"""/queue status — registration happens via /custom register or the panel."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.ui import reply
from bot.db import SessionLocal
from bot.i18n import t
from bot.i18n.translator import L
from bot.services import custom as custom_svc


class QueueCog(commands.GroupCog, name="queue"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(description=L("cmd.queue.status.desc"))
    async def status(self, itx: discord.Interaction, custom_id: int):
        async with SessionLocal() as s:
            await custom_svc.get_in_guild(s, custom_id, itx.guild_id)
        r = await custom_svc.roster(custom_id)
        if not r.size:
            return await reply(itx, t("queue.none"))
        body = "\n".join(f"\u2022 <@{u}>" for u in r.starters) or t("queue.empty")
        if r.waitlist:
            body += t("queue.waitlist",
                      members=", ".join(f"<@{u}>" for u in r.waitlist))
        header = t("queue.header", custom_id=custom_id, n=len(r.starters), size=r.size)
        await reply(itx, f"{header}\n{body}")


async def setup(bot: commands.Bot):
    await bot.add_cog(QueueCog(bot))
