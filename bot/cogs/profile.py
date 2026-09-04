"""Player profile commands.

One profile, a section per game: Valorant keeps the Riot ID + rank/role it
always had (the only game with an API wired up), while CS2 and Dota 2 hold a
Steam handle the player links themselves. The card's accent follows the
player's main game, if they've set one.
"""
from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.embeds import DASH, EMBED_COLOR, game_color, game_mark
from bot.core.errors import BotError
from bot.core.ui import reply
from bot.db import SessionLocal
from bot.db.models import MemberRole, User
from bot.i18n import t
from bot.i18n.translator import L
from bot.services import games as games_svc
from bot.services import henrik, rank_sync
from bot.services.identity import normalize_tag

log = logging.getLogger("customly.profile")

ROLES = ["Duelist", "Controller", "Initiator", "Sentinel", "Flex"]

# Game choices, lazily labelled (labels are resolved per-interaction, not at
# import, before the guild's language is known).
_GAME_CHOICES = [
    app_commands.Choice(name=L(games_svc.GAME_KEY[g]), value=g)
    for g in games_svc.GAMES
]


async def _ensure_player(s, guild_id: int, user_id: int) -> User:
    """Fetch (or create) the User row and make sure they hold the base player
    role — every identity command is also a first-contact for the player."""
    u = await s.get(User, user_id)
    if not u:
        u = User(user_id=user_id)
        s.add(u)
    if not await s.get(MemberRole, (guild_id, user_id, "player")):
        s.add(MemberRole(guild_id=guild_id, user_id=user_id, role="player"))
    return u


def _valorant_value(u: User) -> str:
    if not u.riot_id:
        return t("profile.not_linked")
    approved = u.riot_status == "approved"
    return t(
        "profile.val.linked",
        riot=u.riot_id,
        status=t(f"profile.status.{u.riot_status}") if u.riot_status else DASH,
        rank=(u.cur_rank or DASH) if approved else DASH,
        rr=(str(u.cur_rr) if u.cur_rr is not None else DASH) if approved else DASH,
        peak=(u.peak_rank or DASH) if approved else DASH,
        role=t(f"profile.role.{u.main_role.lower()}") if u.main_role else DASH,
    )


def _steam_value(u: User, *, with_friend: bool) -> str:
    if not u.steam_id:
        return t("profile.not_linked")
    line = t("profile.steam.line", steam=u.steam_id)
    if with_friend and u.dota_friend_id:
        line += "\n" + t("profile.dota.friend", friend=u.dota_friend_id)
    return line


def _profile_embed(member: discord.Member, u: User) -> discord.Embed:
    main = u.main_game if u.main_game in games_svc.GAMES else None
    e = discord.Embed(
        title=t("profile.title", name=member.display_name),
        description=(
            t("profile.header_main", mark=game_mark(main),
              game=games_svc.game_label(main), wins=u.wins)
            if main else t("profile.header_nomain", wins=u.wins)
        ),
        color=game_color(main) if main else EMBED_COLOR,
    )
    e.add_field(
        name=f"{game_mark('valorant')} {games_svc.game_label('valorant')}",
        value=_valorant_value(u), inline=False,
    )
    e.add_field(
        name=f"{game_mark('cs2')} {games_svc.game_label('cs2')}",
        value=_steam_value(u, with_friend=False), inline=True,
    )
    e.add_field(
        name=f"{game_mark('dota2')} {games_svc.game_label('dota2')}",
        value=_steam_value(u, with_friend=True), inline=True,
    )
    return e


class ProfileCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # --------------------------------------------------------- Valorant ------
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
            u = await _ensure_player(s, itx.guild_id, itx.user.id)
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
            # Only the Riot identity resets — main_role, wins, Steam and the
            # player MemberRole are earned/kept independently.
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

    # ----------------------------------------------------- CS2 / Dota 2 ------
    @app_commands.command(description=L("cmd.link.desc"))
    @app_commands.describe(steam=L("cmd.link.steam"), dota_friend_id=L("cmd.link.friend"))
    async def link(self, itx: discord.Interaction, steam: str,
                   dota_friend_id: str | None = None):
        """Link a Steam handle — it covers both CS2 and Dota 2."""
        steam = steam.strip()
        if not steam:
            return await reply(itx, t("profile.link.empty"))
        async with SessionLocal() as s:
            u = await _ensure_player(s, itx.guild_id, itx.user.id)
            u.steam_id = steam[:64]
            if dota_friend_id is not None:
                u.dota_friend_id = dota_friend_id.strip()[:32] or None
            await s.commit()
        log.info("link: user %s linked steam", itx.user.id)
        await reply(itx, t("profile.link.done", steam=steam[:64]))

    @app_commands.command(description=L("cmd.unlink.desc"))
    @app_commands.describe(what=L("cmd.unlink.what"))
    @app_commands.choices(what=[
        app_commands.Choice(name=L("profile.unlink.opt.valorant"), value="valorant"),
        app_commands.Choice(name=L("profile.unlink.opt.steam"), value="steam"),
    ])
    async def unlink(self, itx: discord.Interaction, what: app_commands.Choice[str]):
        async with SessionLocal() as s:
            u = await s.get(User, itx.user.id)
            if not u:
                return await reply(itx, t("profile.none"))
            if what.value == "valorant":
                if not u.riot_id:
                    return await reply(itx, t("profile.unlink.nothing"))
                u.riot_id = u.riot_puuid = u.riot_region = None
                u.riot_status = u.riot_reviewed_by = u.riot_reviewed_at = None
                u.cur_rank = u.cur_rr = u.peak_rank = u.rank_updated_at = None
            else:  # steam (CS2 + Dota 2)
                if not u.steam_id:
                    return await reply(itx, t("profile.unlink.nothing"))
                u.steam_id = u.dota_friend_id = None
            await s.commit()
        log.info("unlink: user %s cleared %s", itx.user.id, what.value)
        await reply(itx, t("profile.unlink.done", what=what.name))

    @app_commands.command(description=L("cmd.setmain.desc"))
    @app_commands.describe(game=L("cmd.setmain.game"))
    @app_commands.choices(game=_GAME_CHOICES)
    async def setmain(self, itx: discord.Interaction, game: app_commands.Choice[str]):
        async with SessionLocal() as s:
            u = await _ensure_player(s, itx.guild_id, itx.user.id)
            u.main_game = game.value
            await s.commit()
        await reply(itx, t("profile.main.done", game=games_svc.game_label(game.value)))

    # ------------------------------------------------------------ view -------
    @app_commands.command(description=L("cmd.profile.view.desc"))
    async def profile(self, itx: discord.Interaction, member: discord.Member | None = None):
        member = member or itx.user
        async with SessionLocal() as s:
            u = await s.get(User, member.id)
        if not u or not (u.riot_id or u.steam_id or u.main_game):
            return await reply(itx, t("profile.none"))
        # Deliberately public and permanent, unlike every other reply() /
        # Screen in the bot: a profile is a durable reference teammates check
        # when picking captains, not a transient confirmation. Refreshing an
        # approved player's rank can hit the network, so defer first.
        await itx.response.defer()
        if u.riot_status == "approved":
            u = await rank_sync.refresh_rank(member.id) or u
        await itx.followup.send(embed=_profile_embed(member, u))


async def setup(bot: commands.Bot):
    await bot.add_cog(ProfileCog(bot))
