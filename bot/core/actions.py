"""Reusable orchestration shared by slash commands and the button panel.

Keeping this here (not in a cog) lets both /custom, /match AND the panel views
call the exact same flows without duplication or circular imports.
"""
from __future__ import annotations

import json
import logging
import asyncio
from datetime import datetime, timedelta, timezone

import discord
from sqlalchemy import select

from bot.config import settings
from bot.core import audit, board
from bot.core.controllers import (
    CoinflipController,
    DraftController,
    ReadyCheckController,
    VetoController,
)
from bot.core.embeds import DASH, EMBED_COLOR, custom_registration_embed, member_name
from bot.core.errors import BotError
from bot.core.naming import channel_slug
from bot.core.permissions import can_manage_custom, is_admin
from bot.core.views import (
    CoinflipView,
    DraftView,
    ReadyCheckView,
    VetoView,
    registration_view,
)
from bot.db import SessionLocal
from bot.db.models import (
    Custom,
    CustomRegistration,
    Match,
    MatchPlayer,
    MatchResult,
    MatchTeam,
    Queue,
    User,
)
from bot.i18n import t
from bot.services import custom as custom_svc
from bot.services import games as games_svc
from bot.services import guild_svc
from bot.services import draft as draft_svc
from bot.services import queue_svc, rank_sync, voice
from bot.services import veto as veto_svc

log = logging.getLogger("customly.flow")

# active veto controllers keyed by match_id
ACTIVE_VETO: dict[int, VetoController] = {}


def flow_step(channel, what: str):
    """Wrap a match-flow hand-off so a failure is visible instead of silent.

    These callbacks run inside view callbacks and timer tasks: an exception in
    one only reaches the log (or, from a timer, is swallowed as an unretrieved
    task result), and the match just stops with nothing said in the channel.
    """
    def wrap(fn):
        async def runner(*args, **kwargs):
            try:
                return await fn(*args, **kwargs)
            except Exception as e:                      # noqa: BLE001 - reported
                log.exception("match flow failed before %s", what)
                try:
                    await channel.send(
                        t("error.flow_step", what=what,
                          error=f"{type(e).__name__}: {e}")
                    )
                except discord.HTTPException:
                    pass
        return runner
    return wrap


# ----------------------------------------------------------- time parsing ---
# Leaving the start time out means "we're playing now" — the common case for a
# custom thrown together on the spot.
ASAP_TOKENS = {"", "asap", "now", "immediately"}


def is_asap(raw: str | None) -> bool:
    return (raw or "").strip().lower() in ASAP_TOKENS


def parse_start(raw: str, tz_offset: int | None = None) -> datetime:
    """`HH:MM` or ISO → a UTC instant. Blank (or `asap`) → right now.

    Times are read in the server's local zone (`TZ_OFFSET` in .env) — Discord
    doesn't expose a user's timezone, so one server-wide offset is the closest
    thing to "just type the time you mean". A bare `HH:MM` that has already
    passed today rolls forward to tomorrow.

    An ASAP custom still gets a real instant (now), so the time-block overlap
    rule keeps working exactly as it does for a scheduled one — only the display
    differs, driven by `Custom.start_asap`.
    """
    raw = (raw or "").strip()
    if is_asap(raw):
        return datetime.now(timezone.utc)
    if tz_offset is None:
        tz_offset = settings.tz_offset
    tz = timezone(timedelta(hours=tz_offset))
    try:
        if len(raw) <= 5 and ":" in raw:
            now_local = datetime.now(tz)
            h, m = map(int, raw.split(":"))
            local = now_local.replace(hour=h, minute=m, second=0, microsecond=0)
            if local <= now_local:
                local += timedelta(days=1)   # "20:00" typed at 21:00 means tomorrow
            return local.astimezone(timezone.utc)
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=tz)
        return dt.astimezone(timezone.utc)
    except ValueError:
        raise BotError(t("error.bad_start"))


# ------------------------------------------------------- create custom flow ---
# channel_slug lives in bot.core.naming; re-exported here for the callers (and
# tests) that have always imported it from actions.
__all__ = ["channel_slug"]

# The custom channel is read-only for the room; these are the people who run it.
WRITE = discord.PermissionOverwrite(view_channel=True, send_messages=True)


def staff_overwrites(guild: discord.Guild) -> dict:
    """Write access for the configured staff roles (`ADMIN_ROLE` /
    `SUPERADMIN_ROLE`), so organisers can talk in any custom's channel."""
    out = {}
    for role_id in (settings.admin_role, settings.superadmin_role):
        role = guild.get_role(role_id) if role_id else None
        if role:
            out[role] = WRITE
    return out


async def allow_write(channel, target, reason: str) -> None:
    """Let one member type in a custom's (otherwise read-only) channel."""
    if not isinstance(channel, discord.TextChannel) or target is None:
        return
    try:
        await channel.set_permissions(
            target, view_channel=True, send_messages=True, reason=reason
        )
    except discord.HTTPException:
        pass


