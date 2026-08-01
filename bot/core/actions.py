"""Reusable orchestration shared by slash commands and the button panel.

Keeping this here (not in a cog) lets both /custom, /match AND the panel views
call the exact same flows without duplication or circular imports.
"""
from __future__ import annotations

import logging
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
from bot.core.embeds import VAL_RED, custom_registration_embed
from bot.core.errors import BotError
from bot.core.naming import channel_slug
from bot.core.views import (
    CoinflipView,
    DraftView,
    ReadyCheckView,
    SidePickView,
    VetoView,
    registration_view,
)
from bot.db import SessionLocal
from bot.db.models import (
    Custom,
    CustomRegistration,
    Match,
    MatchPlayer,
    MatchTeam,
    Queue,
    User,
)
from bot.services import custom as custom_svc
from bot.services import draft as draft_svc
from bot.services import queue_svc, voice

log = logging.getLogger("valbot.flow")

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
                        f"⚠️ Couldn't continue to **{what}** — "
                        f"`{type(e).__name__}: {e}`.\n"
                        f"Ask an admin to end this custom and start it again "
                        f"(the error is in the bot log)."
                    )
                except discord.HTTPException:
                    pass
        return runner
    return wrap


# ----------------------------------------------------------- time parsing ---
def parse_start(raw: str, tz_offset: int | None = None) -> datetime:
    """`HH:MM` or ISO → a UTC instant.

    Times are read in the server's local zone (`TZ_OFFSET` in .env) — Discord
    doesn't expose a user's timezone, so one server-wide offset is the closest
    thing to "just type the time you mean". A bare `HH:MM` that has already
    passed today rolls forward to tomorrow.
    """
    raw = raw.strip()
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
        raise BotError("Start must be `HH:MM` or ISO `2026-06-24T20:00`.")


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
) -> Custom:
    start_dt = parse_start(start_raw, tz_offset)
    c = await custom_svc.create_custom(
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
    msg = await reg.send(embed=custom_registration_embed(db_c, [], db_c.team_size * 2),
                         view=registration_view(db_c.custom_id))
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
    title = f"🎮 Custom #{custom.custom_id}"
    try:
        async for m in chan.history(limit=50, oldest_first=True):
            if (m.author.id == guild.me.id and m.embeds
                    and (m.embeds[0].title or "").startswith(title)):
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


# ------------------------------------------------------ join / leave a custom ---
async def join_custom(
    guild: discord.Guild, custom_id: int, user_id: int, message=None
) -> str:
    """Register, redraw the embed, and say where they landed."""
    c, wait_pos = await custom_svc.register(custom_id, user_id, guild.id)
    await refresh_registration_embed(guild, custom_id, message)
    board.schedule(guild)
    if wait_pos:
        return (f"🪑 Custom #{custom_id} is full — you're **#{wait_pos} on the "
                f"waitlist** and move up automatically if someone drops out.")
    # Taking the last seat opens the ready check for everyone.
    await maybe_auto_ready_check(guild, custom_id)
    return f"Registered for Custom #{custom_id} ✅ — watch for the ready check."


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
                    f"🪑 <@{promoted}> — a seat opened up in **{c.name}**, "
                    f"you're in the game now."
                )
            except discord.HTTPException:
                pass
        member = guild.get_member(promoted)
        if member:
            try:
                await member.send(
                    f"🪑 You moved off the waitlist into **Custom #{custom_id} — "
                    f"{c.name}** in **{guild.name}**. You're playing."
                )
            except discord.HTTPException:
                pass
    return f"Left Custom #{custom_id}."


