"""Reusable orchestration shared by slash commands and the button panel.

Keeping this here (not in a cog) lets both /custom, /match AND the panel views
call the exact same flows without duplication or circular imports.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import discord
from sqlalchemy import select

from bot.config import settings
from bot.core import audit
from bot.core.controllers import CoinflipController, DraftController, VetoController
from bot.core.embeds import VAL_RED, custom_registration_embed
from bot.core.errors import BotError
from bot.core.naming import channel_slug
from bot.core.views import (
    CoinflipView,
    DraftView,
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

# active veto controllers keyed by match_id
ACTIVE_VETO: dict[int, VetoController] = {}


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
    size = db_c.team_size * 2
    msg = await reg.send(embed=custom_registration_embed(db_c, [], size),
                         view=registration_view(db_c.custom_id))
    # Remember the embed so later changes (e.g. an ownership transfer) can
    # redraw it without hunting through the channel's history.
    async with SessionLocal() as s:
        db_c = await s.get(Custom, c.custom_id)
        db_c.reg_message = msg.id
        await s.commit()
        await s.refresh(db_c)
    await audit.log(itx.guild_id, itx.user.id, "custom_create", str(c.custom_id))
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


async def refresh_registration_embed(guild: discord.Guild, custom_id: int) -> None:
    """Redraw the registration embed from the DB (owner, state, registrants)."""
    async with SessionLocal() as s:
        c = await s.get(Custom, custom_id)
        q = (await s.execute(
            select(Queue).where(Queue.custom_id == custom_id)
        )).scalar_one_or_none()
    if not c:
        return
    msg = await _reg_message(guild, c)
    if not msg:
        return
    regs = await custom_svc.registrants(custom_id)
    size = q.size if q else c.team_size * 2
    try:
        await msg.edit(embed=custom_registration_embed(c, regs, size))
    except discord.HTTPException:
        pass


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
    await voice.setup_team_vcs(guild, custom, draft.team["A"], draft.team["B"],
                               cap_a=cap_a, cap_b=cap_b)
    async with SessionLocal() as s:
        m = await s.get(Match, match_id)
        m.state = "veto"
        await s.commit()
    view = VetoView(veto_ctl)
    view.channel = channel

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


async def start_match(
    itx: discord.Interaction,
    custom_id: int,
    captains: str = "random",
    captain_a: discord.Member | None = None,
    captain_b: discord.Member | None = None,
    allow_partial: bool = False,
):
    from bot.core.permissions import can_manage_custom

    # Starting a match makes several REST calls (channel perms, messages) before
    # it can answer — ack the interaction first or the token expires (10062).
    if not itx.response.is_done():
        await itx.response.defer(ephemeral=True)

    async with SessionLocal() as s:
        c = await custom_svc.get_in_guild(s, custom_id, itx.guild_id)
    if not await can_manage_custom(c, itx.user):
        raise BotError("Only the owner or a superadmin can start this custom.")
    if c.state in ("captains", "veto", "live"):
        raise BotError(
            f"Custom #{custom_id} already has a match in progress (state: {c.state}). "
            "Finish it, or run `/custom delete` to reset and start over."
        )

    q = await _queue_for_custom(custom_id)
    member_ids = await queue_svc.members(q.queue_id)

    if allow_partial:
        n = len(member_ids)
        if n < 2 or n % 2 != 0:
            raise BotError(
                f"Manual start needs an even number of players ≥ 2 (have {n})."
            )
    else:
        if len(member_ids) < q.size:
            raise BotError(
                f"Queue not full ({len(member_ids)}/{q.size}). "
                "Use force-start to begin with the current players."
            )
        member_ids = member_ids[: q.size]

    manual = None
    if captains == "manual":
        if not (captain_a and captain_b):
            raise BotError("Manual captains: provide both captains.")
        if captain_a.id == captain_b.id:
            raise BotError("Captains must be two different players.")
        if captain_a.id not in member_ids or captain_b.id not in member_ids:
            raise BotError("Both captains must be registered in this custom.")
        manual = (captain_a.id, captain_b.id)

    async with SessionLocal() as s:
        match = Match(guild_id=itx.guild_id, custom_id=custom_id, format=c.format,
                      state="captains", created_by=itx.user.id)
        s.add(match)
        await s.flush()
        for uid in member_ids:
            s.add(MatchPlayer(match_id=match.match_id, user_id=uid, checked_in=True))
        db_c = await s.get(Custom, custom_id)
        db_c.match_id = match.match_id
        db_c.state = "veto"
        await s.commit()
        match_id = match.match_id

    players_meta = await _players_meta(member_ids)
    cap_a, cap_b = draft_svc.choose_captains(captains, players_meta, manual=manual)
    pool = [u for u in member_ids if u not in (cap_a, cap_b)]
    per_side = len(member_ids) // 2

    guild = itx.guild
    # All match flow (toss, draft, ban/pick veto, sides, lobby) goes in the
    # custom's own channel.
    channel = guild.get_channel(c.reg_channel) if c.reg_channel else itx.channel

    # Let the two captains type in the custom channel; everyone else stays read-only
    # (admins and the owner already got write access when the channel was made).
    for cap_id in (cap_a, cap_b):
        await allow_write(channel, guild.get_member(cap_id), reason="captain")

    await itx.followup.send(
        f"Match #{match_id} starting ({per_side}v{per_side}) in {channel.mention}. "
        f"Captains: <@{cap_a}> (A) vs <@{cap_b}> (B).",
        ephemeral=True,
    )
    await channel.send(
        f"🎬 **Match #{match_id}** ({per_side}v{per_side}) — "
        f"captains <@{cap_a}> (A) vs <@{cap_b}> (B)."
    )

    if not pool:
        # 1v1: there is nobody to draft, so a toss for pick order decides nothing.
        return await _run_draft(guild, channel, c, match_id, cap_a, cap_b, pool, "A")

    # Coin toss first: a random captain calls it, the winner takes first or
    # second pick, and that decides who opens the draft.
    coin = CoinflipController(match_id, cap_a, cap_b)

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
        if c.state == "registration":
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