async def create_custom_flow(
    itx: discord.Interaction,
    *,
    name: str,
    fmt: str,
    start_raw: str,
    maps_csv: str,
    team_size: int = 5,
    draft_mode: str = "snake",
    captain_method: str = "random",
    tz_offset: int | None = None,
    game: str = "valorant",
) -> Custom:
    start_dt = parse_start(start_raw, tz_offset)
    c = await custom_svc.create_custom(
        start_asap=is_asap(start_raw),
        guild_id=itx.guild_id,
        owner_id=itx.user.id,
        name=name,
        fmt=fmt,
        start_time=start_dt,
        maps=maps_csv.split(","),
        vc_category=settings.customs_category_id,
        config_chan=itx.channel_id,
        team_size=team_size,
        draft_mode=draft_mode,
        captain_method=captain_method,
        game=game,
    )
    category = (
        itx.guild.get_channel(settings.customs_category_id)
        if settings.customs_category_id else None
    )
    # Everyone can see the channel and use the Register/Leave buttons (button clicks
    # don't need Send Messages), but only the bot, the staff roles, the owner —
    # and later the two captains — may type.
    overwrites = {
        itx.guild.default_role: discord.PermissionOverwrite(
            view_channel=True, send_messages=False, add_reactions=False
        ),
        itx.guild.me: discord.PermissionOverwrite(
            view_channel=True, send_messages=True, manage_channels=True
        ),
    }
    overwrites.update(staff_overwrites(itx.guild))
    if isinstance(itx.user, discord.Member):
        # The owner runs the custom, so they can always type in it — even if their
        # admin level is a bot-side grant rather than one of the Discord roles.
        overwrites[itx.user] = WRITE
    reg = await itx.guild.create_text_channel(
        channel_slug(itx.user.display_name, name),
        category=category if isinstance(category, discord.CategoryChannel) else None,
        overwrites=overwrites,
        reason="custom registration channel",
    )
    async with SessionLocal() as s:
        db_c = await s.get(Custom, c.custom_id)
        db_c.reg_channel = reg.id
        await s.commit()
        await s.refresh(db_c)
    notify_role_id = await guild_svc.get_notify_role(itx.guild_id)
    announce = t("custom.reg.announce", game=games_svc.game_label(db_c.game))
    content = f"<@&{notify_role_id}> {announce}" if notify_role_id else announce
    allowed_mentions = (
        discord.AllowedMentions(everyone=False, users=False,
                                 roles=[discord.Object(id=notify_role_id)])
        if notify_role_id else None
    )
    msg = await reg.send(
        content=content,
        embed=custom_registration_embed(db_c, [], db_c.team_size * 2),
        view=registration_view(db_c.custom_id),
        allowed_mentions=allowed_mentions,
    )
    # Remember the embed so later changes (e.g. an ownership transfer) can
    # redraw it without hunting through the channel's history.
    async with SessionLocal() as s:
        db_c = await s.get(Custom, c.custom_id)
        db_c.reg_message = msg.id
        await s.commit()
        await s.refresh(db_c)
    await audit.log(itx.guild_id, itx.user.id, "custom_create", str(c.custom_id))
    board.schedule(itx.guild)
    return db_c


# --------------------------------------------------- registration embed sync ---
async def _reg_message(
    guild: discord.Guild, custom: Custom
) -> discord.Message | None:
    """The custom's registration embed, by stored id — falling back to a scan of
    the channel for customs created before the id was recorded."""
    chan = guild.get_channel(custom.reg_channel) if custom.reg_channel else None
    if not isinstance(chan, discord.TextChannel):
        return None
    if custom.reg_message:
        try:
            return await chan.fetch_message(custom.reg_message)
        except discord.HTTPException:
            pass
    # Language-independent: the id is in the title in every language.
    marker = f"#{custom.custom_id}"
    try:
        async for m in chan.history(limit=50, oldest_first=False):
            if (m.author.id == guild.me.id and m.embeds
                    and marker in (m.embeds[0].title or "")):
                async with SessionLocal() as s:
                    db_c = await s.get(Custom, custom.custom_id)
                    if db_c:
                        db_c.reg_message = m.id
                        await s.commit()
                return m
    except discord.HTTPException:
        pass
    return None


async def refresh_registration_embed(
    guild: discord.Guild,
    custom_id: int,
    message: discord.Message | None = None,
) -> None:
    """Redraw the registration embed from the DB (owner, state, roster).

    `message` short-circuits the lookup when the caller already has it — a click
    on the Register/Leave buttons arrives with the message attached."""
    async with SessionLocal() as s:
        c = await s.get(Custom, custom_id)
    if not c:
        return
    msg = message or await _reg_message(guild, c)
    if not msg:
        return
    r = await custom_svc.roster(custom_id)
    try:
        await msg.edit(
            embed=custom_registration_embed(c, r.starters, r.size, r.waitlist)
        )
    except discord.HTTPException:
        pass


async def resend_registration_embed(guild: discord.Guild, custom_id: int) -> None:
    """Delete the current panel and repost it at the end of the channel.

    Used after a ready check fails so the panel — and its Register/Leave
    buttons — is visible again below the failure notice instead of sitting
    wherever it originally landed."""
    async with SessionLocal() as s:
        c = await s.get(Custom, custom_id)
    if not c:
        return
    chan = guild.get_channel(c.reg_channel) if c.reg_channel else None
    if not isinstance(chan, discord.TextChannel):
        return
    # Capture reference to old message before sending new one, so _reg_message
    # doesn't accidentally match the new message in its fallback channel scan.
    old = await _reg_message(guild, c)
    r = await custom_svc.roster(custom_id)
    try:
        msg = await chan.send(
            embed=custom_registration_embed(c, r.starters, r.size, r.waitlist),
            view=registration_view(custom_id),
        )
    except discord.HTTPException:
        return
    async with SessionLocal() as s:
        db_c = await s.get(Custom, custom_id)
        if db_c:
            db_c.reg_message = msg.id
            await s.commit()
    if old:
        try:
            await old.delete()
        except discord.HTTPException:
            pass


# ------------------------------------------------------ join / leave a custom ---
async def join_custom(
    guild: discord.Guild, custom_id: int, user_id: int, message=None
) -> str:
    """Register, redraw the embed, and say where they landed."""
    c, wait_pos = await custom_svc.register(custom_id, user_id, guild.id)
    await refresh_registration_embed(guild, custom_id, message)
    board.schedule(guild)
    if wait_pos:
        return t("custom.joined_waitlist", custom_id=custom_id, position=wait_pos)
    # Taking the last seat opens the ready check for everyone.
    await maybe_auto_ready_check(guild, custom_id)
    return t("custom.joined", custom_id=custom_id)


