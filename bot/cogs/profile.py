"""Player profile commands.

One profile, a section per game. Each game that has a rank API works the same
way: submit an identity → an admin approves it → the rank is fetched and kept
fresh. Valorant uses HenrikDev (Riot ID), CS2 uses Faceit (nickname), Dota 2
uses OpenDota (friend id). Steam is a cosmetic handle with no rank attached.
"""
from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot.core import board
from bot.core.embeds import DASH, EMBED_COLOR, game_color, game_mark
from bot.core.errors import BotError
from bot.core.ui import reply
from bot.db import SessionLocal
from bot.db.models import MemberRole, User
from bot.i18n import t
from bot.i18n.translator import L
from bot.services import faceit
from bot.services import games as games_svc
from bot.services import henrik, opendota, rank_sync
from bot.services.identity import faceit_url, normalize_tag, opendota_url, steam_url

log = logging.getLogger("customly.profile")

ROLES = ["Duelist", "Controller", "Initiator", "Sentinel", "Flex"]

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


def _status_suffix(status: str | None) -> str:
    """` (pending review)` / ` (denied)` after an identity — nothing once it's
    approved, since at that point the rank line beneath it says it all."""
    if not status or status == "approved":
        return ""
    return f" ({t(f'profile.status.{status}')})"


# --------------------------------------------------------- per-game values ----
def _valorant_value(u: User) -> str:
    if not u.riot_id:
        return t("profile.not_linked")
    approved = u.riot_status == "approved"
    return t(
        "profile.val.linked",
        riot=u.riot_id, status=_status_suffix(u.riot_status),
        rank=(u.cur_rank or DASH) if approved else DASH,
        rr=(str(u.cur_rr) if u.cur_rr is not None else DASH) if approved else DASH,
        peak=(u.peak_rank or DASH) if approved else DASH,
        role=t(f"profile.role.{u.main_role.lower()}") if u.main_role else DASH,
    )


def _steam_value(u: User) -> str:
    """The Steam handle as a clickable "Steam" link, or plain text if the handle
    isn't something a profile URL can be built from."""
    if not u.steam_id:
        return t("profile.not_linked")
    url = steam_url(u.steam_id)
    return t("profile.steam.link", url=url) if url else t("profile.steam.line", steam=u.steam_id)


def _cs2_value(u: User) -> str:
    if not u.cs2_nick:
        return _steam_value(u)
    line = t("profile.cs2.linked", nick=u.cs2_nick, url=faceit_url(u.cs2_nick),
             status=_status_suffix(u.cs2_status))
    if u.cs2_status == "approved":
        line += "\n" + t(
            "profile.cs2.rank",
            level=str(u.cs2_level) if u.cs2_level is not None else DASH,
            elo=str(u.cs2_elo) if u.cs2_elo is not None else DASH,
        )
    return line


