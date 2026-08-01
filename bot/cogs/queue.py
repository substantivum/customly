"""/queue status — registration happens via /custom register or the panel."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.ui import reply
from bot.services import custom as custom_svc


class QueueCog(commands.GroupCog, name="queue"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(description="Show a custom's queue status.")
    async def status(self, itx: discord.Interaction, custom_id: int):
        r = await custom_svc.roster(custom_id)
        if not r.size:
            return await reply(itx, "No queue for that custom.")
        body = "\n".join(f"• <@{u}>" for u in r.starters) or "_empty_"
        if r.waitlist:
            body += "\n**🪑 Waitlist:** " + ", ".join(f"<@{u}>" for u in r.waitlist)
        await reply(
            itx,
            f"**Queue for Custom #{custom_id}** ({len(r.starters)}/{r.size})\n{body}",
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(QueueCog(bot))