async def leave_custom(
    guild: discord.Guild, custom_id: int, user_id: int, message=None
) -> str:
    """Leave, redraw the embed, and ping whoever that just promoted."""
    c, promoted = await custom_svc.leave(custom_id, user_id, guild.id)
    await refresh_registration_embed(guild, custom_id, message)
    board.schedule(guild)
    if promoted:
        chan = guild.get_channel(c.reg_channel) if c.reg_channel else None
        if isinstance(chan, discord.TextChannel):
            try:
                await chan.send(
                    t("custom.promoted_channel", user_id=promoted, name=c.name)
                )
            except discord.HTTPException:
                pass
        member = guild.get_member(promoted)
        if member:
            try:
                await member.send(
                    t("custom.promoted_dm", custom_id=custom_id, name=c.name,
                      guild=guild.name)
                )
            except discord.HTTPException:
                pass
    return t("custom.left", custom_id=custom_id)


# ------------------------------------------------------------- ownership ------
async def transfer_custom(
    itx: discord.Interaction, custom_id: int, new_owner: discord.Member
) -> Custom:
    """Hand a custom over: persist, redraw the registration embed, and tell the
    new owner — in DM, and in the custom's own channel so the room sees it too."""
    async with SessionLocal() as s:
        c = await custom_svc.get_in_guild(s, custom_id, itx.guild_id)
    if not await can_manage_custom(c, itx.user):
        raise BotError(t("error.transfer_perm"))
    if c.owner_id == new_owner.id:
        raise BotError(t("error.already_owner", name=new_owner.display_name,
                         custom_id=custom_id))
    if new_owner.bot:
        raise BotError(t("error.bot_owner"))

    c = await custom_svc.transfer(custom_id, new_owner.id)
    await refresh_registration_embed(itx.guild, custom_id)

    chan = itx.guild.get_channel(c.reg_channel) if c.reg_channel else None
    # The new owner runs the custom now, so let them talk in its channel.
    await allow_write(chan, new_owner, reason=f"custom {custom_id} owner")
    note = t("custom.transfer_note", custom_id=custom_id, name=c.name,
             new_owner=new_owner.mention, actor=itx.user.mention)
    if isinstance(chan, discord.TextChannel):
        try:
            await chan.send(note)
        except discord.HTTPException:
            pass
    try:
        where = (chan.mention if isinstance(chan, discord.TextChannel)
                 else t("common.its_channel"))
        await new_owner.send(
            t("custom.transfer_dm", custom_id=custom_id, name=c.name,
              guild=itx.guild.name, actor=itx.user.display_name, where=where)
        )
    except discord.HTTPException:
        pass  # DMs closed — the channel note above still tells them

    await audit.log(itx.guild_id, itx.user.id, "custom_transfer",
                    str(custom_id), to=new_owner.id)
    board.schedule(itx.guild)
    return c


# -------------------------------------------------------- start match flow ---
async def _queue_for_custom(custom_id: int) -> Queue:
    q = await queue_svc.queue_for_custom(custom_id)
    if not q:
        raise BotError(t("error.no_queue"))
    return q


async def _players_meta(ids: list[int], *, refresh_ranks: bool = False) -> list[dict]:
    if refresh_ranks:
        # Captains are being chosen off this data right now, so a cached
        # value isn't good enough here — force past the normal TTL.
        for uid in ids:
            await rank_sync.refresh_rank(uid, force=True)  # best-effort, never raises
    async with SessionLocal() as s:
        out = []
        for uid in ids:
            u = await s.get(User, uid)
            approved = bool(u) and u.riot_status == "approved"
            out.append({"user_id": uid,
                        "wins": u.wins if u else 0,
                        "cur_rr": u.cur_rr if approved else None,
                        "peak_rank": u.peak_rank if approved else None})
        return out


async def _run_draft(guild, channel, custom, match_id, cap_a, cap_b, pool, first_side):
    """Draft the non-captain players, in the custom's configured order."""
    draft = DraftController(match_id, cap_a, cap_b, pool,
                            mode=custom.draft_mode, first=first_side, guild=guild)

    @flow_step(channel, "the map veto" if games_svc.has_veto(custom.game) else "the match lobby")
    async def after_draft():
        if games_svc.has_veto(custom.game):
            await _run_veto(guild, channel, custom, match_id, draft, cap_a, cap_b)
        else:
            await _finish_without_veto(guild, channel, custom, match_id, draft, cap_a, cap_b)

    if draft.done:                      # 1v1: nothing to draft
        await draft.persist_teams()
        await channel.send(embed=draft.embed())
        await after_draft()
        return
    dview = DraftView(draft, after_draft, guild=guild)
    dview.channel = channel
    dview.message = await channel.send(embed=draft.embed(), view=dview)
    await dview.arm()  # start the per-turn auto-pick timer


async def _setup_team_vcs_safe(guild, channel, custom, draft, cap_a, cap_b) -> None:
    """Voice is a convenience, the match itself is not. A server that can't take
    two more channels (category full, missing Manage Channels) must not strand
    the match between the draft and whatever comes next, so this failure is
    reported, not raised."""
    try:
        await voice.setup_team_vcs(guild, custom, draft.team["A"], draft.team["B"],
                                   cap_a=cap_a, cap_b=cap_b)
    except discord.HTTPException as e:
        log.warning("team VCs for custom %s failed: %s", custom.custom_id, e)
        await channel.send(t("error.team_vcs", error=e.text or e))


async def _finish_without_veto(guild, channel, custom, match_id, draft, cap_a, cap_b):
    """Games with no map veto (Dota 2) go straight from the draft to live."""
    await _setup_team_vcs_safe(guild, channel, custom, draft, cap_a, cap_b)
    async with SessionLocal() as s:
        m = await s.get(Match, match_id)
        m.state = "live"
        await s.commit()
    await finish_match(guild, channel, custom, match_id)


