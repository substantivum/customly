"""Embed factories."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import discord

from bot.db.models import Custom
from bot.i18n import t
from bot.services.draft import captain_label, draft_mode_label
from bot.services.games import game_label, has_veto

# The bot's neutral brand colour, worn by everything that isn't about one
# specific game: the tier boards, and all server/staff chrome (roles, language,
# bans, audit). A single game's custom or match wears its game colour instead
# (see game_color), which is what makes the three games legible at a glance.
EMBED_COLOR = discord.Color.from_str("#BF3100")

# Per-game accent. Any embed about a single game's custom or match is coloured
# from here; a board that mixes games keeps EMBED_COLOR and marks each row with
# game_mark() instead, since an embed has only the one accent bar.
GAME_COLORS = {
    "valorant": "#FF4655",
    "cs2": "#F2A93B",
    "dota2": "#C1440E",
}

# A colour-coded square that carries the game into a plain-text line — a board
# row, an embed title — where the accent bar can't reach. Indicator only, in the
# same spirit as the state dots.
GAME_MARK = {
    "valorant": "🟥",
    "cs2": "🟨",
    "dota2": "🟧",
}

# The run-of-match phases, in order. Dota 2 has no veto (see games.has_veto), so
# its ribbon drops that node.
FLOW_PHASES = ("coin", "draft", "veto", "live")
_PHASE_DONE, _PHASE_NOW, _PHASE_TODO = "🟢", "🔵", "⚪"

# Not a translatable string — a typographic placeholder for "no value".
DASH = "—"


def game_color(game: str | None) -> discord.Color:
    """The accent for a single-game embed; the neutral brand colour otherwise."""
    hexv = GAME_COLORS.get(game or "")
    return discord.Color.from_str(hexv) if hexv else EMBED_COLOR


def game_mark(game: str | None) -> str:
    """A game's indicator square, or empty for an unknown game."""
    return GAME_MARK.get(game or "", "")


def phase_ribbon(current: str, *, has_veto: bool = True) -> str:
    """`Coin ▸ Draft ▸ Veto ▸ Live` with the current step marked and named.

    Reads the same in every language: the labels come from the catalog, the
    dots don't. Steps before `current` are done, the rest are pending.
    """
    phases = [p for p in FLOW_PHASES if p != "veto" or has_veto]
    if current not in phases:
        current = phases[-1]
    here = phases.index(current)
    out = []
    for i, p in enumerate(phases):
        label = t(f"flow.{p}")
        if i < here:
            out.append(f"{_PHASE_DONE} {label}")
        elif i == here:
            out.append(f"{_PHASE_NOW} **{label}**")
        else:
            out.append(f"{_PHASE_TODO} {label}")
    return " ▸ ".join(out)


def flow_header(
    e: discord.Embed, game: str, match_id: int, phase: str, *,
    fmt: str | None = None,
) -> discord.Embed:
    """Stamp a run-of-match embed with its context line and phase ribbon.

    The author line ("Match #12 · Valorant · BO3") and the ribbon are the two
    things every phase shares, so a player always knows which game, which match
    and how far along it is."""
    ctx = f"{game_mark(game)} Match #{match_id} · {game_label(game)}"
    if fmt:
        ctx += f" · {fmt}"
    e.set_author(name=ctx)
    e.add_field(
        name=t("flow.phase"),
        value=phase_ribbon(phase, has_veto=has_veto(game)),
        inline=False,
    )
    return e


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
    start = as_utc(custom.start_time)
    end = start + timedelta(hours=custom.duration_h)
    game = getattr(custom, "game", "valorant") or "valorant"
    body_kwargs = dict(
        game=game_label(game),
        fmt=custom.format,
        size=custom.team_size,
        start=start_line(custom),
        from_time=ts(start, "t"),
        to_time=ts(end, "t"),
        draft=draft_mode_label(custom.draft_mode or "snake"),
        captains=captain_label(custom.captain_method or "random"),
    )
    if has_veto(game):
        body = t("custom.reg.body", pool=", ".join(json.loads(custom.map_pool)), **body_kwargs)
    else:
        body = t("custom.reg.body_no_maps", **body_kwargs)
    e = discord.Embed(
        title=f"{game_mark(game)} "
              + t("custom.reg.title", custom_id=custom.custom_id, name=custom.name),
        description=body,
        color=game_color(game),
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
