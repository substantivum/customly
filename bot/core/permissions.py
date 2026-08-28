"""Role-based and ownership-based permission checks.

A member's effective level is the highest of three sources:
  1. Discord guild owner / `administrator` permission  → superadmin
  2. A configured Discord role (ADMIN_ROLE / SUPERADMIN_ROLE in .env)
  3. Bot roles granted in the DB (`member_roles`, via /admin grant or the panel)
"""
from __future__ import annotations

from typing import Callable

import discord
from discord import app_commands
from sqlalchemy import select

from bot.config import settings
from bot.core import audit
from bot.core.errors import PermissionDenied
from bot.db import SessionLocal
from bot.db.models import Custom, MemberRole
from bot.i18n import t

PLAYER, ADMIN, SUPER = 0, 1, 2
ROLE_RANK = {"player": PLAYER, "admin": ADMIN, "superadmin": SUPER}
# Catalog keys, not finished text: a rank only has a name once the reader's
# language is known.
RANK_KEY = {PLAYER: "rank.player", ADMIN: "rank.admin", SUPER: "rank.superadmin"}


async def get_roles(guild_id: int, user_id: int) -> set[str]:
    async with SessionLocal() as s:
        rows = await s.execute(
            select(MemberRole.role).where(
                MemberRole.guild_id == guild_id, MemberRole.user_id == user_id
            )
        )
        return {r[0] for r in rows.all()}


async def db_level(guild_id: int, user_id: int) -> int:
    """Highest bot role granted in the DB."""
    roles = await get_roles(guild_id, user_id)
    return max((ROLE_RANK.get(r, PLAYER) for r in roles), default=PLAYER)


def discord_role_level(member: discord.Member) -> int:
    """Level implied by the Discord roles configured in .env."""
    role_ids = {r.id for r in getattr(member, "roles", [])}
    if settings.superadmin_role and settings.superadmin_role in role_ids:
        return SUPER
    if settings.admin_role and settings.admin_role in role_ids:
        return ADMIN
    return PLAYER


async def member_level(user: discord.Member | discord.User) -> int:
    """Effective level of a member in their guild. Non-members are players."""
    if not isinstance(user, discord.Member):
        return PLAYER
    if user.guild.owner_id == user.id or user.guild_permissions.administrator:
        return SUPER
    return max(
        discord_role_level(user),
        await db_level(user.guild.id, user.id),
    )


async def is_superadmin(user: discord.Member | discord.User) -> bool:
    return await member_level(user) >= SUPER


async def is_admin(user: discord.Member | discord.User) -> bool:
    return await member_level(user) >= ADMIN


async def grant_role(guild_id: int, user_id: int, role: str, actor_id: int) -> bool:
    """Grant a bot `role` to a member, auditing the change. Returns False (no-op,
    not audited) if they already had it."""
    key = (guild_id, user_id, role)
    async with SessionLocal() as s:
        if await s.get(MemberRole, key):
            return False
        s.add(MemberRole(guild_id=guild_id, user_id=user_id, role=role))
        await s.commit()
    await audit.log(guild_id, actor_id, "grant", str(user_id), role=role)
    return True


async def revoke_role(guild_id: int, user_id: int, role: str, actor_id: int) -> bool:
    """Revoke a bot `role` from a member, auditing the change. Returns False
    (no-op, not audited) if they didn't have it."""
    key = (guild_id, user_id, role)
    async with SessionLocal() as s:
        row = await s.get(MemberRole, key)
        if not row:
            return False
        await s.delete(row)
        await s.commit()
    await audit.log(guild_id, actor_id, "revoke", str(user_id), role=role)
    return True


async def can_manage_custom(custom: Custom, member: discord.Member) -> bool:
    """Owner of the custom, or a superadmin **of the custom's own guild**."""
    if not isinstance(member, discord.Member) or custom.guild_id != member.guild.id:
        return False
    if await is_superadmin(member):
        return True
    return member.id == custom.owner_id


def require(role: str) -> Callable:
    """app_commands check: enforce a minimum bot role.

    Implemented as a check (not a wrapper) so the command callback keeps its
    own module globals — important for annotation resolution under
    `from __future__ import annotations`.
    """
    want = ROLE_RANK[role]

    async def predicate(itx: discord.Interaction) -> bool:
        if await member_level(itx.user) >= want:
            return True
        raise PermissionDenied(t("error.need_role_cmd", role=t(f"rank.{role}")))

    # Exposed so a command's real gate can be introspected (see
    # tests/test_help_permissions.py) rather than trusted to stay in sync with
    # bot.cogs.help._SECTIONS by convention alone.
    predicate.min_level = want
    return app_commands.check(predicate)


def in_channel(*channel_ids: int) -> Callable:
    """app_commands check: restrict a command to specific channel id(s)."""

    async def predicate(itx: discord.Interaction) -> bool:
        if channel_ids and itx.channel_id not in channel_ids:
            raise PermissionDenied(t("error.config_channel"))
        return True

    return app_commands.check(predicate)