async def _run_veto(guild, channel, custom, match_id, draft, cap_a, cap_b):
    pool = json.loads(custom.map_pool)
    veto_ctl = VetoController(match_id, custom.format, pool, cap_a, cap_b,
                              guild=guild, game=custom.game)
    ACTIVE_VETO[match_id] = veto_ctl
    await _setup_team_vcs_safe(guild, channel, custom, draft, cap_a, cap_b)
    async with SessionLocal() as s:
        m = await s.get(Match, match_id)
        m.state = "veto"
        await s.commit()
    view = VetoView(veto_ctl)
    view.channel = channel

    @flow_step(channel, "the match lobby")
    async def _finish():
        # The decider's side lives on the match row as well, so a lobby drawn by
        # a build that predates the per-map table still shows something.
        if veto_ctl.sides:
            name, chooser, choice = veto_ctl.sides[-1]
            async with SessionLocal() as s:
                m = await s.get(Match, match_id)
                if m:
                    m.side_map, m.side_pick, m.side_pick_side = name, choice, chooser
                    await s.commit()
        await finish_match(guild, channel, custom, match_id)

    view.on_done = _finish
    view.message = await channel.send(embed=veto_ctl.embed(), view=view)
    await view.arm()  # start the per-turn auto-pick timer


async def build_lobby_embed(guild: discord.Guild, custom_id: int) -> discord.Embed | None:
    """The match lobby, rebuilt from the DB.

    Read from storage rather than the in-memory controllers so the lobby's
    buttons can redraw it at any time — including after a bot restart, when the
    draft/veto controllers are long gone.
    """
    from bot.db.models import MapVeto, MatchMapSide

    async with SessionLocal() as s:
        c = await s.get(Custom, custom_id)
        if not c or not c.match_id:
            return None
        m = await s.get(Match, c.match_id)
        caps = {
            t.side: t.captain_id
            for (t,) in (await s.execute(
                select(MatchTeam).where(MatchTeam.match_id == c.match_id)
            )).all()
        }
        squads: dict[str, list[int]] = {"A": [], "B": []}
        for (mp,) in (await s.execute(
            select(MatchPlayer).where(MatchPlayer.match_id == c.match_id)
        )).all():
            if mp.side in squads:
                squads[mp.side].append(mp.user_id)
        maps = [
            r[0] for r in (await s.execute(
                select(MapVeto.map_name).where(
                    MapVeto.match_id == c.match_id,
                    MapVeto.action.in_(("pick", "decider")),
                ).order_by(MapVeto.step)
            )).all()
        ]
        sides = {
            r.map_name: (r.team_side, r.choice)
            for (r,) in (await s.execute(
                select(MatchMapSide).where(MatchMapSide.match_id == c.match_id)
                .order_by(MatchMapSide.map_index)
            )).all()
        }
        # Matches played before sides were tracked per map kept only the
        # decider's, on the match row itself.
        if not sides and m and m.side_map and m.side_pick and m.side_pick_side:
            sides = {m.side_map: (m.side_pick_side, m.side_pick)}

    def _squad(side: str) -> str:
        cap = caps.get(side)
        # captain first, then the rest
        ids = sorted(squads[side], key=lambda u: (u != cap, u))
        return "\n".join(f"<@{u}>" for u in ids) or DASH

    e = discord.Embed(
        title=t("lobby.full_title", name=c.name, match_id=c.match_id, fmt=c.format),
        color=EMBED_COLOR,
    )
    # The captain is named in the field header rather than crowned in the list —
    # the roster below is then just the roster.
    for side, label in (("A", "common.team_a"), ("B", "common.team_b")):
        cap = caps.get(side)
        e.add_field(
            name=t("lobby.team_cap", team=t(label),
                   captain=member_name(guild, cap) if cap else DASH),
            value=_squad(side),
            inline=True,
        )

    def _map_line(i: int, name: str) -> str:
        chooser, choice = sides.get(name, (None, None))
        if not chooser:
            return t("lobby.map_line_plain", index=i, map=name)
        flip = "defence" if choice == "attack" else "attack"
        return t(
            "lobby.map_line", index=i, map=name,
            side_a=games_svc.side_label(choice if chooser == "A" else flip),
            side_b=games_svc.side_label(choice if chooser == "B" else flip),
        )

    if games_svc.has_veto(c.game):
        e.add_field(
            name=t("common.maps"),
            value="\n".join(_map_line(i, n) for i, n in enumerate(maps, start=1)) or DASH,
            inline=False,
        )
    e.add_field(
        name=games_svc.code_text("label", c.game),
        value=f"`{m.party_code}`" if m and m.party_code else DASH,
        inline=True,
    )
    vcs = " / ".join(x.mention for x in voice.team_vcs(guild, c) if x)
    if vcs:
        e.add_field(name=t("lobby.voice"), value=vcs, inline=True)
    e.set_footer(text=t("lobby.footer"))
    e.timestamp = datetime.now(timezone.utc)
    return e


async def finish_match(guild, channel, custom, match_id):
    """Veto (or draft, for games with none) done → mark the match live and post
    the final lobby for everyone."""
    from bot.core.views import lobby_view

    async with SessionLocal() as s:
        m = await s.get(Match, match_id)
        m.state = "live"
        c = await s.get(Custom, custom.custom_id)
        c.state = "live"
        await s.commit()
    ACTIVE_VETO.pop(match_id, None)

    e = await build_lobby_embed(guild, custom.custom_id)
    if e:
        await channel.send(embed=e, view=lobby_view(custom.custom_id, game=custom.game))


