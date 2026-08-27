"""Embed factories."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import discord

from bot.db.models import Custom
from bot.i18n import t
from bot.services.draft import captain_label, draft_mode_label

# The bot's one accent colour. Muted olive: it holds up as an embed's left bar in
# both Discord themes, where a lighter sand washes out against the dark one.
EMBED_COLOR = discord.Color.from_str("#6B7A4B")

# Not a translatable string — a typographic placeholder for "no value".
DASH = "—"


def as_utc(dt: datetime) -> datetime:
    """SQLite returns naive datetimes; treat stored values as UTC so the
    Discord timestamp resolves to the right instant regardless of host TZ."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def ts(dt: datetime, style: str = "F") -> str:
    """Render a Discord timestamp (`<t:epoch:style>`) — localizes per viewer.
    Styles: t short time, T long time, d date, D long date, f/F datetime, R relative."""
    return discord.utils.format_dt(as_utc(dt), style=style)


def start_text(custom: Custom, style: str = "F") -> str:
    """How a custom's start time reads to a player.

    A custom created without a time carries a real `start_time` (the moment it
    was made, so the overlap rule still works) but should never show a clock —
    it says ASAP, because that's what was actually agreed.
    """
    if getattr(custom, "start_asap", False):
        return t("custom.asap")
    return ts(custom.start_time, style)


def start_line(custom: Custom) -> str:
    """The fuller form, for a detail embed."""
    if getattr(custom, "start_asap", False):
        return t("custom.asap_full")
    return f"{ts(custom.start_time, 'F')}  ({ts(custom.start_time, 'R')})"


def member_name(guild: discord.Guild | None, user_id: int) -> str:
    """A player's name as it renders on this server. Embeds don't parse mention
    syntax, so a raw <@id> shows as literal text — resolve it ourselves."""
    m = guild.get_member(user_id) if guild else None
    return m.display_name if m else f"<@{user_id}>"


SHOW_MAX = 10  # keep an embed field under Discord's 1024-char limit


def custom_registration_embed(
    custom: Custom,
    registered: list[int],
    size: int,
    waitlist: list[int] | None = None,
) -> discord.Embed:
    pool = ", ".join(json.loads(custom.map_pool))
    start = as_utc(custom.start_time)
    end = start + timedelta(hours=custom.duration_h)
    e = discord.Embed(
        title=t("custom.reg.title", custom_id=custom.custom_id, name=custom.name),
        description=t(
            "custom.reg.body",
            fmt=custom.format,
            size=custom.team_size,
            start=start_line(custom),
            from_time=ts(start, "t"),
            to_time=ts(end, "t"),
            pool=pool,
            draft=draft_mode_label(custom.draft_mode or "snake"),
            captains=captain_label(custom.captain_method or "random"),
        ),
        color=EMBED_COLOR,
    )
    names = "\n".join(f"• <@{u}>" for u in registered[:SHOW_MAX]) or DASH
    e.add_field(
        name=t("custom.reg.registered", n=len(registered), size=size),
        value=names,
        inline=False,
    )
    if waitlist:
        queued = "\n".join(f"{i}. <@{u}>" for i, u in enumerate(waitlist[:SHOW_MAX], 1))
        if len(waitlist) > SHOW_MAX:
            queued += t("custom.reg.waitlist_more", n=len(waitlist) - SHOW_MAX)
        e.add_field(
            name=t("custom.reg.waitlist", n=len(waitlist)),
            value=queued + t("custom.reg.waitlist_note"),
            inline=False,
        )
    e.add_field(name=t("common.owner"), value=f"<@{custom.owner_id}>", inline=True)
    e.add_field(name=t("common.state"), value=t(f"state.{custom.state}"), inline=True)
    e.set_footer(text=t("custom.reg.footer"))
    e.timestamp = datetime.now(timezone.utc)
    return e