# ------------------------------------------------------------- ownership ------
async def transfer_custom(
    itx: discord.Interaction, custom_id: int, new_owner: discord.Member
) -> Custom:
    """Hand a custom over: persist, redraw the registration embed, and tell the
    new owner — in DM, and in the custom's own channel so the room sees it too."""
    from bot.core.permissions import can_manage_custom

    async with SessionLocal() as s:
        c = await custom_svc.get_in_guild(s, custom_id, itx.guild_id)
    if not await can_manage_custom(c, itx.user):
        raise BotError("Only the owner or a superadmin can transfer this custom.")
    if c.owner_id == new_owner.id:
        raise BotError(f"{new_owner.display_name} already owns Custom #{custom_id}.")
    if new_owner.bot:
        raise BotError("A bot can't own a custom.")

    c = await custom_svc.transfer(custom_id, new_owner.id)
    await refresh_registration_embed(itx.guild, custom_id)

    chan = itx.guild.get_channel(c.reg_channel) if c.reg_channel else None
    # The new owner runs the custom now, so let them talk in its channel.
    await allow_write(chan, new_owner, reason=f"custom {custom_id} owner")
    note = (f"👑 Ownership of **Custom #{custom_id} — {c.name}** transferred to "
            f"{new_owner.mention} by {itx.user.mention}.")
    if isinstance(chan, discord.TextChannel):
        try:
            await chan.send(note)
        except discord.HTTPException:
            pass
    try:
        where = chan.mention if isinstance(chan, discord.TextChannel) else "its channel"
        await new_owner.send(
            f"👑 You now own **Custom #{custom_id} — {c.name}** in "
            f"**{itx.guild.name}** (handed over by {itx.user.display_name}).\n"
            f"You can start, force start, end, transfer or delete it from "
            f"**Admin panel → Manage customs**, or in {where}."
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
        raise BotError("No queue for this custom.")
    return q


async def _players_meta(ids: list[int]) -> list[dict]:
    async with SessionLocal() as s:
        out = []
        for uid in ids:
            u = await s.get(User, uid)
            out.append({"user_id": uid,
                        "cur_rr": u.cur_rr if u else None,
                        "peak_rank": u.peak_rank if u else None})
        return out


async def _run_draft(guild, channel, custom, match_id, cap_a, cap_b, pool, first_side):
    """Draft the non-captain players, in the custom's configured order."""
    draft = DraftController(match_id, cap_a, cap_b, pool,
                            mode=custom.draft_mode, first=first_side)

    @flow_step(channel, "the map veto")
    async def after_draft():
        await _run_veto(guild, channel, custom, match_id, draft, cap_a, cap_b)

    if draft.done:                      # 1v1: nothing to draft
        await draft.persist_teams()
        await channel.send(embed=draft.embed())
        await after_draft()
        return
    dview = DraftView(draft, after_draft, guild=guild)
    dview.channel = channel
    dview.message = await channel.send(embed=draft.embed(), view=dview)
    dview.arm()  # start the per-turn auto-pick timer


async def _run_veto(guild, channel, custom, match_id, draft, cap_a, cap_b):
    import json

    pool = json.loads(custom.map_pool)
    veto_ctl = VetoController(match_id, custom.format, pool, cap_a, cap_b)
    ACTIVE_VETO[match_id] = veto_ctl
    # Voice is a convenience, the veto is the match. A server that can't take two
    # more channels (category full, missing Manage Channels) must not strand the
    # match between the draft and the veto, so this failure is reported, not raised.
    try:
        await voice.setup_team_vcs(guild, custom, draft.team["A"], draft.team["B"],
                                   cap_a=cap_a, cap_b=cap_b)
    except discord.HTTPException as e:
        log.warning("team VCs for custom %s failed: %s", custom.custom_id, e)
        await channel.send(
            f"⚠️ Couldn't create the team voice channels — `{e.text or e}`. "
            f"Carrying on with the veto; make them by hand or free up the "
            f"customs category, then start the next one."
        )
    async with SessionLocal() as s:
        m = await s.get(Match, match_id)
        m.state = "veto"
        await s.commit()
    view = VetoView(veto_ctl)
    view.channel = channel

    @flow_step(channel, "the side pick")
    async def _finish():
        await _run_side_pick(guild, channel, custom, match_id, veto_ctl, cap_a, cap_b)

    view.on_done = _finish
    view.message = await channel.send(embed=veto_ctl.embed(), view=view)
    view.arm()  # start the per-turn auto-pick timer


async def _run_side_pick(guild, channel, custom, match_id, veto_ctl, cap_a, cap_b):
    """Attack or defence on the decider, chosen by the team that didn't ban it
    away. Straight to the lobby if the veto had no sided step to derive it from."""
    side = veto_ctl.side_choice_side
    if side is None:
        return await finish_veto(guild, channel, custom, match_id)
    captain_id = cap_a if side == "A" else cap_b
    decider = veto_ctl.decider_map

    @flow_step(channel, "the match lobby")
    async def _done(choice: str, auto: bool):
        async with SessionLocal() as s:
            m = await s.get(Match, match_id)
            if m:
                m.side_map = decider
                m.side_pick = choice
                m.side_pick_side = side
                await s.commit()
        on_map = f" on **{decider}**" if decider else ""
        note = " _(auto)_" if auto else ""
        await channel.send(
            f"🎯 Team {side} starts **{choice.title()}**{on_map}{note}."
        )
        await finish_veto(guild, channel, custom, match_id)

    view = SidePickView(match_id, side, captain_id, decider, _done)
    view.channel = channel
    view.message = await channel.send(embed=view.embed(), view=view)
    view.arm()


async def build_lobby_embed(guild: discord.Guild, custom_id: int) -> discord.Embed | None:
    """The match lobby, rebuilt from the DB.

    Read from storage rather than the in-memory controllers so the lobby's
    buttons can redraw it at any time — including after a bot restart, when the
    draft/veto controllers are long gone.
    """
    from bot.db.models import MapVeto

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

    def _squad(side: str) -> str:
        cap = caps.get(side)
        # captain first, then the rest
        ids = sorted(squads[side], key=lambda u: (u != cap, u))
        return "\n".join(f"{'👑 ' if u == cap else ''}<@{u}>" for u in ids) or "—"

    e = discord.Embed(
        title=f"🏁 {c.name} — Match #{c.match_id} ({c.format})", color=VAL_RED
    )
    e.add_field(name="🟥 Team A", value=_squad("A"), inline=True)
    e.add_field(name="🟦 Team B", value=_squad("B"), inline=True)
    e.add_field(name="🗺 Maps", value=", ".join(maps) or "—", inline=False)
    if m and m.side_pick and m.side_pick_side:
        other = "B" if m.side_pick_side == "A" else "A"
        flip = "defence" if m.side_pick == "attack" else "attack"
        e.add_field(
            name="🎯 Sides" + (f" — {m.side_map}" if m.side_map else ""),
            value=f"Team {m.side_pick_side} **{m.side_pick}** · "
                  f"Team {other} **{flip}**",
            inline=False,
        )
    e.add_field(
        name="🔑 Party code",
        value=f"`{m.party_code}`" if m and m.party_code else "_not set yet_",
        inline=True,
    )
    vcs = " / ".join(x.mention for x in voice.team_vcs(guild, c) if x)
    if vcs:
        e.add_field(name="🔊 Voice", value=vcs, inline=True)
    e.set_footer(text="Anyone playing this custom can set the code or end the match.")
    return e


async def finish_veto(guild, channel, custom, match_id):
    """Veto done → mark the match live and post the final lobby for everyone."""
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
        await channel.send(embed=e, view=lobby_view(custom.custom_id))


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
        raise BotError(
            f"A ready check is running on Custom #{custom_id}. Wait for it, or "
            f"use **Start** / **Force start** to cut it short."
        )
    if c.state in ("captains", "veto", "live"):
        raise BotError(
            f"Custom #{custom_id} already has a match in progress (state: {c.state}). "
            "Finish it, or run `/custom delete` to reset and start over."
        )
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
            raise BotError(
                f"Manual start needs an even number of players ≥ 2 (have {n})."
            )
    elif len(member_ids) < q.size:
        raise BotError(
            f"Queue not full ({len(member_ids)}/{q.size}). "
            "Use force-start to begin with the current players."
        )

    if captains == "manual":
        if not manual:
            raise BotError("Manual captains: provide both captains.")
        if manual[0] == manual[1]:
            raise BotError("Captains must be two different players.")
        if not set(manual) <= set(member_ids):
            raise BotError("Both captains must be registered in this custom.")

    async with SessionLocal() as s:
        match = Match(guild_id=guild.id, custom_id=custom_id, format=c.format,
                      state="captains", created_by=actor_id)
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

    players_meta = await _players_meta(member_ids)
    cap_a, cap_b = draft_svc.choose_captains(captains, players_meta, manual=manual)
    pool = [u for u in member_ids if u not in (cap_a, cap_b)]
    per_side = len(member_ids) // 2

    # All match flow (toss, draft, ban/pick veto, sides, lobby) goes in the
    # custom's own channel.
    channel = guild.get_channel(c.reg_channel) if c.reg_channel else None
    if channel is None:
        raise BotError("This custom has no channel left to run the match in.")

    # Let the two captains type in the custom channel; everyone else stays read-only
    # (admins and the owner already got write access when the channel was made).
    for cap_id in (cap_a, cap_b):
        await allow_write(channel, guild.get_member(cap_id), reason="captain")

    await channel.send(
        f"🎬 **Match #{match_id}** ({per_side}v{per_side}) — "
        f"captains <@{cap_a}> (A) vs <@{cap_b}> (B) "
        f"({draft_svc.CAPTAIN_METHOD_LABEL.get(captains, captains)})."
    )
    if subs:
        await channel.send(
            "🪑 **Subs (not in this match):** "
            + ", ".join(f"<@{u}>" for u in subs)
            + " — you signed up after the seats filled."
        )

    if not pool:
        # 1v1: there is nobody to draft, so a toss for pick order decides nothing.
        await _run_draft(guild, channel, c, match_id, cap_a, cap_b, pool, "A")
        return match_id, channel, cap_a, cap_b, per_side

    # Coin toss first: a random captain calls it, the winner takes first or
    # second pick, and that decides who opens the draft.
    coin = CoinflipController(match_id, cap_a, cap_b)

    @flow_step(channel, "the draft")
    async def after_coin(first_side: str):
        async with SessionLocal() as s:
            m = await s.get(Match, match_id)
            if m:
                m.first_pick_side = first_side
                await s.commit()
        await _run_draft(guild, channel, c, match_id, cap_a, cap_b, pool, first_side)

    cview = CoinflipView(coin, after_coin)
    cview.channel = channel
    cview.message = await channel.send(embed=coin.embed(), view=cview)
    cview.arm()
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
    from bot.core.permissions import can_manage_custom

    # Starting a match makes several REST calls (channel perms, messages) before
    # it can answer — ack the interaction first or the token expires (10062).
    if not itx.response.is_done():
        await itx.response.defer(ephemeral=True)

    async with SessionLocal() as s:
        c = await custom_svc.get_in_guild(s, custom_id, itx.guild_id)
    if not await can_manage_custom(c, itx.user):
        raise BotError("Only the owner or a superadmin can start this custom.")

    # A manual start overrules a running ready check — that's the whole point of
    # having both ways in.
    await cancel_ready_check(
        custom_id, f"▶️ Cut short — {itx.user.mention} started the match manually."
    )

    manual = None
    if captains == "manual":
        if not (captain_a and captain_b):
            raise BotError("Manual captains: provide both captains.")
        manual = (captain_a.id, captain_b.id)

    match_id, channel, cap_a, cap_b, per_side = await begin_match(
        itx.guild, custom_id, captains=captains, manual=manual,
        allow_partial=allow_partial, actor_id=itx.user.id,
    )
    await itx.followup.send(
        f"Match #{match_id} starting ({per_side}v{per_side}) in {channel.mention}. "
        f"Captains: <@{cap_a}> (A) vs <@{cap_b}> (B).",
        ephemeral=True,
    )


# -------------------------------------------------------------- ready check ---
# Live ready checks, keyed by custom_id. In memory like the other run-of-match
# views — `custom_svc.clear_stale_ready_checks()` un-sticks anything a restart
# stranded in the `ready` state.
ACTIVE_READY: dict[int, ReadyCheckView] = {}

MAX_READY_ROUNDS = 3  # drop-and-refill can't loop forever


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
    if custom_id in ACTIVE_READY:
        raise BotError(f"A ready check is already running on Custom #{custom_id}.")
    if c.state not in ("registration", "full"):
        raise BotError(
            f"Custom #{custom_id} is `{c.state}` — a ready check only makes sense "
            f"before the match starts."
        )
    channel = guild.get_channel(c.reg_channel) if c.reg_channel else None
    if not isinstance(channel, discord.TextChannel):
        raise BotError("This custom has no channel to run a ready check in.")

    r = await custom_svc.roster(custom_id)
    n = len(r.starters)
    if n < 2 or n % 2 != 0:
        raise BotError(
            f"A ready check needs an even number of players ≥ 2 (have {n})."
        )

    deadline = datetime.now(timezone.utc) + timedelta(seconds=settings.ready_check_seconds)
    ctl = ReadyCheckController(custom_id, c.name, r.starters, deadline, round_no)
    view = ReadyCheckView(ctl, None)

    @flow_step(channel, "the match")
    async def on_resolve(timed_out: bool):
        await _resolve_ready_check(guild, custom_id, ctl, view)

    view.on_resolve = on_resolve
    view.channel = channel
    await _set_state(custom_id, "ready")
    view.message = await channel.send(
        content=f"🔔 **Ready check** — {ctl.mentions()}", embed=ctl.embed(), view=view
    )
    view.arm()
    ACTIVE_READY[custom_id] = view
    board.schedule(guild)
    await audit.log(guild.id, actor_id, "ready_check", str(custom_id), round=round_no)
    return (f"🔔 Ready check posted in {channel.mention} — "
            f"{n} player(s) have {settings.ready_check_seconds}s to confirm.")


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
        await outcome("✅ Everyone ready — starting the match.")
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
    await refresh_registration_embed(guild, custom_id)
    board.schedule(guild)

    r = await custom_svc.roster(custom_id)
    dropped = ", ".join(f"<@{u}>" for u in absent)
    await outcome(f"⏳ Not everyone confirmed. Dropped: {dropped}")

    filled = len(r.starters) == r.size
    if filled and ctl.round_no < MAX_READY_ROUNDS:
        await channel.send(
            f"🪑 {dropped} lost their seat — subs moved up. Running ready check "
            f"round **{ctl.round_no + 1}**."
        )
        return await start_ready_check(guild, custom_id, round_no=ctl.round_no + 1)

    await _set_state(custom_id, "full" if filled else "registration")
    board.schedule(guild)
    why = ("no subs were waiting" if not filled
           else f"gave up after {MAX_READY_ROUNDS} rounds")
    await channel.send(
        f"⚠️ **Ready check failed** for Custom #{custom_id} — {why}. "
        f"{len(r.starters)}/{r.size} seats filled; registration is open again. "
        f"An admin can re-run the check or force start."
    )


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
    from bot.core.permissions import can_manage_custom, is_admin

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
) -> None:
    """Any registered player (or admin) sets/updates the party code.

    `announce` posts it as a channel message — used by the slash command. The
    lobby button passes False because it redraws the lobby embed instead.
    """
    if not await can_play_custom(custom_id, itx.user):
        raise BotError("Only players registered for this custom (or an admin) can set the code.")
    match = await active_match_for_custom(custom_id)
    if not match:
        raise BotError("That custom hasn't started a match yet.")
    # The code is echoed into a public channel inside a code span — strip the
    # characters that would let it break out or inject markdown.
    code = "".join(ch for ch in code.strip() if ch.isalnum() or ch in "-_")[:16]
    if not code:
        raise BotError("Party code must be alphanumeric (`-` and `_` allowed).")
    async with SessionLocal() as s:
        m = await s.get(Match, match.match_id)
        m.party_code = code
        c = await s.get(Custom, custom_id)
        chan_id = c.reg_channel
        await s.commit()
    # Post the code openly (visible to everyone) in the custom channel.
    chan = itx.guild.get_channel(chan_id) if chan_id else None
    if announce and chan:
        await chan.send(
            f"🔑 **Party Code — Custom #{custom_id}:** `{code}`  (set by {itx.user.mention})"
        )
    await audit.log(itx.guild_id, itx.user.id, "party_code", str(custom_id))


async def end_custom(itx: discord.Interaction, custom_id: int) -> None:
    """End a match: mark it completed/done, then remove the custom's voice AND
    text channels. Any registered player can end it once it has started.

    The caller must have already answered (or deferred) the interaction — the
    text channel this was clicked in is about to disappear."""
    if not await can_play_custom(custom_id, itx.user):
        raise BotError("Only players registered for this custom (or an admin) can end it.")
    async with SessionLocal() as s:
        c = await s.get(Custom, custom_id)
        if not c:
            raise BotError("Custom not found.")
        if c.state == "done":
            raise BotError("This custom is already ended.")
        if c.state in ("registration", "full"):
            raise BotError("This custom hasn't started yet — delete it instead.")
        if c.match_id:
            m = await s.get(Match, c.match_id)
            if m:
                m.state = "completed"
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