async def begin_match(
    guild: discord.Guild,
    custom_id: int,
    *,
    captains: str | None = None,
    manual: tuple[int, int] | None = None,
    allow_partial: bool = False,
    actor_id: int | None = None,
) -> tuple[int, discord.abc.Messageable, int, int, int]:
    """Create the match, pick captains and hand off to the coin toss.

    No `Interaction`: this is the shared core, driven either by a person
    pressing **Start** or by a ready check that everybody passed. Returns
    `(match_id, channel, cap_a, cap_b, per_side)` for the caller to report.
    """
    async with SessionLocal() as s:
        c = await custom_svc.get_in_guild(s, custom_id, guild.id)
    if c.state == "ready":
        raise BotError(t("error.ready_running", custom_id=custom_id))
    if c.state in ("veto", "live"):
        raise BotError(
            t("error.match_in_progress", custom_id=custom_id, state=c.state)
        )
    # Check the pool before anything is created: a custom made before the format
    # got its pool rule would otherwise strand two drafted teams at the veto.
    # Games with no veto (Dota 2) have no pool to check.
    if games_svc.has_veto(c.game):
        try:
            veto_svc.check_pool(c.format, len(json.loads(c.map_pool)))
        except BotError as e:
            raise BotError(t("error.pool_recreate", reason=e))
    # The method is fixed when the custom is created; `captains` overrides it
    # only where a caller genuinely needs to (e.g. `/match start captains:manual`).
    captains = captains or c.captain_method or "random"

    q = await _queue_for_custom(custom_id)
    signed_up = await queue_svc.members(q.queue_id)
    # Anyone past the seat count is a sub — they never play, whichever start is
    # used, so the custom always runs at the team size it was created with.
    member_ids, subs = signed_up[: q.size], signed_up[q.size:]

    if allow_partial:
        n = len(member_ids)
        if n < 2 or n % 2 != 0:
            raise BotError(t("error.partial_even", n=n))
    elif len(member_ids) < q.size:
        raise BotError(
            t("error.queue_not_full", have=len(member_ids), size=q.size)
        )

    if captains == "manual":
        if not manual:
            raise BotError(t("error.manual_both"))
        if manual[0] == manual[1]:
            raise BotError(t("error.manual_distinct"))
        if not set(manual) <= set(member_ids):
            raise BotError(t("error.manual_registered"))

    async with SessionLocal() as s:
        match = Match(guild_id=guild.id, custom_id=custom_id, format=c.format,
                      game=c.game, state="captains", created_by=actor_id)
        s.add(match)
        await s.flush()
        for uid in member_ids:
            s.add(MatchPlayer(match_id=match.match_id, user_id=uid, checked_in=True))
        db_c = await s.get(Custom, custom_id)
        db_c.match_id = match.match_id
        db_c.state = "veto"
        await s.commit()
        match_id = match.match_id
    board.schedule(guild)

    players_meta = await _players_meta(
        member_ids, refresh_ranks=captains in draft_svc.RANK_METHODS
    )
    fell_back, original_method = False, captains
    if captains in draft_svc.RANK_METHODS and not draft_svc.has_enough_rank_data(
        captains, players_meta
    ):
        fell_back, captains = True, "random"
        log.info("match %s: captain method %s fell back to random (not enough rank data)",
                 match_id, original_method)
    cap_a, cap_b = draft_svc.choose_captains(captains, players_meta, manual=manual)
    log.info("match %s: captains chosen via %s -> %s, %s", match_id, captains, cap_a, cap_b)
    pool = [u for u in member_ids if u not in (cap_a, cap_b)]
    per_side = len(member_ids) // 2

    # All match flow (toss, draft, ban/pick veto, sides, lobby) goes in the
    # custom's own channel.
    channel = guild.get_channel(c.reg_channel) if c.reg_channel else None
    if channel is None:
        raise BotError(t("error.no_channel"))

    # Let the two captains type in the custom channel; everyone else stays read-only
    # (admins and the owner already got write access when the channel was made).
    for cap_id in (cap_a, cap_b):
        await allow_write(channel, guild.get_member(cap_id), reason="captain")

    # No letters yet on purpose — the coin toss below decides who is Team A.
    await channel.send(
        t("match.announce", match_id=match_id, per_side=per_side,
          cap_a=cap_a, cap_b=cap_b, method=draft_svc.captain_label(captains))
    )
    if fell_back:
        await channel.send(
            t("match.captains_fallback_random",
              method=draft_svc.captain_label(original_method))
        )
    if subs:
        await channel.send(
            t("match.subs", subs=", ".join(f"<@{u}>" for u in subs))
        )

    # Coin toss first: a random captain calls it and the winner takes Team A or
    # Team B. It runs even in a 1v1, where there's no draft to order but Team A
    # still bans first. The captains may swap letters, so read them back off the
    # controller rather than trusting the pair we came in with.
    coin = CoinflipController(match_id, cap_a, cap_b, guild=guild)

    @flow_step(channel, "the draft")
    async def after_coin(toss: CoinflipController):
        async with SessionLocal() as s:
            m = await s.get(Match, match_id)
            if m:
                m.first_pick_side = toss.first_side
                await s.commit()
        await _run_draft(guild, channel, c, match_id, toss.cap_a, toss.cap_b,
                         pool, toss.first_side)

    cview = CoinflipView(coin, after_coin)
    cview.channel = channel
    cview.message = await channel.send(embed=coin.embed(), view=cview)
    await cview.arm()
    return match_id, channel, cap_a, cap_b, per_side


