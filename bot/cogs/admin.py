"""/admin role + audit management."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import select

from bot.core import audit
from bot.core.permissions import grant_role, is_superadmin, require, revoke_role
from bot.core.ui import reply
from bot.db import SessionLocal
from bot.db.models import AuditLog
from bot.i18n import t
from bot.i18n.translator import L
from bot.services import bans as bans_svc, guild_svc

GRANTABLE = ["admin", "superadmin", "player"]
_ROLE_CHOICES = [
    app_commands.Choice(name=L(f"role.{r}"), value=r) for r in GRANTABLE
]


class AdminCog(commands.GroupCog, name="admin"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(description=L("cmd.admin.grant.desc"))
    @app_commands.choices(role=_ROLE_CHOICES)
    async def grant(
        self, itx: discord.Interaction, member: discord.Member, role: app_commands.Choice[str]
    ):
        if not await is_superadmin(itx.user):
            return await reply(itx, t("error.superadmin_only"))
        granted = await grant_role(itx.guild_id, member.id, role.value, itx.user.id)
        await reply(itx, t("roles.granted" if granted else "roles.already_granted",
                           role=t(f"role.{role.value}"), member=member.mention))

    @app_commands.command(description=L("cmd.admin.revoke.desc"))
    @app_commands.choices(role=_ROLE_CHOICES)
    async def revoke(
        self, itx: discord.Interaction, member: discord.Member, role: app_commands.Choice[str]
    ):
        if not await is_superadmin(itx.user):
            return await reply(itx, t("error.superadmin_only"))
        revoked = await revoke_role(itx.guild_id, member.id, role.value, itx.user.id)
        await reply(itx, t("roles.revoked" if revoked else "roles.not_granted",
                           role=t(f"role.{role.value}"), member=member.mention))

    @app_commands.command(description=L("cmd.admin.audit.desc"))
    @require("admin")
    async def audit(self, itx: discord.Interaction, limit: app_commands.Range[int, 1, 25] = 10):
        async with SessionLocal() as s:
            rows = await s.execute(
                select(AuditLog)
                .where(AuditLog.guild_id == itx.guild_id)
                .order_by(AuditLog.id.desc())
                .limit(limit)
            )
            entries = [r[0] for r in rows.all()]
        if not entries:
            return await reply(itx, t("audit.none"))
        lines = [
            t("audit.line", ts=f"{e.ts:%m-%d %H:%M}", actor=f"<@{e.actor_id}>",
              action=e.action, target=e.target or "")
            for e in entries
        ]
        await reply(itx, "\n".join(lines))

    @app_commands.command(description=L("cmd.admin.ban.desc"))
    @require("admin")
    async def ban(self, itx: discord.Interaction, member: discord.Member, reason: str | None = None):
        created = await bans_svc.ban(itx.guild_id, member.id, itx.user.id, reason)
        await audit.log(itx.guild_id, itx.user.id, "ban", str(member.id), reason=reason or "")
        msg = t("bans.banned" if created else "bans.already_banned", member=member.mention)
        if reason:
            msg += t("bans.reason_suffix", reason=reason)
        await reply(itx, msg)

    @app_commands.command(description=L("cmd.admin.unban.desc"))
    @require("admin")
    async def unban(self, itx: discord.Interaction, member: discord.Member):
        removed = await bans_svc.unban(itx.guild_id, member.id)
        await audit.log(itx.guild_id, itx.user.id, "unban", str(member.id))
        await reply(itx, t("bans.unbanned" if removed else "bans.not_banned",
                           member=member.mention))

    @app_commands.command(description=L("cmd.admin.bans.desc"))
    @require("admin")
    async def bans(self, itx: discord.Interaction):
        rows = await bans_svc.list_bans(itx.guild_id)
        if not rows:
            return await reply(itx, t("bans.none"))
        lines = [f"\u2022 <@{b.user_id}>" + (f" \u2014 {b.reason}" if b.reason else "")
                 for b in rows]
        await reply(itx, "\n".join(lines))

    @app_commands.command(description=L("cmd.admin.notify_role.desc"))
    @app_commands.describe(role=L("cmd.admin.notify_role.param"))
    @require("admin")
    async def notify_role(self, itx: discord.Interaction, role: discord.Role | None = None):
        await guild_svc.set_notify_role(itx.guild_id, role.id if role else None)
        if role:
            await reply(itx, t("admin.notify_role.set", role=role.mention))
        else:
            await reply(itx, t("admin.notify_role.cleared"))


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))
