"""/queue status — registration happens via /custom register or the panel."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.ui import reply
from bot.services import queue_svc


class QueueCog(commands.GroupCog, name="queue"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(description="Show a custom's queue status.")
    async def status(self, itx: discord.Interaction, custom_id: int):
        q = await queue_svc.queue_for_custom(custom_id)
        if not q:
            return await reply(itx, "No queue for that custom.")
        ids = await queue_svc.members(q.queue_id)
        body = "\n".join(f"• <@{u}>" for u in ids) or "_empty_"
        await reply(itx, f"**Queue for Custom #{custom_id}** ({len(ids)}/{q.size})\n{body}")


async def setup(bot: commands.Bot):
    await bot.add_cog(QueueCog(bot))
