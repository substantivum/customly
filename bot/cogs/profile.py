"""Player profile commands."""
from __future__ import annotations

import logging

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
from bot.services import henrik, rank_sync
from bot.services.identity import normalize_tag

log = logging.getLogger("customly.profile")

ROLES = ["Duelist", "Controller", "Initiator", "Sentinel", "Flex"]


class ProfileCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(description=L("cmd.profile.register.desc"))
    @app_commands.describe(
        riot_id=L("cmd.profile.register.riot_id"),
        main_role=L("cmd.profile.register.main_role"),
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
    ):
        try:
            tag = normalize_tag(riot_id)
        except BotError as e:
            return await reply(itx, str(e))
        name, _, riot_tag = tag.partition("#")
        # Verifying against HenrikDev can take a few seconds — well past
        # Discord's 3s ack window.
        await itx.response.defer(ephemeral=True)
        try:
            account = await henrik.fetch_account(name, riot_tag)
        except henrik.AccountNotFound:
            log.info("register: %s not found for user %s", tag, itx.user.id)
            return await reply(itx, t("error.riot_not_found", tag=tag))
        except henrik.RateLimited:
            log.info("register: rate limited resolving %s for user %s", tag, itx.user.id)
            return await reply(itx, t("error.riot_rate_limited"))
        except henrik.HenrikTimeout:
            log.info("register: timed out resolving %s for user %s", tag, itx.user.id)
            return await reply(itx, t("error.riot_timeout"))
        except henrik.HenrikError as e:
            log.warning("register: %s unavailable resolving %s for user %s", e, tag, itx.user.id)
            return await reply(itx, t("error.riot_unavailable"))

        canonical = f"{account.name}#{account.tag}"
        async with SessionLocal() as s:
            u = await s.get(User, itx.user.id)
            if not u:
                u = User(user_id=itx.user.id)
                s.add(u)
            # A denial is contestable — resubmitting the identical tag after
            # one must be able to go back to pending, not stay stuck. But
            # re-registering the same tag while already approved (e.g. just
            # to change main_role) must not silently revoke that approval.
            resubmit = u.riot_id != canonical or u.riot_status == "denied"
            u.riot_id, u.riot_puuid, u.riot_region = canonical, account.puuid, account.region
            if resubmit:
                u.riot_status = "pending"
                u.riot_reviewed_by = None
                u.riot_reviewed_at = None
                u.cur_rank = u.cur_rr = u.peak_rank = None
                u.rank_updated_at = None
            if main_role:
                u.main_role = main_role.value
            # everyone is at least a player
            if not await s.get(MemberRole, (itx.guild_id, itx.user.id, "player")):
                s.add(MemberRole(guild_id=itx.guild_id, user_id=itx.user.id, role="player"))
            await s.commit()
        log.info("register: user %s submitted %s (resubmit=%s)",
                 itx.user.id, canonical, resubmit)
        msg_key = "profile.register.pending" if resubmit else "profile.register.unchanged"
        await reply(itx, t(msg_key, tag=canonical))

    @app_commands.command(description=L("cmd.profile.unregister.desc"))
    async def unregister(self, itx: discord.Interaction):
        async with SessionLocal() as s:
            u = await s.get(User, itx.user.id)
            if not u or not u.riot_id:
                return await reply(itx, t("profile.none"))
            # Only the Riot identity resets — main_role, wins, and the
            # player MemberRole are earned independently and stay put.
            u.riot_id = u.riot_puuid = u.riot_region = None
            u.riot_status = u.riot_reviewed_by = u.riot_reviewed_at = None
            u.cur_rank = u.cur_rr = u.peak_rank = u.rank_updated_at = None
            await s.commit()
        log.info("unregister: user %s cleared their riot id", itx.user.id)
        await reply(itx, t("profile.unregister.done"))

    @app_commands.command(description=L("cmd.profile.refresh.desc"))
    async def refresh_rank(self, itx: discord.Interaction):
        async with SessionLocal() as s:
            u = await s.get(User, itx.user.id)
        if not u or not u.riot_id:
            return await reply(itx, t("profile.none"))
        if u.riot_status != "approved":
            return await reply(itx, t("profile.refresh.not_approved"))
        await itx.response.defer(ephemeral=True)
        log.info("refresh_rank: manual refresh requested by user %s", itx.user.id)
        before = u.rank_updated_at
        u = await rank_sync.refresh_rank(itx.user.id, force=True)
        if u and u.rank_updated_at != before:
            await reply(itx, t("profile.refresh.done", rank=u.cur_rank or DASH,
                               rr=str(u.cur_rr) if u.cur_rr is not None else DASH,
                               peak=u.peak_rank or DASH))
        else:
            log.info("refresh_rank: no update landed for user %s", itx.user.id)
            await reply(itx, t("profile.refresh.failed"))

    @app_commands.command(description=L("cmd.profile.view.desc"))
    async def profile(self, itx: discord.Interaction, member: discord.Member | None = None):
        member = member or itx.user
        async with SessionLocal() as s:
            u = await s.get(User, member.id)
        if not u or not u.riot_id:
            return await reply(itx, t("profile.none"))
        # Deliberately public and permanent, unlike every other reply() /
        # Screen in the bot: a profile is a durable reference teammates check
        # when picking captains, not a transient confirmation. Refreshing an
        # approved player's rank can hit the network, so defer first.
        await itx.response.defer()
        if u.riot_status == "approved":
            u = await rank_sync.refresh_rank(member.id) or u
        approved = u.riot_status == "approved"
        e = discord.Embed(title=t("profile.title", name=member.display_name),
                          color=EMBED_COLOR)
        e.add_field(name=t("profile.riot_id"), value=u.riot_id)
        e.add_field(name=t("profile.main_role"),
                    value=t(f"profile.role.{u.main_role.lower()}") if u.main_role else DASH)
        e.add_field(name=t("profile.rank"), value=(u.cur_rank or DASH) if approved else DASH)
        e.add_field(name=t("profile.rr"),
                    value=(str(u.cur_rr) if u.cur_rr is not None else DASH) if approved else DASH)
        e.add_field(name=t("profile.peak"), value=(u.peak_rank or DASH) if approved else DASH)
        e.add_field(name=t("profile.wins"), value=str(u.wins))
        await itx.followup.send(embed=e)


async def setup(bot: commands.Bot):
    await bot.add_cog(ProfileCog(bot))
