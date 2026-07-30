"""Voice channel orchestration tied to the match/veto lifecycle."""
from __future__ import annotations

import discord

from bot.db.models import Custom


async def setup_team_vcs(
    guild: discord.Guild,
    custom: Custom,
    team_a: list[int],
    team_b: list[int],
) -> dict[str, discord.VoiceChannel]:
    """Create team_a_<id> / team_b_<id> under the Customs category, then do a
    ONE-TIME move of already-connected players into their team VC. After this,
    players may leave/rejoin freely — they are never auto-moved again.

    The channels are open: anyone may connect, so friends and observers just
    join, with no permission grants to manage."""
    category = guild.get_channel(custom.vc_category) if custom.vc_category else None
    category = category if isinstance(category, discord.CategoryChannel) else None

    vcs: dict[str, discord.VoiceChannel] = {}
    for side in ("a", "b"):
        vcs[side] = await guild.create_voice_channel(
            f"team_{side}_{custom.custom_id}",
            category=category,
            reason=f"custom {custom.custom_id} start",
        )

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


async def teardown_vcs(guild: discord.Guild, custom_id: int, disconnect: bool = True) -> None:
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
    for name in (f"team_a_{custom_id}", f"team_b_{custom_id}", f"staging_{custom_id}"):
        vc = discord.utils.get(guild.voice_channels, name=name)
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
