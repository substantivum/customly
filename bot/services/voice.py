"""Voice channel orchestration tied to the match/veto lifecycle."""
from __future__ import annotations

import discord

from bot.core.naming import team_vc_name
from bot.db import SessionLocal
from bot.db.models import Custom


def _nick(guild: discord.Guild, user_id: int | None) -> str | None:
    m = guild.get_member(user_id) if user_id else None
    return m.display_name if m else None


def team_vcs(
    guild: discord.Guild, custom: Custom
) -> tuple[discord.VoiceChannel | None, discord.VoiceChannel | None]:
    """The custom's two team VCs.

    Resolved by the ids stored at creation; the `team_<side>_<id>` names are the
    pre-captain-naming scheme and stay as a fallback for customs made before it.
    """
    def _one(chan_id: int | None, legacy: str) -> discord.VoiceChannel | None:
        ch = guild.get_channel(chan_id) if chan_id else None
        if isinstance(ch, discord.VoiceChannel):
            return ch
        ch = discord.utils.get(guild.voice_channels, name=legacy)
        return ch if isinstance(ch, discord.VoiceChannel) else None

    cid = custom.custom_id
    return _one(custom.vc_a, f"team_a_{cid}"), _one(custom.vc_b, f"team_b_{cid}")


async def setup_team_vcs(
    guild: discord.Guild,
    custom: Custom,
    team_a: list[int],
    team_b: list[int],
    cap_a: int | None = None,
    cap_b: int | None = None,
) -> dict[str, discord.VoiceChannel]:
    """Create the two team VCs under the Customs category, then do a ONE-TIME
    move of already-connected players into their team VC. After this, players
    may leave/rejoin freely — they are never auto-moved again.

    Channels are named `<custom>-<side>-<captain nickname>` so a server running
    several customs at once can tell them apart at a glance; their ids are saved
    on the custom so later lookups don't depend on the name.

    The channels are open: anyone may connect, so friends and observers just
    join, with no permission grants to manage."""
    category = guild.get_channel(custom.vc_category) if custom.vc_category else None
    category = category if isinstance(category, discord.CategoryChannel) else None

    caps = {"a": cap_a, "b": cap_b}
    vcs: dict[str, discord.VoiceChannel] = {}
    for side in ("a", "b"):
        vcs[side] = await guild.create_voice_channel(
            team_vc_name(custom.name, side, _nick(guild, caps[side])),
            category=category,
            reason=f"custom {custom.custom_id} start",
        )

    async with SessionLocal() as s:
        db_c = await s.get(Custom, custom.custom_id)
        if db_c:
            db_c.vc_a, db_c.vc_b = vcs["a"].id, vcs["b"].id
            await s.commit()
    custom.vc_a, custom.vc_b = vcs["a"].id, vcs["b"].id

    # one-time move at game start only
    side_of = {uid: "a" for uid in team_a}
    side_of.update({uid: "b" for uid in team_b})
    for uid, side in side_of.items():
        m = guild.get_member(uid)
        if m and m.voice and m.voice.channel:   # only movable if already connected
            try:
                await m.move_to(vcs[side])
            except discord.HTTPException:
                pass
    return vcs


async def teardown_vcs(
    guild: discord.Guild, custom: Custom, disconnect: bool = True
) -> None:
    """Remove the team voice channels for a custom (used on match end).
    Anyone still inside is moved to DEFAULT_VOICE_CHANNEL if configured; otherwise
    they're disconnected."""
    from bot.config import settings

    dest = None
    if settings.default_voice_channel:
        ch = guild.get_channel(settings.default_voice_channel)
        if isinstance(ch, discord.VoiceChannel):
            dest = ch

    # staging_* is no longer created, but old customs may still have one
    staging = discord.utils.get(guild.voice_channels, name=f"staging_{custom.custom_id}")
    for vc in (*team_vcs(guild, custom), staging):
        if not vc:
            continue
        if disconnect:
            for m in list(vc.members):
                try:
                    await m.move_to(dest)  # dest=channel → move; dest=None → disconnect
                except discord.HTTPException:
                    pass
        try:
            await vc.delete(reason="custom ended")
        except discord.HTTPException:
            pass
