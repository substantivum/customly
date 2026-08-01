"""Embed factories."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import discord

from bot.db.models import Custom
from bot.services.draft import CAPTAIN_METHOD_LABEL, DRAFT_MODE_LABEL

VAL_RED = discord.Color.from_str("#ff4655")


def as_utc(dt: datetime) -> datetime:
    """SQLite returns naive datetimes; treat stored values as UTC so the
    Discord timestamp resolves to the right instant regardless of host TZ."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def ts(dt: datetime, style: str = "F") -> str:
    """Render a Discord timestamp (`<t:epoch:style>`) — localizes per viewer.
    Styles: t short time, T long time, d date, D long date, f/F datetime, R relative."""
    return discord.utils.format_dt(as_utc(dt), style=style)


ASAP_LABEL = "🔥 **ASAP**"


def start_text(custom: Custom, style: str = "F") -> str:
    """How a custom's start time reads to a player.

    A custom created without a time carries a real `start_time` (the moment it
    was made, so the overlap rule still works) but should never show a clock —
    it says ASAP, because that's what was actually agreed.
    """
    if getattr(custom, "start_asap", False):
        return ASAP_LABEL
    return ts(custom.start_time, style)


def start_line(custom: Custom) -> str:
    """The fuller form, for a detail embed."""
    if getattr(custom, "start_asap", False):
        return f"{ASAP_LABEL} — as soon as the lobby is ready"
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
    draft = DRAFT_MODE_LABEL.get(custom.draft_mode or "snake", custom.draft_mode)
    method = custom.captain_method or "random"
    e = discord.Embed(
        title=f"🎮 Custom #{custom.custom_id} — {custom.name}",
        description=(
            f"**Format:** {custom.format}  ·  **{custom.team_size}v{custom.team_size}**\n"
            f"**Starts:** {start_line(custom)}\n"
            f"**Block:** {ts(start, 't')} – {ts(end, 't')}\n"
            f"**Map pool:** {pool}\n"
            f"**Draft:** {draft}\n"
            f"**Captains:** {CAPTAIN_METHOD_LABEL.get(method, method)}"
        ),
        color=VAL_RED,
    )
    names = "\n".join(f"• <@{u}>" for u in registered[:SHOW_MAX]) or "_no one yet_"
    e.add_field(name=f"Registered ({len(registered)}/{size})", value=names, inline=False)
    if waitlist:
        queued = "\n".join(f"{i}. <@{u}>" for i, u in enumerate(waitlist[:SHOW_MAX], 1))
        if len(waitlist) > SHOW_MAX:
            queued += f"\n_…and {len(waitlist) - SHOW_MAX} more_"
        e.add_field(
            name=f"🪑 Waitlist ({len(waitlist)})",
            value=queued + "\n_Subs move up automatically when a starter leaves._",
            inline=False,
        )
    e.add_field(name="Owner", value=f"<@{custom.owner_id}>", inline=True)
    e.add_field(name="State", value=custom.state, inline=True)
    e.set_footer(text="Use the buttons below to register or leave.")
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
    e = discord.Embed(title=f"🏟 Match Lobby — Custom #{custom.custom_id}", color=VAL_RED)
    e.add_field(
        name=f"🟥 Team A (cap {f'<@{cap_a}>' if cap_a else '—'})",
        value="\n".join(f"<@{u}>" for u in team_a) or "—",
        inline=True,
    )
    e.add_field(
        name=f"🟦 Team B (cap {f'<@{cap_b}>' if cap_b else '—'})",
        value="\n".join(f"<@{u}>" for u in team_b) or "—",
        inline=True,
    )
    e.add_field(name="Maps", value=", ".join(maps) or "TBD", inline=False)
    code = (party_code or "—") if viewer_can_see_code else "🔒 hidden"
    e.add_field(name="🔑 Party Code", value=code, inline=False)
    return e