def _dota_value(u: User) -> str:
    if not u.dota_friend_id:
        return _steam_value(u)
    url = opendota_url(u.dota_friend_id)
    line = (t("profile.dota.linked", friend=u.dota_friend_id, url=url,
              status=_status_suffix(u.dota_status)) if url
            else t("profile.dota.linked_plain", friend=u.dota_friend_id,
                   status=_status_suffix(u.dota_status)))
    if u.dota_status == "approved":
        medal = opendota.dota_rank_name(u.dota_rank_tier, u.dota_leaderboard)
        line += "\n" + t("profile.dota.rank", rank=medal or t("profile.dota.unranked"))
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
    e.add_field(name=f"{game_mark('valorant')} {games_svc.game_label('valorant')}",
                value=_valorant_value(u), inline=False)
    e.add_field(name=f"{game_mark('cs2')} {games_svc.game_label('cs2')}",
                value=_cs2_value(u), inline=True)
    e.add_field(name=f"{game_mark('dota2')} {games_svc.game_label('dota2')}",
                value=_dota_value(u), inline=True)
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
        await itx.response.defer(ephemeral=True)
        try:
            account = await henrik.fetch_account(name, riot_tag)
        except henrik.AccountNotFound:
            return await reply(itx, t("error.riot_not_found", tag=tag))
        except henrik.RateLimited:
            return await reply(itx, t("error.riot_rate_limited"))
        except henrik.HenrikTimeout:
            return await reply(itx, t("error.riot_timeout"))
        except henrik.HenrikError:
            return await reply(itx, t("error.riot_unavailable"))

        canonical = f"{account.name}#{account.tag}"
        async with SessionLocal() as s:
            u = await _ensure_player(s, itx.guild_id, itx.user.id)
            resubmit = u.riot_id != canonical or u.riot_status == "denied"
            u.riot_id, u.riot_puuid, u.riot_region = canonical, account.puuid, account.region
            if resubmit:
                u.riot_status = "pending"
                u.riot_reviewed_by = u.riot_reviewed_at = None
                u.cur_rank = u.cur_rr = u.peak_rank = None
                u.rank_updated_at = None
            if main_role:
                u.main_role = main_role.value
            await s.commit()
        log.info("register: user %s submitted %s (resubmit=%s)", itx.user.id, canonical, resubmit)
        if resubmit:
            board.schedule(itx.guild)  # the staff boards count pending approvals
        msg_key = "profile.register.pending" if resubmit else "profile.register.unchanged"
        await reply(itx, t(msg_key, tag=canonical))

    # --------------------------------------------------------- CS2 (Faceit) --
    @app_commands.command(description=L("cmd.register_cs2.desc"))
    @app_commands.describe(faceit_nickname=L("cmd.register_cs2.nick"))
    async def register_cs2(self, itx: discord.Interaction, faceit_nickname: str):
        nick = faceit_nickname.strip()
        if not nick:
            return await reply(itx, t("profile.cs2.empty"))
        await itx.response.defer(ephemeral=True)
        try:
            player = await faceit.fetch_player(nick)
        except faceit.FaceitNotConfigured:
            return await reply(itx, t("error.faceit_unconfigured"))
        except faceit.AccountNotFound:
            return await reply(itx, t("error.faceit_not_found", nick=nick))
        except faceit.RateLimited:
            return await reply(itx, t("error.faceit_rate_limited"))
        except faceit.FaceitTimeout:
            return await reply(itx, t("error.faceit_timeout"))
        except faceit.FaceitError:
            return await reply(itx, t("error.faceit_unavailable"))

        async with SessionLocal() as s:
            u = await _ensure_player(s, itx.guild_id, itx.user.id)
            resubmit = u.cs2_faceit_id != player.player_id or u.cs2_status == "denied"
            u.cs2_nick, u.cs2_faceit_id = player.nickname, player.player_id
            if resubmit:
                u.cs2_status = "pending"
                u.cs2_reviewed_by = u.cs2_reviewed_at = None
                u.cs2_level = u.cs2_elo = u.cs2_updated_at = None
            await s.commit()
        log.info("register_cs2: user %s submitted %s (resubmit=%s)",
                 itx.user.id, player.nickname, resubmit)
        if resubmit:
            board.schedule(itx.guild)  # the staff boards count pending approvals
        msg_key = "profile.cs2.pending" if resubmit else "profile.cs2.unchanged"
        await reply(itx, t(msg_key, nick=player.nickname))

    # ---------------------------------------------------------- Dota (OpenDota)
    @app_commands.command(description=L("cmd.register_dota.desc"))
    @app_commands.describe(friend_id=L("cmd.register_dota.friend"))
    async def register_dota(self, itx: discord.Interaction, friend_id: str):
        raw = friend_id.strip()
        if not raw.isdigit():
            return await reply(itx, t("error.dota_bad_id"))
        await itx.response.defer(ephemeral=True)
        try:
            player = await opendota.fetch_player(int(raw))
        except opendota.AccountNotFound:
            return await reply(itx, t("error.dota_not_found", friend=raw))
        except opendota.RateLimited:
            return await reply(itx, t("error.dota_rate_limited"))
        except opendota.DotaTimeout:
            return await reply(itx, t("error.dota_timeout"))
        except opendota.DotaError:
            return await reply(itx, t("error.dota_unavailable"))

        async with SessionLocal() as s:
            u = await _ensure_player(s, itx.guild_id, itx.user.id)
            resubmit = u.dota_friend_id != raw or u.dota_status == "denied"
            u.dota_friend_id = raw
            if resubmit:
                u.dota_status = "pending"
                u.dota_reviewed_by = u.dota_reviewed_at = None
                u.dota_rank_tier = u.dota_leaderboard = u.dota_updated_at = None
            await s.commit()
        log.info("register_dota: user %s submitted %s (resubmit=%s)", itx.user.id, raw, resubmit)
        if resubmit:
            board.schedule(itx.guild)  # the staff boards count pending approvals
        msg_key = "profile.dota.pending" if resubmit else "profile.dota.unchanged"
        await reply(itx, t(msg_key, friend=raw))

    # ------------------------------------------------------ Steam (cosmetic) --
    @app_commands.command(description=L("cmd.link.desc"))
    @app_commands.describe(steam=L("cmd.link.steam"))
    async def link(self, itx: discord.Interaction, steam: str):
        steam = steam.strip()
        if not steam:
            return await reply(itx, t("profile.link.empty"))
        async with SessionLocal() as s:
            u = await _ensure_player(s, itx.guild_id, itx.user.id)
            u.steam_id = steam[:64]
            await s.commit()
        await reply(itx, t("profile.link.done", steam=steam[:64]))

    @app_commands.command(description=L("cmd.setmain.desc"))
    @app_commands.describe(game=L("cmd.setmain.game"))
    @app_commands.choices(game=_GAME_CHOICES)
    async def setmain(self, itx: discord.Interaction, game: app_commands.Choice[str]):
        async with SessionLocal() as s:
            u = await _ensure_player(s, itx.guild_id, itx.user.id)
            u.main_game = game.value
            await s.commit()
        await reply(itx, t("profile.main.done", game=games_svc.game_label(game.value)))

    # ------------------------------------------------------------ refresh ----
    @app_commands.command(description=L("cmd.profile.refresh.desc"))
    async def refresh_rank(self, itx: discord.Interaction):
        async with SessionLocal() as s:
            u = await s.get(User, itx.user.id)
        approved = bool(u) and any(
            getattr(u, f) == "approved"
            for f in ("riot_status", "cs2_status", "dota_status")
        )
        if not approved:
            return await reply(itx, t("profile.refresh.not_approved"))
        await itx.response.defer(ephemeral=True)
        log.info("refresh_rank: manual refresh requested by user %s", itx.user.id)
        await rank_sync.refresh_all(itx.user.id, force=True)
        await reply(itx, t("profile.refresh.done_all"))

    # ------------------------------------------------------------ unlink -----
    @app_commands.command(description=L("cmd.unlink.desc"))
    @app_commands.describe(what=L("cmd.unlink.what"))
    @app_commands.choices(what=[
        app_commands.Choice(name=L("profile.unlink.opt.valorant"), value="valorant"),
        app_commands.Choice(name=L("profile.unlink.opt.cs2"), value="cs2"),
        app_commands.Choice(name=L("profile.unlink.opt.dota"), value="dota2"),
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
            elif what.value == "cs2":
                if not u.cs2_nick:
                    return await reply(itx, t("profile.unlink.nothing"))
                u.cs2_nick = u.cs2_faceit_id = None
                u.cs2_status = u.cs2_reviewed_by = u.cs2_reviewed_at = None
                u.cs2_level = u.cs2_elo = u.cs2_updated_at = None
            elif what.value == "dota2":
                if not u.dota_friend_id:
                    return await reply(itx, t("profile.unlink.nothing"))
                u.dota_friend_id = None
                u.dota_status = u.dota_reviewed_by = u.dota_reviewed_at = None
                u.dota_rank_tier = u.dota_leaderboard = u.dota_updated_at = None
            else:  # steam
                if not u.steam_id:
                    return await reply(itx, t("profile.unlink.nothing"))
                u.steam_id = None
            await s.commit()
        log.info("unlink: user %s cleared %s", itx.user.id, what.value)
        await reply(itx, t("profile.unlink.done", what=what.name))

    @app_commands.command(description=L("cmd.profile.unregister.desc"))
    async def unregister(self, itx: discord.Interaction):
        """Legacy alias — clears the Valorant Riot ID only."""
        async with SessionLocal() as s:
            u = await s.get(User, itx.user.id)
            if not u or not u.riot_id:
                return await reply(itx, t("profile.none"))
            u.riot_id = u.riot_puuid = u.riot_region = None
            u.riot_status = u.riot_reviewed_by = u.riot_reviewed_at = None
            u.cur_rank = u.cur_rr = u.peak_rank = u.rank_updated_at = None
            await s.commit()
        await reply(itx, t("profile.unregister.done"))

    # ------------------------------------------------------------ view -------
    @app_commands.command(description=L("cmd.profile.view.desc"))
    async def profile(self, itx: discord.Interaction, member: discord.Member | None = None):
        member = member or itx.user
        async with SessionLocal() as s:
            u = await s.get(User, member.id)
        if not u or not (u.riot_id or u.cs2_nick or u.dota_friend_id
                         or u.steam_id or u.main_game):
            return await reply(itx, t("profile.none"))
        # Deliberately public and permanent: a profile is a durable reference
        # teammates check when picking captains. Refreshing can hit the network,
        # so defer first.
        await itx.response.defer()
        await rank_sync.refresh_all(member.id)
        async with SessionLocal() as s:
            u = await s.get(User, member.id) or u
        await itx.followup.send(embed=_profile_embed(member, u))


async def setup(bot: commands.Bot):
    await bot.add_cog(ProfileCog(bot))
