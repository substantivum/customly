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
    names = "\n".join(f"• <@{u}>" for u in registered[:SHOW_MAX]) or t("custom.reg.no_one")
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
    return e


def lobby_embed(
    custom: Custom,
    team_a: list[int],
    team_b: list[int],
    cap_a: int | None,
    cap_b: int | None,
    maps: list[str],
    party_code: str | None,
    viewer_can_see_code: bool,
) -> discord.Embed:
    e = discord.Embed(
        title=t("lobby.title", custom_id=custom.custom_id), color=EMBED_COLOR
    )
    e.add_field(
        name=t("lobby.team_cap", team=t("common.team_a"),
               captain=f"<@{cap_a}>" if cap_a else DASH),
        value="\n".join(f"<@{u}>" for u in team_a) or DASH,
        inline=True,
    )
    e.add_field(
        name=t("lobby.team_cap", team=t("common.team_b"),
               captain=f"<@{cap_b}>" if cap_b else DASH),
        value="\n".join(f"<@{u}>" for u in team_b) or DASH,
        inline=True,
    )
    e.add_field(name=t("common.maps"), value=", ".join(maps) or t("common.tbd"),
                inline=False)
    code = (party_code or DASH) if viewer_can_see_code else t("common.hidden")
    e.add_field(name=t("lobby.party_code"), value=code, inline=False)
    return e
