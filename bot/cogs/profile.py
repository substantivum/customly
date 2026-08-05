"""Player profile commands."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.embeds import DASH, EMBED_COLOR
from bot.core.errors import BotError
from bot.core.ui import reply
from bot.db import SessionLocal
from bot.db.models import MemberRole, User
from bot.i18n import t
from bot.i18n.translator import L
from bot.services.identity import normalize_tag

ROLES = ["Duelist", "Controller", "Initiator", "Sentinel", "Flex"]


class ProfileCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(description=L("cmd.profile.register.desc"))
    @app_commands.describe(
        riot_id=L("cmd.profile.register.riot_id"),
        main_role=L("cmd.profile.register.main_role"),
        cur_rank=L("cmd.profile.register.cur_rank"),
        cur_rr=L("cmd.profile.register.cur_rr"),
        peak_rank=L("cmd.profile.register.peak_rank"),
    )
    @app_commands.choices(
        main_role=[
            app_commands.Choice(name=L(f"profile.role.{r.lower()}"), value=r)
            for r in ROLES
        ]
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
        await reply(itx, t("profile.registered", tag=tag))

    @app_commands.command(description=L("cmd.profile.view.desc"))
    async def profile(self, itx: discord.Interaction, member: discord.Member | None = None):
        member = member or itx.user
        async with SessionLocal() as s:
            u = await s.get(User, member.id)
        if not u or not u.riot_id:
            return await reply(itx, t("profile.none"))
        e = discord.Embed(title=t("profile.title", name=member.display_name),
                          color=EMBED_COLOR)
        e.add_field(name=t("profile.riot_id"), value=u.riot_id)
        e.add_field(name=t("profile.main_role"),
                    value=t(f"profile.role.{u.main_role.lower()}") if u.main_role else DASH)
        e.add_field(name=t("profile.rank"), value=u.cur_rank or DASH)
        e.add_field(name=t("profile.rr"),
                    value=str(u.cur_rr) if u.cur_rr is not None else DASH)
        e.add_field(name=t("profile.peak"), value=u.peak_rank or DASH)
        e.add_field(name=t("profile.elo"), value=str(u.elo))
        await itx.response.send_message(embed=e)


async def setup(bot: commands.Bot):
    await bot.add_cog(ProfileCog(bot))
