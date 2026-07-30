"""Custom sessions: creation, registration with overlap checks, ownership,
deletion/prune with the live-occupancy guard."""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import discord
from sqlalchemy import delete, select

from bot.core.errors import Blocked, BotError, Conflict, NotFound
from bot.db import SessionLocal
from bot.services import veto as veto_svc
from bot.services.bans import is_banned as _is_banned
from bot.db.models import (
    Custom,
    CustomRegistration,
    Map,
    Queue,
    QueueMember,
)

DURATION = {"BO1": 1, "BO3": 3, "BO5": 5}
MIN_TEAM, MAX_TEAM = 1, 5  # 1v1 .. 5v5
ACTIVE_STATES = ("registration", "full", "veto", "live")


# --------------------------------------------------------------- creation ---
async def create_custom(
    *,
    guild_id: int,
    owner_id: int,
    name: str,
    fmt: str,
    start_time: datetime,
    maps: list[str],
    vc_category: int | None,
    config_chan: int | None,
    team_size: int = 5,
) -> Custom:
    fmt = fmt.upper()
    if fmt not in DURATION:
        raise BotError("Format must be BO1, BO3 or BO5.")
    if not (MIN_TEAM <= team_size <= MAX_TEAM):
        raise BotError("Team size must be between 1 and 5 (1v1 to 5v5).")
    async with SessionLocal() as s:
        # current enabled pool (preserve original case for fallback)
        rows = await s.execute(
            select(Map.name).where(Map.guild_id == guild_id, Map.enabled.is_(True))
        )
        enabled_names = [r[0] for r in rows.all()]
        enabled = {n.lower() for n in enabled_names}
        chosen = [m.strip() for m in maps if m.strip()]
        if not chosen:
            # No maps given → use the whole enabled (seeded) pool.
            if not enabled_names:
                raise BotError(
                    "No maps specified and the server has no enabled map pool. "
                    "Run `/maps seed` first, or pass maps."
                )
            chosen = list(enabled_names)
        elif enabled:  # maps given and a pool exists → enforce membership
            bad = [m for m in chosen if m.lower() not in enabled]
            if bad:
                raise BotError(f"Maps not in enabled pool: {', '.join(bad)}")
        need = veto_svc.MIN_POOL[fmt]
        if len(chosen) < need:
            raise BotError(
                f"{fmt} needs at least {need} maps in the pool (got {len(chosen)})."
            )

        c = Custom(
            guild_id=guild_id,
            name=name,
            format=fmt,
            duration_h=DURATION[fmt],
            team_size=team_size,
            map_pool=json.dumps(chosen),
            start_time=start_time,
            vc_category=vc_category,
            config_chan=config_chan,
            owner_id=owner_id,
            created_by=owner_id,
            state="registration",
        )
        s.add(c)
        await s.flush()  # get custom_id
        s.add(Queue(guild_id=guild_id, custom_id=c.custom_id,
                    type=f"{team_size}v{team_size}", size=team_size * 2,
                    format=fmt, open=True))
        await s.commit()
        await s.refresh(c)
        return c


# ----------------------------------------------------------- registration ---
async def user_active_customs(s, user_id: int) -> list[Custom]:
    rows = await s.execute(
        select(Custom)
        .join(CustomRegistration, CustomRegistration.custom_id == Custom.custom_id)
        .where(
            CustomRegistration.user_id == user_id,
            Custom.state.in_(ACTIVE_STATES),
        )
    )
    return [r[0] for r in rows.all()]


def _overlaps(a_start: datetime, a_dur: int, b_start: datetime, b_dur: int) -> bool:
    a_end = a_start + timedelta(hours=a_dur)
    b_end = b_start + timedelta(hours=b_dur)
    return a_start < b_end and b_start < a_end


async def find_conflict(s, user_id: int, target: Custom) -> Custom | None:
    for c in await user_active_customs(s, user_id):
        if c.custom_id == target.custom_id:
            continue
        if _overlaps(target.start_time, target.duration_h, c.start_time, c.duration_h):
            return c
    return None


async def get_in_guild(s, custom_id: int, guild_id: int | None) -> Custom:
    """Load a custom, refusing ids that belong to another guild.

    `custom_id` is a global autoincrement, so ids from other servers are
    trivially guessable — every lookup driven by user input must be scoped.
    """
    c = await s.get(Custom, custom_id)
    if not c or (guild_id is not None and c.guild_id != guild_id):
        raise NotFound("Custom not found.")
    return c