async def start_match(
    itx: discord.Interaction,
    custom_id: int,
    captains: str | None = None,
    captain_a: discord.Member | None = None,
    captain_b: discord.Member | None = None,
    allow_partial: bool = False,
):
    """Someone pressed Start. Checks they may, cancels any ready check that's on
    the clock, and reports back on the interaction."""
    # Starting a match makes several REST calls (channel perms, messages) before
    # it can answer — ack the interaction first or the token expires (10062).
    if not itx.response.is_done():
        await itx.response.defer(ephemeral=True)

    async with SessionLocal() as s:
        c = await custom_svc.get_in_guild(s, custom_id, itx.guild_id)
    if not await can_manage_custom(c, itx.user):
        raise BotError(t("error.start_perm"))

    # A manual start overrules a running ready check — that's the whole point of
    # having both ways in.
    await cancel_ready_check(
        custom_id, t("ready.cancel.manual", actor=itx.user.mention)
    )

    manual = None
    if captains == "manual":
        if not (captain_a and captain_b):
            raise BotError(t("error.manual_both"))
        manual = (captain_a.id, captain_b.id)

    match_id, channel, cap_a, cap_b, per_side = await begin_match(
        itx.guild, custom_id, captains=captains, manual=manual,
        allow_partial=allow_partial, actor_id=itx.user.id,
    )
    await itx.followup.send(
        t("match.starting", match_id=match_id, per_side=per_side,
          channel=channel.mention, cap_a=cap_a, cap_b=cap_b),
        ephemeral=True,
    )


# -------------------------------------------------------------- ready check ---
# Live ready checks, keyed by custom_id. In memory like the other run-of-match
# views — `custom_svc.clear_stale_ready_checks()` un-sticks anything a restart
# stranded in the `ready` state.
ACTIVE_READY: dict[int, ReadyCheckView] = {}

MAX_READY_ROUNDS = 3  # drop-and-refill can't loop forever

READY_COOLDOWN: dict[int, asyncio.Task] = {}
READY_COOLDOWN_SECONDS = 20


def _schedule_cooldown_retry(guild: discord.Guild, custom_id: int) -> None:
    """After a cap-hit failure, wait out the cooldown then try a fresh round 1.

    Mirrors `board.schedule`'s per-key debounce pattern. Retrying instantly
    would just hit the cap again since the waitlist refills every seat — the
    pause is what actually breaks the loop."""
    async def _run() -> None:
        try:
            await asyncio.sleep(READY_COOLDOWN_SECONDS)
            r = await custom_svc.roster(custom_id)
            if len(r.starters) < r.size:
                return  # someone left during the cooldown; a future join retriggers this
            # Clear our own cooldown entry before retrying — start_ready_check's
            # guard checks READY_COOLDOWN, and this task's own entry would
            # otherwise self-reject the very retry it exists to perform. No
            # await happens between this pop and the call, so no external
            # caller can slip in through the gap.
            READY_COOLDOWN.pop(custom_id, None)
            await start_ready_check(guild, custom_id)
        except asyncio.CancelledError:
            raise
        except BotError as e:
            log.info("cooldown ready check skipped for custom %s: %s", custom_id, e)
        except Exception:  # noqa: BLE001 - a crashed retry must not break anything else
            log.exception("cooldown ready check crashed for custom %s", custom_id)
        finally:
            READY_COOLDOWN.pop(custom_id, None)

    READY_COOLDOWN[custom_id] = asyncio.create_task(_run())


async def _set_state(custom_id: int, state: str) -> None:
    async with SessionLocal() as s:
        c = await s.get(Custom, custom_id)
        if c:
            c.state = state
            await s.commit()


async def cancel_ready_check(custom_id: int, note: str) -> bool:
    """Call off a running check (manual start, deletion). Returns whether one was
    actually running."""
    view = ACTIVE_READY.pop(custom_id, None)
    if view is None:
        return False
    await view.cancel(note)
    async with SessionLocal() as s:
        c = await s.get(Custom, custom_id)
        if c and c.state == "ready":
            c.state = "full"
            await s.commit()
    return True


async def start_ready_check(
    guild: discord.Guild, custom_id: int, *, round_no: int = 1, actor_id: int | None = None
) -> str:
    """Post a ready check in the custom's channel and put every starter on the
    clock. Returns a line for whoever asked for it."""
    async with SessionLocal() as s:
        c = await custom_svc.get_in_guild(s, custom_id, guild.id)
    if custom_id in ACTIVE_READY or custom_id in READY_COOLDOWN:
        raise BotError(t("error.ready_already", custom_id=custom_id))
    if c.state not in ("registration", "full"):
        raise BotError(t("error.ready_state", custom_id=custom_id, state=c.state))
    channel = guild.get_channel(c.reg_channel) if c.reg_channel else None
    if not isinstance(channel, discord.TextChannel):
        raise BotError(t("error.ready_no_channel"))

    r = await custom_svc.roster(custom_id)
    n = len(r.starters)
    if n < 2 or n % 2 != 0:
        raise BotError(t("error.ready_even", n=n))

    deadline = datetime.now(timezone.utc) + timedelta(seconds=settings.ready_check_seconds)
    ctl = ReadyCheckController(custom_id, c.name, r.starters, deadline, round_no, guild=guild)
    view = ReadyCheckView(ctl, None)

    @flow_step(channel, "the match")
    async def on_resolve():
        await _resolve_ready_check(guild, custom_id, ctl, view)

    view.on_resolve = on_resolve
    view.channel = channel
    await _set_state(custom_id, "ready")
    view.message = await channel.send(
        content=t("ready.ping", mentions=ctl.mentions()), embed=ctl.embed(), view=view
    )
    await view.arm()
    ACTIVE_READY[custom_id] = view
    board.schedule(guild)
    await audit.log(guild.id, actor_id, "ready_check", str(custom_id), round=round_no)
    return t("ready.posted", channel=channel.mention, n=n,
             seconds=settings.ready_check_seconds)


