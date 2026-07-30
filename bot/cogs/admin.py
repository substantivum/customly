"""/admin role + audit management."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import select

from bot.core import audit
from bot.core.permissions import is_superadmin, require
from bot.core.ui import reply
from bot.db import SessionLocal
from bot.db.models import AuditLog, MemberRole
from bot.services import bans as bans_svc

GRANTABLE = ["admin", "superadmin", "player"]


class AdminCog(commands.GroupCog, name="admin"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(description="Grant a bot role (superadmin only for admin/superadmin).")
    @app_commands.choices(role=[app_commands.Choice(name=r, value=r) for r in GRANTABLE])
    async def grant(
        self, itx: discord.Interaction, member: discord.Member, role: app_commands.Choice[str]
    ):
        if not await is_superadmin(itx.user):
            return await reply(itx, "Superadmin only.")
        async with SessionLocal() as s:
            if not await s.get(MemberRole, (itx.guild_id, member.id, role.value)):
                s.add(MemberRole(guild_id=itx.guild_id, user_id=member.id, role=role.value))
                await s.commit()
        await reply(itx, f"Granted **{role.value}** to {member.mention}.")

    @app_commands.command(description="Revoke a bot role.")
    @app_commands.choices(role=[app_commands.Choice(name=r, value=r) for r in GRANTABLE])
    async def revoke(
        self, itx: discord.Interaction, member: discord.Member, role: app_commands.Choice[str]
    ):
        if not await is_superadmin(itx.user):
            return await reply(itx, "Superadmin only.")
        async with SessionLocal() as s:
            mr = await s.get(MemberRole, (itx.guild_id, member.id, role.value))
            if mr:
                await s.delete(mr)
                await s.commit()
        await reply(itx, f"Revoked **{role.value}** from {member.mention}.")

    @app_commands.command(description="View recent audit log entries.")
    @require("admin")
    async def audit(self, itx: discord.Interaction, limit: int = 10):
        async with SessionLocal() as s:
            rows = await s.execute(
                select(AuditLog)
                .where(AuditLog.guild_id == itx.guild_id)
                .order_by(AuditLog.id.desc())
                .limit(min(limit, 25))
            )
            entries = [r[0] for r in rows.all()]
        if not entries:
            return await reply(itx, "No audit entries.")
        lines = [
            f"`{e.ts:%m-%d %H:%M}` <@{e.actor_id}> **{e.action}** {e.target or ''}"
            for e in entries
        ]
        await reply(itx, "\n".join(lines))

    @app_commands.command(description="Ban a player from joining future games.")
    @require("admin")
    async def ban(self, itx: discord.Interaction, member: discord.Member, reason: str | None = None):
        created = await bans_svc.ban(itx.guild_id, member.id, itx.user.id, reason)
        await audit.log(itx.guild_id, itx.user.id, "ban", str(member.id), reason=reason or "")
        await reply(itx, f"{'Banned' if created else 'Already banned'} {member.mention}."
                         + (f"\nReason: {reason}" if reason else ""))

    @app_commands.command(description="Unban a player.")
    @require("admin")
    async def unban(self, itx: discord.Interaction, member: discord.Member):
        removed = await bans_svc.unban(itx.guild_id, member.id)
        await audit.log(itx.guild_id, itx.user.id, "unban", str(member.id))
        await reply(itx, f"{'Unbanned' if removed else 'Was not banned'} {member.mention}.")

    @app_commands.command(description="List banned players.")
    @require("admin")
    async def bans(self, itx: discord.Interaction):
        rows = await bans_svc.list_bans(itx.guild_id)
        if not rows:
            return await reply(itx, "No banned players.")
        lines = [f"• <@{b.user_id}>" + (f" — {b.reason}" if b.reason else "") for b in rows]
        await reply(itx, "\n".join(lines))


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))