async def register(custom_id: int, user_id: int, guild_id: int | None = None) -> Custom:
    async with SessionLocal() as s:
        c = await get_in_guild(s, custom_id, guild_id)
        if await _is_banned(c.guild_id, user_id):
            raise BotError("You are banned from joining games in this server.")
        if c.state != "registration":
            raise BotError(f"Custom #{custom_id} is not open for registration.")
        clash = await find_conflict(s, user_id, c)
        if clash:
            end = clash.start_time + timedelta(hours=clash.duration_h)
            raise Conflict(
                f"Conflicts with **{clash.name}** "
                f"({clash.start_time:%H:%M}–{end:%H:%M})."
            )
        exists = await s.get(CustomRegistration, (custom_id, user_id))
        if exists:
            raise BotError("Already registered.")
        s.add(CustomRegistration(custom_id=custom_id, user_id=user_id))
        # mirror into the queue
        q = (await s.execute(select(Queue).where(Queue.custom_id == custom_id))).scalar_one()
        s.add(QueueMember(queue_id=q.queue_id, user_id=user_id))
        await s.commit()
        await s.refresh(c)
        return c


async def leave(custom_id: int, user_id: int, guild_id: int | None = None) -> Custom:
    async with SessionLocal() as s:
        c = await get_in_guild(s, custom_id, guild_id)
        reg = await s.get(CustomRegistration, (custom_id, user_id))
        if reg:
            await s.delete(reg)
        q = (await s.execute(select(Queue).where(Queue.custom_id == custom_id))).scalar_one_or_none()
        if q:
            qm = await s.get(QueueMember, (q.queue_id, user_id))
            if qm:
                await s.delete(qm)
        await s.commit()
        await s.refresh(c)
        return c


async def registrants(custom_id: int) -> list[int]:
    async with SessionLocal() as s:
        rows = await s.execute(
            select(CustomRegistration.user_id).where(
                CustomRegistration.custom_id == custom_id
            )
        )
        return [r[0] for r in rows.all()]


# -------------------------------------------------------------- ownership ---
async def transfer(custom_id: int, new_owner: int) -> Custom:
    async with SessionLocal() as s:
        c = await s.get(Custom, custom_id)
        if not c:
            raise NotFound("Custom not found.")
        c.owner_id = new_owner
        await s.commit()
        await s.refresh(c)
        return c


# ---------------------------------------------------- deletion / guard ------
def is_in_progress(custom: Custom, guild: discord.Guild) -> bool:
    """Both team VCs populated ⇒ a game is live ⇒ protect from teardown."""
    a = discord.utils.get(guild.voice_channels, name=f"team_a_{custom.custom_id}")
    b = discord.utils.get(guild.voice_channels, name=f"team_b_{custom.custom_id}")
    return bool(a and b and len(a.members) > 0 and len(b.members) > 0)


async def _purge_channels(custom: Custom, guild: discord.Guild, force: bool) -> None:
    targets = []
    for vc in guild.voice_channels:
        if vc.name in (
            f"team_a_{custom.custom_id}",
            f"team_b_{custom.custom_id}",
            f"staging_{custom.custom_id}",
        ):
            targets.append(vc)
    if custom.reg_channel:
        ch = guild.get_channel(custom.reg_channel)
        if ch:
            targets.append(ch)
    for vc in targets:
        if force and isinstance(vc, discord.VoiceChannel):
            for m in list(vc.members):
                try:
                    await m.move_to(None)  # disconnect
                except discord.HTTPException:
                    pass
        try:
            await vc.delete(reason="custom deleted")
        except discord.HTTPException:
            pass


async def delete_custom(custom_id: int, guild: discord.Guild, force: bool = False) -> None:
    async with SessionLocal() as s:
        c = await get_in_guild(s, custom_id, guild.id)
        if is_in_progress(c, guild) and not force:
            raise Blocked(
                "Both team VCs are occupied — match in progress. "
                "End it first, or (superadmin) pass force:true."
            )
        await _purge_channels(c, guild, force)
        await s.execute(delete(QueueMember).where(
            QueueMember.queue_id.in_(
                select(Queue.queue_id).where(Queue.custom_id == custom_id)
            )
        ))
        await s.execute(delete(Queue).where(Queue.custom_id == custom_id))
        await s.execute(delete(CustomRegistration).where(
            CustomRegistration.custom_id == custom_id
        ))
        await s.delete(c)
        await s.commit()


async def prune(guild: discord.Guild, force: bool = False) -> tuple[int, list[int]]:
    """Delete all customs in the guild. Returns (deleted_count, skipped_ids)."""
    async with SessionLocal() as s:
        rows = await s.execute(select(Custom).where(Custom.guild_id == guild.id))
        customs = [r[0] for r in rows.all()]
    deleted, skipped = 0, []
    for c in customs:
        try:
            await delete_custom(c.custom_id, guild, force=force)
            deleted += 1
        except Blocked:
            skipped.append(c.custom_id)
    return deleted, skipped