async def _resolve_ready_check(
    guild: discord.Guild, custom_id: int, ctl: ReadyCheckController, view: ReadyCheckView
) -> None:
    """Everyone answered, or the clock ran out.

    All ready → start. Otherwise the players who didn't confirm lose their seats
    to the waitlist and a fresh round runs — the lobby repairs itself rather than
    waiting on an organiser. With nobody left to promote, it falls back to
    registration with the roster intact.
    """
    ACTIVE_READY.pop(custom_id, None)
    channel = view.channel

    async def outcome(text: str) -> None:
        try:
            await view.message.edit(embed=ctl.embed(outcome=text), view=None)
        except discord.HTTPException:
            pass

    if ctl.everyone_ready:
        await outcome(t("ready.outcome.all_ready"))
        await _set_state(custom_id, "full")
        await begin_match(guild, custom_id, allow_partial=True)
        return

    absent = ctl.absent
    for uid in absent:
        try:
            await custom_svc.leave(custom_id, uid, guild.id)
        except BotError:
            pass  # already gone
    await _set_state(custom_id, "full")
    board.schedule(guild)

    r = await custom_svc.roster(custom_id)
    dropped = ", ".join(f"<@{u}>" for u in absent)
    await outcome(t("ready.outcome.incomplete", dropped=dropped))

    filled = len(r.starters) == r.size
    if filled and ctl.round_no < MAX_READY_ROUNDS:
        await channel.send(
            t("ready.subs_round", dropped=dropped, round=ctl.round_no + 1)
        )
        await resend_registration_embed(guild, custom_id)
        return await start_ready_check(guild, custom_id, round_no=ctl.round_no + 1)

    if filled:
        # Cap hit but the waitlist still fills every seat every round —
        # retrying instantly would just hit the cap again. State is already
        # "full" from the _set_state call above; cool off, then retry as a
        # genuine round 1.
        await channel.send(
            t("ready.cooldown_retry", n=MAX_READY_ROUNDS, seconds=READY_COOLDOWN_SECONDS)
        )
        await resend_registration_embed(guild, custom_id)
        _schedule_cooldown_retry(guild, custom_id)
        return

    await _set_state(custom_id, "registration")
    board.schedule(guild)
    await channel.send(
        t("ready.failed", custom_id=custom_id, why=t("ready.why.no_subs"),
          filled=len(r.starters), size=r.size)
    )
    await resend_registration_embed(guild, custom_id)


async def maybe_auto_ready_check(guild: discord.Guild, custom_id: int) -> None:
    """Fire a ready check the moment the last seat fills.

    Best-effort: a failure here must never break the registration that triggered
    it, so everything is swallowed and logged.
    """
    try:
        if custom_id in ACTIVE_READY:
            return
        async with SessionLocal() as s:
            c = await s.get(Custom, custom_id)
        if not c or c.state != "full":
            return
        r = await custom_svc.roster(custom_id)
        if len(r.starters) < r.size:
            return
        await start_ready_check(guild, custom_id)
    except BotError as e:
        log.info("auto ready check skipped for custom %s: %s", custom_id, e)
    except Exception:  # noqa: BLE001 - never break a join
        log.exception("auto ready check crashed for custom %s", custom_id)


# --------------------------------------------------------------- party code ---
async def active_match_for_custom(custom_id: int) -> Match | None:
    async with SessionLocal() as s:
        c = await s.get(Custom, custom_id)
        if not c or not c.match_id:
            return None
        return await s.get(Match, c.match_id)


async def is_match_captain(match_id: int, user_id: int) -> bool:
    async with SessionLocal() as s:
        rows = await s.execute(
            select(MatchTeam.captain_id).where(MatchTeam.match_id == match_id)
        )
        return user_id in {r[0] for r in rows.all()}


async def _can_run_custom(custom_id: int, member: discord.Member) -> bool:
    """Captain of the custom's match, or owner/admin of the custom's guild."""
    async with SessionLocal() as s:
        c = await s.get(Custom, custom_id)
    if not c or not isinstance(member, discord.Member) or c.guild_id != member.guild.id:
        return False
    if await can_manage_custom(c, member) or await is_admin(member):
        return True
    if c.match_id and await is_match_captain(c.match_id, member.id):
        return True
    return False


async def is_registered(custom_id: int, user_id: int) -> bool:
    async with SessionLocal() as s:
        return await s.get(CustomRegistration, (custom_id, user_id)) is not None


async def can_play_custom(custom_id: int, member: discord.Member) -> bool:
    """Anyone registered for the custom, plus its owner/captains/admins.
    These are the people actually in the game, so they run it."""
    async with SessionLocal() as s:
        c = await s.get(Custom, custom_id)
    if not c or not isinstance(member, discord.Member) or c.guild_id != member.guild.id:
        return False
    if await is_registered(custom_id, member.id):
        return True
    return await _can_run_custom(custom_id, member)


async def set_party_code(
    itx: discord.Interaction, custom_id: int, code: str, announce: bool = True
) -> str:
    """Any registered player (or admin) sets/updates the party code (or, for a
    game like CS2, the server IP — see bot.services.games.code_text).

    `announce` posts it as a channel message — used by the slash command. The
    lobby button passes False because it redraws the lobby embed instead.
    Returns the custom's game, so callers can word their own confirmation.
    """
    if not await can_play_custom(custom_id, itx.user):
        raise BotError(t("error.code_perm"))
    match = await active_match_for_custom(custom_id)
    if not match:
        raise BotError(t("error.no_match_yet"))
    # The code is echoed into a public channel inside a code span — strip the
    # characters that would let it break out or inject markdown. `.` and `:`
    # are kept so an IP:port (CS2) survives intact.
    code = "".join(ch for ch in code.strip() if ch.isalnum() or ch in "-_.:")[:32]
    if not code:
        raise BotError(t("error.code_charset"))
    async with SessionLocal() as s:
        m = await s.get(Match, match.match_id)
        m.party_code = code
        c = await s.get(Custom, custom_id)
        chan_id = c.reg_channel
        game = c.game
        await s.commit()
    # Post the code openly (visible to everyone) in the custom channel.
    chan = itx.guild.get_channel(chan_id) if chan_id else None
    if announce and chan:
        await chan.send(games_svc.code_text(
            "announced", game, custom_id=custom_id, code=code, actor=itx.user.mention,
        ))
    await audit.log(itx.guild_id, itx.user.id, "party_code", str(custom_id))
    return game


