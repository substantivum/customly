"""/custom command group (thin; orchestration in core.actions)."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import select

from bot.config import settings
from bot.core import actions, audit, board
from bot.core.errors import BotError, PermissionDenied
from bot.core.permissions import can_manage_custom, is_superadmin, require
from bot.core.ui import reply
from bot.db import SessionLocal
from bot.db.models import Custom
from bot.services import custom as custom_svc
from bot.services import draft as draft_svc


class CustomCog(commands.GroupCog, name="custom"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(description="Create a custom (admin, in the config channel).")
    @require("admin")
    @app_commands.describe(
        name="Custom name", format="BO1/BO3/BO5",
        start="HH:MM (server time) or ISO — omit to start ASAP",
        maps="Comma-separated pool, or `competitive` for the current competitive "
             "pool (optional — defaults to all enabled maps)",
        team_size="Players per side: 1 (1v1) … 5 (5v5). Default 5.",
        draft="How players are drafted: snake, or one by one. Default snake.",
        captains="How captains are chosen when this custom starts. Default random.",
    )
    @app_commands.choices(
        draft=[
            app_commands.Choice(name="Snake (A, BB, AA, …)", value="snake"),
            app_commands.Choice(name="One by one (A, B, A, B, …)", value="alternate"),
        ],
        captains=[
            app_commands.Choice(name=draft_svc.CAPTAIN_METHOD_LABEL[m], value=m)
            for m in draft_svc.CREATE_METHODS
        ],
    )
    async def create(
        self, itx: discord.Interaction, name: str, format: str,
        start: str = "",
        maps: str = "",
        team_size: app_commands.Range[int, 1, 5] = 5,
        draft: app_commands.Choice[str] | None = None,
        captains: app_commands.Choice[str] | None = None,
    ):
        if settings.custom_config_channel and itx.channel_id != settings.custom_config_channel:
            raise PermissionDenied("Use the dedicated #custom-config channel.")
        # Channel creation + embed post exceed the 3s interaction window.
        await itx.response.defer(ephemeral=True)
        c = await actions.create_custom_flow(
            itx, name=name, fmt=format, start_raw=start, maps_csv=maps,
            team_size=team_size, draft_mode=draft.value if draft else "snake",
            captain_method=captains.value if captains else "random",
        )
        reg = itx.guild.get_channel(c.reg_channel)
        await reply(itx, f"Created **Custom #{c.custom_id}** ({c.team_size}v{c.team_size}) → "
                         f"{reg.mention if reg else 'channel'}")

    @app_commands.command(description="Register for a custom by id.")
    async def register(self, itx: discord.Interaction, custom_id: int):
        await reply(itx, await actions.join_custom(itx.guild, custom_id, itx.user.id))

    @app_commands.command(description="Leave a custom by id.")
    async def leave(self, itx: discord.Interaction, custom_id: int):
        await reply(itx, await actions.leave_custom(itx.guild, custom_id, itx.user.id))

    @app_commands.command(description="List active customs.")
    async def list(self, itx: discord.Interaction):
        async with SessionLocal() as s:
            rows = await s.execute(
                select(Custom).where(
                    Custom.guild_id == itx.guild_id,
                    Custom.state.in_(custom_svc.ACTIVE_STATES),
                )
            )
            customs = [r[0] for r in rows.all()]
        if not customs:
            return await reply(itx, "No active customs.")
        lines = [f"**#{c.custom_id}** {c.name} · {c.format} · {c.team_size}v{c.team_size} "
                 f"· owner <@{c.owner_id}> · {c.state}" for c in customs]
        await reply(itx, "\n".join(lines))

    @app_commands.command(description="Transfer ownership of a custom.")
    async def transfer(self, itx: discord.Interaction, custom_id: int, to: discord.Member):
        # Redraws the registration embed and DMs the new owner — more than the
        # 3s an un-acknowledged interaction survives.
        await itx.response.defer(ephemeral=True)
        await actions.transfer_custom(itx, custom_id, to)
        await reply(itx, f"Ownership of Custom #{custom_id} → {to.mention} "
                         f"(they've been notified).")

    @app_commands.command(description="Delete a custom by id (owner/superadmin).")
    @app_commands.describe(force="Superadmin override of the occupancy guard")
    async def delete(self, itx: discord.Interaction, custom_id: int, force: bool = False):
        async with SessionLocal() as s:
            c = await s.get(Custom, custom_id)
        if not c:
            raise BotError("Custom not found.")
        if not await can_manage_custom(c, itx.user):
            raise PermissionDenied("Only the owner or a superadmin can delete this.")
        if force and not await is_superadmin(itx.user):
            raise PermissionDenied("Only superadmin may force.")
        await itx.response.defer(ephemeral=True)
        await actions.cancel_ready_check(custom_id, "🗑 Custom deleted.")
        await custom_svc.delete_custom(custom_id, itx.guild, force=force)
        await audit.log(itx.guild_id, itx.user.id, "custom_delete", str(custom_id), force=force)
        board.schedule(itx.guild)
        await reply(itx, f"Deleted Custom #{custom_id}.")

    @app_commands.command(description="Delete ALL customs (superadmin).")
    @require("superadmin")
    async def prune(self, itx: discord.Interaction, force: bool = False):
        await itx.response.defer(ephemeral=True)
        deleted, skipped = await custom_svc.prune(itx.guild, force=force)
        await audit.log(itx.guild_id, itx.user.id, "custom_prune", meta=str(deleted))
        board.schedule(itx.guild)
        msg = f"Pruned {deleted} custom(s)."
        if skipped:
            msg += f" Skipped (in progress): {', '.join(map(str, skipped))}."
        await reply(itx, msg)


async def setup(bot: commands.Bot):
    await bot.add_cog(CustomCog(bot))
