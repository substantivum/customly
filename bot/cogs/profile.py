"""Player profile commands."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.embeds import VAL_RED
from bot.core.errors import BotError
from bot.core.ui import reply
from bot.db import SessionLocal
from bot.db.models import MemberRole, User
from bot.services.identity import normalize_tag

ROLES = ["Duelist", "Controller", "Initiator", "Sentinel", "Flex"]


class ProfileCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(description="Register your profile with your Riot ID tag.")
    @app_commands.describe(
        riot_id="Your Riot ID like TenZ#NA1",
        main_role="Optional preferred role",
        cur_rank="Optional, e.g. Ascendant 2",
        cur_rr="Optional rank rating 0-100",
        peak_rank="Optional, e.g. Immortal 1",
    )
    @app_commands.choices(
        main_role=[app_commands.Choice(name=r, value=r) for r in ROLES]
    )
    async def register(
        self,
        itx: discord.Interaction,
        riot_id: str,
        main_role: app_commands.Choice[str] | None = None,
        cur_rank: str | None = None,
        cur_rr: int | None = None,
        peak_rank: str | None = None,
    ):
        try:
            tag = normalize_tag(riot_id)
        except BotError as e:
            return await reply(itx, str(e))
        async with SessionLocal() as s:
            u = await s.get(User, itx.user.id)
            if not u:
                u = User(user_id=itx.user.id)
                s.add(u)
            u.riot_id = tag
            if main_role:
                u.main_role = main_role.value
            u.cur_rank, u.cur_rr, u.peak_rank = cur_rank, cur_rr, peak_rank
            # everyone is at least a player
            if not await s.get(MemberRole, (itx.guild_id, itx.user.id, "player")):
                s.add(MemberRole(guild_id=itx.guild_id, user_id=itx.user.id, role="player"))
            await s.commit()
        await reply(itx, f"Registered as **{tag}** ✅")

    @app_commands.command(description="View a player's profile.")
    async def profile(self, itx: discord.Interaction, member: discord.Member | None = None):
        member = member or itx.user
        async with SessionLocal() as s:
            u = await s.get(User, member.id)
        if not u or not u.riot_id:
            return await reply(itx, "No profile registered.")
        e = discord.Embed(title=f"Profile — {member.display_name}", color=VAL_RED)
        e.add_field(name="Riot ID", value=u.riot_id)
        e.add_field(name="Main role", value=u.main_role or "—")
        e.add_field(name="Rank", value=u.cur_rank or "—")
        e.add_field(name="RR", value=str(u.cur_rr) if u.cur_rr is not None else "—")
        e.add_field(name="Peak", value=u.peak_rank or "—")
        e.add_field(name="Elo", value=str(u.elo))
        await itx.response.send_message(embed=e)


async def setup(bot: commands.Bot):
    await bot.add_cog(ProfileCog(bot))
