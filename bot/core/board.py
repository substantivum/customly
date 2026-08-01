"""Live control-board embeds and the machinery that keeps them current.

A board is a public, persistent message whose *embed* mirrors the server state —
which customs are open, how many seats are left, what the map pool is. The
buttons on it never mutate the board itself; they open a private navigator (see
`bot.core.nav`), so several people can use one board at once without stepping on
each other.

`schedule()` is the hook the rest of the bot calls after anything that changes
what a board shows. It coalesces bursts (ten people joining at once is one edit)
and never raises into its caller — a board that can't be redrawn is cosmetic.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import discord
from sqlalchemy import select

from bot.config import settings
from bot.core.embeds import VAL_RED, ts
from bot.db import SessionLocal
from bot.db.models import Ban, Custom, MemberRole
from bot.services import custom as custom_svc
from bot.services import maps as maps_svc
from bot.services import panel_svc

log = logging.getLogger("valbot.board")

SHOW_MAX = 8           # customs listed on a board before it says "…and N more"
COALESCE_SECONDS = 1.5  # burst window: many joins in a row cost one edit

STATE_EMOJI = {
    "registration": "🟢",
    "full": "🟡",
    "ready": "🔔",
    "veto": "🗺",
    "live": "🔴",
    "done": "⚫",
}


# ------------------------------------------------------------------ queries ---
async def active_customs(guild_id: int, owned_by: int | None = None) -> list[Custom]:
    """Customs still in play, soonest first."""
    async with SessionLocal() as s:
        q = select(Custom).where(
            Custom.guild_id == guild_id,
            Custom.state.in_(custom_svc.ACTIVE_STATES),
        )
        if owned_by is not None:
            q = q.where(Custom.owner_id == owned_by)
        rows = await s.execute(q.order_by(Custom.start_time))
        return [r[0] for r in rows.all()]


async def seats(custom: Custom) -> tuple[int, int, int]:
    """(taken, size, waitlisted) for one custom."""
    r = await custom_svc.roster(custom.custom_id)
    return len(r.starters), r.size or custom.team_size * 2, len(r.waitlist)


async def custom_line(c: Custom, *, with_owner: bool = False) -> str:
    """One custom as a single readable line on a board."""
    taken, size, waiting = await seats(c)
    bits = [
        f"{STATE_EMOJI.get(c.state, '•')} **#{c.custom_id} · {c.name}**",
        f"{c.format} · {c.team_size}v{c.team_size} · **{taken}/{size}** seats"
        + (f" (+{waiting} 🪑)" if waiting else ""),
        f"starts {ts(c.start_time, 'R')} · `{c.state}`",
    ]
    if with_owner:
        bits.append(f"owner <@{c.owner_id}>")
    return bits[0] + "\n " + " · ".join(bits[1:])


async def customs_field(customs: list[Custom], *, with_owner: bool = False) -> str:
    if not customs:
        return "_Nothing running right now._"
    lines = [await custom_line(c, with_owner=with_owner) for c in customs[:SHOW_MAX]]
    if len(customs) > SHOW_MAX:
        lines.append(f"_…and {len(customs) - SHOW_MAX} more._")
    return "\n".join(lines)


# ------------------------------------------------------------------- embeds ---
def _stamp(e: discord.Embed, note: str) -> discord.Embed:
    e.timestamp = datetime.now(timezone.utc)
    e.set_footer(text=note)
    return e


async def player_embed(guild: discord.Guild) -> discord.Embed:
    customs = await active_customs(guild.id)
    e = discord.Embed(
        title="🎮 Customs",
        description=(
            "Every open game is listed below. Hit **Browse & join** to open your "
            "own private menu — pick a game, register or leave, check the roster."
        ),
        color=VAL_RED,
    )
    e.add_field(
        name=f"Open games ({len(customs)})",
        value=await customs_field(customs),
        inline=False,
    )
    return _stamp(e, "Updates itself · your menu is private to you")


async def admin_embed(guild: discord.Guild) -> discord.Embed:
    customs = await active_customs(guild.id)
    all_maps = await maps_svc.all_maps(guild.id)
    enabled = [m.name for m in all_maps if m.enabled]
    competitive = [m.name for m in all_maps if m.competitive and m.enabled]
    e = discord.Embed(
        title="🛡 Admin Panel",
        description="Create and run customs. Every button opens a private menu.",
        color=VAL_RED,
    )
    e.add_field(
        name=f"Active customs ({len(customs)})",
        value=await customs_field(customs, with_owner=True),
        inline=False,
    )
    e.add_field(
        name="🗺 Map pool",
        value=(f"**{len(enabled)}/{len(all_maps)}** enabled"
               if all_maps else "_Not seeded — use **Maps → Seed defaults**._"),
        inline=True,
    )
    e.add_field(
        name="⭐ Competitive pool",
        value=", ".join(competitive) if competitive else "_not set_",
        inline=True,
    )
    return _stamp(e, "Updates itself when a custom changes")


async def _staff(guild: discord.Guild) -> tuple[list[int], list[int]]:
    """(admin ids, superadmin ids) granted in the DB for this guild."""
    async with SessionLocal() as s:
        rows = await s.execute(
            select(MemberRole.user_id, MemberRole.role).where(
                MemberRole.guild_id == guild.id,
                MemberRole.role.in_(("admin", "superadmin")),
            )
        )
        admins, supers = [], []
        for uid, role in rows.all():
            (supers if role == "superadmin" else admins).append(uid)
    return admins, supers


def _role_line(guild: discord.Guild, role_id: int | None, granted: list[int]) -> str:
    role = guild.get_role(role_id) if role_id else None
    parts = [role.mention] if role else []
    parts += [f"<@{u}>" for u in granted[:10]]
    if len(granted) > 10:
        parts.append(f"_+{len(granted) - 10} more_")
    return ", ".join(parts) if parts else "_none_"


async def super_embed(guild: discord.Guild) -> discord.Embed:
    customs = await active_customs(guild.id)
    admins, supers = await _staff(guild)
    async with SessionLocal() as s:
        bans = len((await s.execute(select(Ban.user_id).where(Ban.guild_id == guild.id))).all())
    by_state: dict[str, int] = {}
    for c in customs:
        by_state[c.state] = by_state.get(c.state, 0) + 1

    e = discord.Embed(
        title="👑 Super Admin",
        description="Server-wide controls. Every button opens a private menu.",
        color=VAL_RED,
    )
    e.add_field(
        name=f"Customs ({len(customs)} active)",
        value=" · ".join(f"{STATE_EMOJI.get(k, '•')} {k} **{v}**"
                         for k, v in sorted(by_state.items())) or "_none active_",
        inline=False,
    )
    e.add_field(name="🛡 Admins", value=_role_line(guild, settings.admin_role, admins),
                inline=False)
    e.add_field(name="👑 Superadmins",
                value=_role_line(guild, settings.superadmin_role, supers), inline=False)
    e.add_field(name="🔨 Banned players", value=str(bans), inline=True)
    e.add_field(name="⚙️ Config", value=_config_summary(guild), inline=True)
    return _stamp(e, "Updates itself when a custom changes")


def _config_summary(guild: discord.Guild) -> str:
    def mark(value: int | None, label: str) -> str:
        return f"{'✅' if value else '⚠️'} {label}"

    return "\n".join([
        mark(settings.customs_category_id, "customs category"),
        mark(settings.custom_config_channel, "config channel"),
        mark(settings.admin_panel_channel, "admin channel"),
        mark(settings.superadmin_panel_channel, "superadmin channel"),
    ])


EMBED_FOR = {
    "player": player_embed,
    "admin": admin_embed,
    "superadmin": super_embed,
}


async def embed_for(guild: discord.Guild, tier: str) -> discord.Embed:
    return await EMBED_FOR[tier](guild)


# ------------------------------------------------------------------ refresh ---
async def refresh(guild: discord.Guild) -> None:
    """Redraw every board registered for this guild. Boards whose message is
    gone are forgotten rather than retried forever."""
    for b in await panel_svc.boards(guild.id):
        channel = guild.get_channel(b.channel_id)
        if not isinstance(channel, discord.abc.Messageable):
            await panel_svc.forget(guild.id, b.tier)
            continue
        try:
            msg = await channel.fetch_message(b.message_id)
            # Edit the embed only: the buttons on the message are persistent and
            # stay bound to the view registered at startup.
            await msg.edit(embed=await embed_for(guild, b.tier))
        except discord.NotFound:
            await panel_svc.forget(guild.id, b.tier)
        except discord.HTTPException as e:
            log.debug("board refresh failed (%s/%s): %s", guild.id, b.tier, e)


_pending: dict[int, asyncio.Task] = {}


def schedule(guild: discord.Guild | None) -> None:
    """Fire-and-forget board refresh, coalesced per guild.

    Called from the flow (create/join/leave/start/end/delete), where the caller
    is busy answering an interaction and must not wait on — or be broken by — a
    board redraw."""
    if guild is None or guild.id in _pending:
        return

    async def _run() -> None:
        try:
            await asyncio.sleep(COALESCE_SECONDS)
            await refresh(guild)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - a stale board must never break a flow
            log.exception("board refresh crashed for guild %s", guild.id)
        finally:
            _pending.pop(guild.id, None)

    _pending[guild.id] = asyncio.create_task(_run())
