"""/custom command group (thin; orchestration in core.actions)."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from bot.config import settings
from bot.core import actions, audit, board
from bot.core.errors import BotError, PermissionDenied
from bot.core.permissions import can_manage_custom, is_superadmin, require
from bot.core.ui import reply
from bot.db import SessionLocal
from bot.db.models import Custom
from bot.i18n import t
from bot.i18n.translator import L
from bot.services import custom as custom_svc
from bot.services import draft as draft_svc


class CustomCog(commands.GroupCog, name="custom"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(description=L("cmd.custom.create.desc"))
    @require("admin")
    @app_commands.describe(
        name=L("cmd.custom.create.name"), format=L("cmd.custom.create.format"),
        start=L("cmd.custom.create.start"), maps=L("cmd.custom.create.maps"),
        team_size=L("cmd.custom.create.team_size"),
        draft=L("cmd.custom.create.draft"),
        captains=L("cmd.custom.create.captains"),
    )
    @app_commands.choices(
        draft=[
            app_commands.Choice(name=L(key), value=mode)
            for mode, key in draft_svc.DRAFT_MODE_KEY.items()
        ],
        captains=[
            app_commands.Choice(name=L(draft_svc.CAPTAIN_METHOD_KEY[m]), value=m)
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
            raise PermissionDenied(t("error.config_channel"))
        # Channel creation + embed post exceed the 3s interaction window.
        await itx.response.defer(ephemeral=True)
        c = await actions.create_custom_flow(
            itx, name=name, fmt=format, start_raw=start, maps_csv=maps,
            team_size=team_size, draft_mode=draft.value if draft else "snake",
            captain_method=captains.value if captains else "random",
        )
        reg = itx.guild.get_channel(c.reg_channel)
        await reply(itx, t("custom.created", custom_id=c.custom_id, size=c.team_size,
                           channel=reg.mention if reg else t("common.its_channel")))

    @app_commands.command(description=L("cmd.custom.register.desc"))
    async def register(self, itx: discord.Interaction, custom_id: int):
        await reply(itx, await actions.join_custom(itx.guild, custom_id, itx.user.id))

    @app_commands.command(description=L("cmd.custom.leave.desc"))
    async def leave(self, itx: discord.Interaction, custom_id: int):
        await reply(itx, await actions.leave_custom(itx.guild, custom_id, itx.user.id))

    @app_commands.command(description=L("cmd.custom.list.desc"))
    async def list(self, itx: discord.Interaction):
        customs = await custom_svc.list_active(itx.guild_id)
        if not customs:
            return await reply(itx, t("custom.none_active"))
        lines = [
            t("custom.list_line", custom_id=c.custom_id, name=c.name, fmt=c.format,
              size=c.team_size, owner_id=c.owner_id, state=board.state_name(c.state))
            for c in customs
        ]
        await reply(itx, "\n".join(lines))

    @app_commands.command(description=L("cmd.custom.transfer.desc"))
    async def transfer(self, itx: discord.Interaction, custom_id: int, to: discord.Member):
        # Redraws the registration embed and DMs the new owner — more than the
        # 3s an un-acknowledged interaction survives.
        await itx.response.defer(ephemeral=True)
        await actions.transfer_custom(itx, custom_id, to)
        await reply(itx, t("custom.transferred", custom_id=custom_id, member=to.mention))

    @app_commands.command(description=L("cmd.custom.delete.desc"))
    @app_commands.describe(force=L("cmd.custom.delete.force"))
    async def delete(self, itx: discord.Interaction, custom_id: int, force: bool = False):
        async with SessionLocal() as s:
            c = await s.get(Custom, custom_id)
        if not c:
            raise BotError(t("error.custom_not_found"))
        if not await can_manage_custom(c, itx.user):
            raise PermissionDenied(t("error.delete_perm"))
        if force and not await is_superadmin(itx.user):
            raise PermissionDenied(t("error.force_superadmin"))
        await itx.response.defer(ephemeral=True)
        await actions.cancel_ready_check(custom_id, t("ready.cancel.deleted"))
        await custom_svc.delete_custom(custom_id, itx.guild, force=force)
        await audit.log(itx.guild_id, itx.user.id, "custom_delete", str(custom_id), force=force)
        board.schedule(itx.guild)
        await reply(itx, t("custom.deleted", custom_id=custom_id))

    @app_commands.command(description=L("cmd.custom.prune.desc"))
    @require("superadmin")
    async def prune(self, itx: discord.Interaction, force: bool = False):
        await itx.response.defer(ephemeral=True)
        deleted, skipped = await custom_svc.prune(itx.guild, force=force)
        await audit.log(itx.guild_id, itx.user.id, "custom_prune", meta=str(deleted))
        board.schedule(itx.guild)
        msg = t("custom.pruned", n=deleted)
        if skipped:
            msg += t("custom.pruned_skipped", ids=", ".join(map(str, skipped)))
        await reply(itx, msg)


async def setup(bot: commands.Bot):
    await bot.add_cog(CustomCog(bot))
