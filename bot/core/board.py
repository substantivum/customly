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
from bot.core.embeds import DASH, EMBED_COLOR, member_name, start_text
from bot.db import SessionLocal
from bot.db.models import Ban, Custom, MemberRole
from bot.i18n import LANG_NAME, t, use_lang
from bot.services import custom as custom_svc
from bot.services import guild_svc
from bot.services import maps as maps_svc
from bot.services import panel_svc

log = logging.getLogger("valbot.board")

SHOW_MAX = 8           # customs listed on a board before it says "…and N more"
COALESCE_SECONDS = 1.5  # burst window: many joins in a row cost one edit

# The one place pictographs survive: a coloured dot per lifecycle state is what
# makes a board scannable, and it reads the same in every language.
STATE_DOT = {
    "registration": "🟢",
    "full": "🟡",
    "ready": "🔵",
    "veto": "🟠",
    "live": "🔴",
    "done": "⚫",
}
FALLBACK_DOT = "⚪"

# Configured / not configured, in the superadmin config summary.
OK_MARK, WARN_MARK = "✅", "⚠️"


def state_dot(state: str) -> str:
    return STATE_DOT.get(state, FALLBACK_DOT)


def state_name(state: str) -> str:
    """A lifecycle state as a player reads it."""
    return t(f"state.{state}") if state in STATE_DOT else state


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


async def custom_line(
    c: Custom, *, with_owner: bool = False, guild: discord.Guild | None = None
) -> str:
    """One custom as a single readable line on a board."""
    taken, size, waiting = await seats(c)
    bits = [
        f"{state_dot(c.state)} **#{c.custom_id} · {c.name}**",
        t("board.line.seats", fmt=c.format, size=c.team_size, taken=taken, total=size)
        + (t("board.line.waiting", n=waiting) if waiting else ""),
        (start_text(c) if c.start_asap
         else t("board.line.starts", when=start_text(c, "R")))
        + f" · `{state_name(c.state)}`",
    ]
    if with_owner:
        bits.append(t("board.line.owner", owner=member_name(guild, c.owner_id)))
    return bits[0] + "\n " + " · ".join(bits[1:])


async def customs_field(
    customs: list[Custom], *, with_owner: bool = False, guild: discord.Guild | None = None
) -> str:
    if not customs:
        return t("board.nothing_running")
    lines = [
        await custom_line(c, with_owner=with_owner, guild=guild) for c in customs[:SHOW_MAX]
    ]
    if len(customs) > SHOW_MAX:
        lines.append(t("board.and_more", n=len(customs) - SHOW_MAX))
    return "\n".join(lines)


# ------------------------------------------------------------------- embeds ---
def _stamp(e: discord.Embed, note: str) -> discord.Embed:
    e.timestamp = datetime.now(timezone.utc)
    e.set_footer(text=note)
    return e


async def player_embed(guild: discord.Guild) -> discord.Embed:
    customs = await active_customs(guild.id)
    e = discord.Embed(
        title=t("board.player.title"),
        description=t("board.player.desc"),
        color=EMBED_COLOR,
    )
    e.add_field(
        name=t("board.open_games", n=len(customs)),
        value=await customs_field(customs, guild=guild),
        inline=False,
    )
    return _stamp(e, t("board.footer.player"))


async def admin_embed(guild: discord.Guild) -> discord.Embed:
    customs = await active_customs(guild.id)
    all_maps = await maps_svc.all_maps(guild.id)
    enabled = [m.name for m in all_maps if m.enabled]
    competitive = [m.name for m in all_maps if m.competitive and m.enabled]
    e = discord.Embed(
        title=t("board.admin.title"),
        description=t("board.admin.desc"),
        color=EMBED_COLOR,
    )
    e.add_field(
        name=t("board.active_customs", n=len(customs)),
        value=await customs_field(customs, with_owner=True, guild=guild),
        inline=False,
    )
    e.add_field(
        name=t("board.map_pool"),
        value=(t("board.map_pool_count", enabled=len(enabled), total=len(all_maps))
               if all_maps else t("board.map_pool_unseeded")),
        inline=True,
    )
    e.add_field(
        name=t("board.competitive"),
        value=", ".join(competitive) if competitive else DASH,
        inline=True,
    )
    return _stamp(e, t("board.footer.staff"))


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
    parts += [member_name(guild, u) for u in granted[:10]]
    if len(granted) > 10:
        parts.append(t("board.more_granted", n=len(granted) - 10))
    return ", ".join(parts) if parts else DASH


async def super_embed(guild: discord.Guild) -> discord.Embed:
    customs = await active_customs(guild.id)
    admins, supers = await _staff(guild)
    async with SessionLocal() as s:
        bans = len((await s.execute(select(Ban.user_id).where(Ban.guild_id == guild.id))).all())
    by_state: dict[str, int] = {}
    for c in customs:
        by_state[c.state] = by_state.get(c.state, 0) + 1

    e = discord.Embed(
        title=t("board.super.title"),
        description=t("board.super.desc"),
        color=EMBED_COLOR,
    )
    e.add_field(
        name=t("board.customs_active", n=len(customs)),
        value=" · ".join(f"{state_dot(k)} {state_name(k)} **{v}**"
                         for k, v in sorted(by_state.items())) or t("board.none_active"),
        inline=False,
    )
    e.add_field(name=t("board.admins"), value=_role_line(guild, settings.admin_role, admins),
                inline=False)
    e.add_field(name=t("board.superadmins"),
                value=_role_line(guild, settings.superadmin_role, supers), inline=False)
    e.add_field(name=t("board.banned"), value=str(bans), inline=True)
    e.add_field(name=t("board.config"), value=_config_summary(), inline=True)
    e.add_field(
        name=t("board.language"),
        value=LANG_NAME.get(await guild_svc.get_lang(guild.id), "?"),
        inline=True,
    )
    return _stamp(e, t("board.footer.staff"))


def _config_summary() -> str:
    def mark(value: int | None, label_key: str) -> str:
        return f"{OK_MARK if value else WARN_MARK} {t(label_key)}"

    return "\n".join([
        mark(settings.customs_category_id, "board.cfg.category"),
        mark(settings.custom_config_channel, "board.cfg.config_channel"),
        mark(settings.admin_panel_channel, "board.cfg.admin_channel"),
        mark(settings.superadmin_panel_channel, "board.cfg.super_channel"),
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
    gone are forgotten rather than retried forever.

    Both the embed *and* the components are rewritten: button labels are part of
    the message, so a language change would otherwise leave a Russian board
    wearing English buttons until someone re-ran `/panel`."""
    from bot.cogs.panel import BOARD_VIEW

    async with use_lang(guild.id):
        for b in await panel_svc.boards(guild.id):
            channel = guild.get_channel(b.channel_id)
            if not isinstance(channel, discord.abc.Messageable):
                await panel_svc.forget(guild.id, b.tier)
                continue
            try:
                msg = await channel.fetch_message(b.message_id)
                view = BOARD_VIEW[b.tier]()
                await msg.edit(embed=await embed_for(guild, b.tier), view=view)
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
