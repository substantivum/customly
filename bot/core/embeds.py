"""Embed factories."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import discord

from bot.db.models import Custom

VAL_RED = discord.Color.from_str("#ff4655")


def as_utc(dt: datetime) -> datetime:
    """SQLite returns naive datetimes; treat stored values as UTC so the
    Discord timestamp resolves to the right instant regardless of host TZ."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def ts(dt: datetime, style: str = "F") -> str:
    """Render a Discord timestamp (`<t:epoch:style>`) — localizes per viewer.
    Styles: t short time, T long time, d date, D long date, f/F datetime, R relative."""
    return discord.utils.format_dt(as_utc(dt), style=style)


def custom_registration_embed(custom: Custom, registered: list[int], size: int) -> discord.Embed:
    pool = ", ".join(json.loads(custom.map_pool))
    start = as_utc(custom.start_time)
    end = start + timedelta(hours=custom.duration_h)
    e = discord.Embed(
        title=f"🎮 Custom #{custom.custom_id} — {custom.name}",
        description=(
            f"**Format:** {custom.format}  ·  **{custom.team_size}v{custom.team_size}**\n"
            f"**Starts:** {ts(start, 'F')}  ({ts(start, 'R')})\n"
            f"**Block:** {ts(start, 't')} – {ts(end, 't')}\n"
            f"**Map pool:** {pool}"
        ),
        color=VAL_RED,
    )
    names = "\n".join(f"• <@{u}>" for u in registered) or "_no one yet_"
    e.add_field(name=f"Registered ({len(registered)}/{size})", value=names, inline=False)
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