async def played_maps(match_id: int) -> list[str]:
    """The maps this match actually plays, in the order they're played —
    every veto `pick` plus the decider. Empty until the veto has run, which
    is what tells a caller there is no result to ask about yet."""
    from bot.db.models import MapVeto

    async with SessionLocal() as s:
        return [
            r[0] for r in (await s.execute(
                select(MapVeto.map_name).where(
                    MapVeto.match_id == match_id,
                    MapVeto.action.in_(("pick", "decider")),
                ).order_by(MapVeto.step)
            )).all()
        ]


async def pending_result(custom_id: int) -> tuple[int, list[str], dict[str, str]] | None:
    """What still needs reporting before this custom can be ended honestly:
    `(match_id, maps, already reported as {map: "13-11"})`.

    `None` means there is nothing to ask about — the custom has no match, the
    veto never finished (so no map was played), or the results already on file
    settle the series. Everything else means ending now would throw the game
    away: `_award_wins` has nothing to credit, and the custom silently
    disappears from everyone's win count.
    """
    async with SessionLocal() as s:
        c = await s.get(Custom, custom_id)
        # Only a custom that reached `live` has played anything: the veto writes
        # its picks one at a time, so a custom ended mid-veto would otherwise be
        # asked for the score of maps that were merely chosen.
        if not c or not c.match_id or c.state != "live":
            return None
        match_id = c.match_id
        reported = [
            r for (r,) in (await s.execute(
                select(MatchResult).where(MatchResult.match_id == match_id)
                .order_by(MatchResult.map_index)
            )).all()
        ]
    if draft_svc.series_winner([r.winner_side for r in reported]):
        return None
    maps = await played_maps(match_id)
    if not maps:
        return None
    return match_id, maps, {r.map_name: f"{r.score_a}-{r.score_b}" for r in reported}


async def save_match_results(match_id: int, rows: list[tuple[str, int, int]]) -> None:
    """Replace this match's results with `[(map_name, score_a, score_b), ...]`,
    in the order the maps were played.

    A wholesale replace, not an append: the rows come from a form that shows
    what was already on file, so what comes back *is* the series — merging it
    with earlier `/match result` reports would double-count the maps the
    reporter left untouched."""
    async with SessionLocal() as s:
        for r in (await s.execute(
            select(MatchResult).where(MatchResult.match_id == match_id)
        )).scalars().all():
            await s.delete(r)
        await s.flush()
        for idx, (map_name, score_a, score_b) in enumerate(rows):
            s.add(MatchResult(
                match_id=match_id, map_index=idx, map_name=map_name,
                score_a=score_a, score_b=score_b,
                winner_side="A" if score_a > score_b else "B",
            ))
        await s.commit()
    log.info("match %s: results set to %s", match_id, rows)


async def _award_wins(s, match_id: int) -> None:
    """+1 `User.wins` for every player on the side that won the series,
    determined from the maps reported on the result form (or via
    `/match result`). A no-op if nothing was reported, or the two sides are
    tied (a force-ended custom with no majority yet) — there's no winner to
    credit."""
    results = (await s.execute(
        select(MatchResult.winner_side).where(MatchResult.match_id == match_id)
    )).scalars().all()
    winner_side = draft_svc.series_winner(results)
    if not winner_side:
        log.info("match %s: no series winner to award wins for (%s)", match_id, results)
        return
    winners = (await s.execute(
        select(MatchPlayer.user_id).where(
            MatchPlayer.match_id == match_id, MatchPlayer.side == winner_side
        )
    )).scalars().all()
    for uid in winners:
        u = await s.get(User, uid)
        if u:
            u.wins += 1
    log.info("match %s: side %s won, +1 win for %s", match_id, winner_side, winners)


async def end_custom(
    itx: discord.Interaction, custom_id: int, *, require_result: bool = True
) -> None:
    """End a match: mark it completed/done, then remove the custom's voice AND
    text channels. Any registered player can end it once it has started.

    `require_result=False` ends a match whose result nobody reported. It is not
    the default because ending is the last moment the result exists anywhere:
    the channels go, and with them any chance of asking who won — the maps go
    uncredited and the custom vanishes from everyone's win count. Callers pass
    it only after a human has been asked and answered (the result form) or has
    deliberately forced it.

    The caller must have already answered (or deferred) the interaction — the
    text channel this was clicked in is about to disappear."""
    if not await can_play_custom(custom_id, itx.user):
        raise BotError(t("error.end_perm"))
    async with SessionLocal() as s:
        c = await s.get(Custom, custom_id)
        if not c:
            raise BotError(t("error.custom_not_found"))
        if c.state == "done":
            raise BotError(t("error.already_ended"))
        if c.state in ("registration", "full"):
            raise BotError(t("error.not_started"))
        if c.match_id:
            m = await s.get(Match, c.match_id)
            if m:
                if require_result and await pending_result(custom_id):
                    raise BotError(t("error.result_missing"))
                m.state = "completed"
                await _award_wins(s, c.match_id)
        c.state = "done"
        chan_id = c.reg_channel
        await s.commit()
    await voice.teardown_vcs(itx.guild, c, disconnect=True)
    if chan_id:
        chan = itx.guild.get_channel(chan_id)
        if chan:
            try:
                await chan.delete(reason=f"custom {custom_id} ended")
            except discord.HTTPException:
                pass
    await audit.log(itx.guild_id, itx.user.id, "custom_end", str(custom_id))
    board.schedule(itx.guild)
