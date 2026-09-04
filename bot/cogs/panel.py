"""Control boards — one per tier, one per channel.

`/panel` posts a **live board**: a public message whose embed mirrors the server
state (open games, seats, map pool) and redraws itself whenever anything
changes. Its buttons never touch the board — each opens a *private* screen (see
`bot.core.nav`) that morphs in place as you navigate, so several people can use
one board at the same time.

There are three boards and they are meant to live in three different channels:

    #customs      /panel                 → player board   (everyone)
    #admin-panel  /panel tier:admin      → admin board    (Admin+)
    #super-panel  /panel tier:superadmin → super board    (SuperAdmin)

Set `ADMIN_PANEL_CHANNEL` / `SUPERADMIN_PANEL_CHANNEL` in `.env` and the staff
boards refuse to be posted anywhere else.

Every label here is built at *render* time rather than declared with a
`@discord.ui.button` decorator: a decorator's label is evaluated at import, long
before the server's language is known. The persistent board buttons keep their
fixed `custom_id`s, which is what makes them survive a restart.

Profiles, personal scores and leaderboards are deliberately **absent** from the
panel: that feature isn't finished, and a board that only shows lobby-relevant
state is easier to trust. `/register`, `/profile` and `/stats` still work.
"""
from __future__ import annotations

import json

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import select

from bot.config import settings
from bot.core import actions, audit, board
from bot.core.embeds import (
    DASH,
    EMBED_COLOR,
    custom_registration_embed,
    game_color,
    game_mark,
    member_name,
    start_line,
)
from bot.core.errors import BotError
from bot.core.nav import Screen
from bot.core.permissions import (
    ADMIN,
    PLAYER,
    RANK_KEY,
    SUPER,
    can_manage_custom,
    grant_role,
    is_superadmin,
    member_level,
    revoke_role,
)
from bot.core.ui import reply
from bot.core.views import MatchResultModal
from bot.db import SessionLocal
from bot.db.models import AuditLog, Custom, Map, MemberRole, User
from bot.i18n import LANG_NAME, LANGS, lang_context, t
from bot.i18n.translator import L
from bot.i18n.ui import LocalizedModal, bind
from bot.services import bans as bans_svc
from bot.services import custom as custom_svc
from bot.services import draft as draft_svc
from bot.services import games as games_svc
from bot.services import guild_svc
from bot.services import maps as maps_svc
from bot.services import panel_svc
from bot.services import approvals as appr_svc
from bot.services import rank_sync

TIER_LEVEL = {"player": PLAYER, "admin": ADMIN, "superadmin": SUPER}
TIER_KEY = {"player": "tier.player", "admin": "tier.admin",
            "superadmin": "tier.superadmin"}
TIER_CHANNEL = {
    "admin": "admin_panel_channel",
    "superadmin": "superadmin_panel_channel",
}

# On/off marks for the map pool. Not the boards' state dots (🟢🟡🔵🟠🔴⚫) — those
# mean lifecycle state, and reusing them here for a binary toggle would collide.
MAP_ON, MAP_OFF = "✅", "⬜"


def tier_label(tier: str) -> str:
    return t(TIER_KEY[tier])


async def _guard(itx: discord.Interaction, level: int) -> bool:
    """Shared level check; explains what the caller is missing."""
    if await member_level(itx.user) >= level:
        return True
    await reply(itx, t("error.need_role", role=t(RANK_KEY[level])))
    return False


async def _get_custom(itx: discord.Interaction, custom_id: int) -> Custom | None:
    async with SessionLocal() as s:
        c = await s.get(Custom, custom_id)
    if not c or c.guild_id != itx.guild_id:
        await reply(itx, t("error.custom_gone", custom_id=custom_id))
        return None
    return c


def _picker_options(customs: list[Custom]) -> list[discord.SelectOption]:
    return [
        discord.SelectOption(
            label=f"#{c.custom_id} {c.name}"[:100],
            description=t("picker.desc", fmt=c.format, size=c.team_size,
                          state=board.state_name(c.state))[:100],
            value=str(c.custom_id),
            emoji=board.state_dot(c.state),
        )
        for c in customs[:25]
    ]


# ============================================================== modals ========
class CreateCustomModal(LocalizedModal):
    """Step 2 of creation — game, map pool and draft mode were already chosen
    on the Create screen. (Discord modals cannot contain dropdowns, hence two
    steps.)"""

    def __init__(self, maps: list[str] | None = None, draft_mode: str = "snake",
                 captain_method: str = "random", game: str = "valorant"):
        super().__init__(title=t("modal.create.title"))
        self.maps = maps or []
        self.draft_mode = draft_mode
        self.captain_method = captain_method
        self.game = game
        self.name = discord.ui.TextInput(
            label=t("modal.create.name"), placeholder=t("modal.create.name_ph"),
            max_length=64,
        )
        # CS2 is BO1-only (see bot.services.games) — the field is fixed rather
        # than shown, so there's nothing to pick wrong.
        self.fmt = discord.ui.TextInput(
            label=t("modal.create.fmt"), default="BO1", max_length=3
        )
        self.team_size = discord.ui.TextInput(
            label=t("modal.create.team_size"), default="5", max_length=1
        )
        self.start = discord.ui.TextInput(
            label=t("modal.create.start"), placeholder=t("modal.create.start_ph"),
            required=False,
        )
        items = [self.name]
        if game != "cs2":
            items.append(self.fmt)
        items += [self.team_size, self.start]
        for item in items:
            self.add_item(item)

    async def on_submit(self, itx: discord.Interaction):
        # Creating a custom writes to the DB and makes two REST calls (create
        # channel, post the embed) — far more than the 3s an un-acknowledged
        # interaction token survives. Ack first, answer on the followup.
        await itx.response.defer(ephemeral=True)
        try:
            ts_ = int(self.team_size.value)
            c = await actions.create_custom_flow(
                itx, name=self.name.value, fmt=self.fmt.value,
                start_raw=self.start.value, maps_csv=",".join(self.maps),
                team_size=ts_, draft_mode=self.draft_mode,
                captain_method=self.captain_method, game=self.game,
            )
        except (BotError, ValueError) as e:
            return await reply(itx, str(e))
        reg = itx.guild.get_channel(c.reg_channel)
        await reply(itx, t(
            "custom.created", custom_id=c.custom_id, size=c.team_size,
            channel=reg.mention if reg else f"#custom-{c.custom_id}",
        ))


class AddMapModal(LocalizedModal):
    def __init__(self, screen: "MapsScreen"):
        super().__init__(title=t("modal.addmap.title"))
        self.screen = screen
        self.name = discord.ui.TextInput(
            label=t("modal.addmap.name"), placeholder=t("modal.addmap.name_ph"),
            max_length=32,
        )
        self.add_item(self.name)

    async def on_submit(self, itx: discord.Interaction):
        name = self.name.value.strip()
        if not name:
            return await reply(itx, t("maps.err.empty"))
        added = await maps_svc.add_map(itx.guild_id, name, itx.user.id, game=self.screen.game)
        if not added:
            return await reply(itx, t("maps.err.exists", name=name))
        await self.screen.repaint()        # redraw the pool behind the modal
        board.schedule(itx.guild)
        await reply(itx, t("maps.added", name=name))


class BanReasonModal(LocalizedModal):
    def __init__(self, member: discord.Member, screen: "BansScreen"):
        super().__init__(title=t("modal.ban.title"))
        self.member = member
        self.screen = screen
        self.reason = discord.ui.TextInput(
            label=t("modal.ban.reason"), required=False,
            style=discord.TextStyle.paragraph, max_length=200,
        )
        self.add_item(self.reason)

    async def on_submit(self, itx: discord.Interaction):
        created = await bans_svc.ban(itx.guild_id, self.member.id, itx.user.id,
                                     self.reason.value or None)
        await audit.log(itx.guild_id, itx.user.id, "ban", str(self.member.id))
        await self.screen.repaint()
        board.schedule(itx.guild)
        await reply(itx, t("bans.banned" if created else "bans.already_banned",
                           member=self.member.mention))


# ------------------------------------------------------------ profiles ------
# Parked until personal scores/profiles are finished. The panel deliberately
# shows nothing about ranks, records or leaderboards — it is a lobby tool. The
# equivalent slash commands (`/register`, `/profile`, `/stats`) still work, and
# re-adding a Profile button here is a one-liner once the feature lands.


# ============================================================= screens =======
class _Gated(Screen):
    """A private screen that re-checks the caller's tier on every click — the
    message is already private, but a role can be revoked mid-session."""

    LEVEL = PLAYER

    async def interaction_check(self, itx: discord.Interaction) -> bool:
        # Bind the language first: the refusal below is itself translated.
        await super().interaction_check(itx)
        return await _guard(itx, self.LEVEL)


# ------------------------------------------------- player: browse & join ----
class CustomsScreen(_Gated):
    """Every open game, with your own sign-up state marked."""

    LEVEL = PLAYER

    def __init__(self, guild_id: int, user_id: int, parent: Screen | None = None):
        super().__init__(parent)
        self.guild_id = guild_id
        self.user_id = user_id
        self._customs: list[Custom] = []

    async def embed(self) -> discord.Embed:
        self._customs = await board.active_customs(self.guild_id)
        e = discord.Embed(
            title=t("screen.customs.title"),
            description=t("screen.customs.desc"),
            color=EMBED_COLOR,
        )
        if not self._customs:
            e.description = t("screen.customs.empty")
            return e
        lines = []
        for c in self._customs[:25]:
            mine = await actions.is_registered(c.custom_id, self.user_id)
            lines.append(await board.custom_line(c)
                         + (t("screen.customs.youre_in") if mine else ""))
        e.add_field(name=t("board.open_games", n=len(self._customs)),
                    value="\n".join(lines)[:1024], inline=False)
        return e

    async def build(self) -> None:
        if self._customs:
            self.add_item(self._Picker(self._customs))

    class _Picker(discord.ui.Select):
        def __init__(self, customs: list[Custom]):
            super().__init__(placeholder=t("screen.customs.pick"),
                             options=_picker_options(customs), row=0)

        async def callback(self, itx: discord.Interaction):
            view: CustomsScreen = self.view
            await view.goto(
                itx, CustomScreen(int(self.values[0]), view.user_id, parent=view)
            )


class CustomScreen(_Gated):
    """One game: live roster, seats, your status — and the two buttons that
    matter, enabled only when they'd actually do something."""

    LEVEL = PLAYER

    def __init__(self, custom_id: int, user_id: int, parent: Screen | None = None):
        super().__init__(parent)
        self.cid = custom_id
        self.user_id = user_id
        self._registered = False
        self._open = False

    async def embed(self) -> discord.Embed:
        # compose() runs embed() before build(), so the per-viewer state resolved
        # here is what decides which buttons come out enabled.
        async with SessionLocal() as s:
            c = await s.get(Custom, self.cid)
        if not c:
            self._registered = self._open = False
            return discord.Embed(
                title=t("screen.gone.title"),
                description=t("error.custom_gone", custom_id=self.cid),
                color=EMBED_COLOR,
            )
        r = await custom_svc.roster(self.cid)
        self._open = c.state in ("registration", "full")
        self._registered = self.user_id in r.all
        e = custom_registration_embed(c, r.starters, r.size, r.waitlist)
        if self._registered:
            seat = t("screen.custom.you_waitlist" if self.user_id in r.waitlist
                     else "screen.custom.you_in")
            e.add_field(name=t("screen.custom.you"), value=seat, inline=False)
        elif not self._open:
            e.add_field(name=t("screen.custom.you"),
                        value=t("screen.custom.closed"), inline=False)
        return e

    async def build(self) -> None:
        self.add_item(self._Act("btn.register", "register",
                                discord.ButtonStyle.success,
                                disabled=self._registered or not self._open))
        self.add_item(self._Act("btn.leave", "leave",
                                discord.ButtonStyle.secondary,
                                disabled=not self._registered))

    class _Act(discord.ui.Button):
        def __init__(self, label_key, action, style, *, disabled=False):
            super().__init__(label=t(label_key), style=style,
                             disabled=disabled, row=0)
            self.action = action

        async def callback(self, itx: discord.Interaction):
            view: CustomScreen = self.view
            fn = actions.join_custom if self.action == "register" else actions.leave_custom
            try:
                msg = await fn(itx.guild, view.cid, itx.user.id)
            except BotError as e:
                return await reply(itx, str(e))
            await view.reload(itx)
            board.schedule(itx.guild)
            await reply(itx, msg)


# ------------------------------------------------------- admin: create ------
class CreateScreen(_Gated):
    """Map pool and draft mode live in the embed as you pick them; the rest goes
    in a modal, because Discord modals can't hold dropdowns."""

    LEVEL = ADMIN

    def __init__(self, guild_id: int, parent: Screen | None = None):
        super().__init__(parent)
        self.guild_id = guild_id
        self.game = "valorant"
        self.selected: list[str] = []
        self.draft_mode = "snake"
        self.captain_method = "random"
        self._maps: list[Map] = []
        self._competitive: list[str] = []

    async def embed(self) -> discord.Embed:
        has_veto = games_svc.has_veto(self.game)
        if has_veto:
            self._maps = await maps_svc.enabled_maps(self.guild_id, self.game)
            self._competitive = await maps_svc.competitive_names(self.guild_id, self.game)
        else:
            self._maps = []
            self._competitive = []
        e = discord.Embed(
            title=t("screen.create.title"),
            description=t("screen.create.desc"),
            color=game_color(self.game),
        )
        e.add_field(name=t("common.game"), value=games_svc.game_label(self.game), inline=True)
        if has_veto:
            e.add_field(
                name=t("common.maps"),
                value=", ".join(self.selected) if self.selected
                else t("screen.create.all_maps", n=len(self._maps)),
                inline=False,
            )
        e.add_field(name=t("common.draft"),
                    value=draft_svc.draft_mode_label(self.draft_mode), inline=True)
        e.add_field(
            name=t("common.captains"),
            value=f"{draft_svc.captain_label(self.captain_method)}\n"
                  f"_{draft_svc.captain_help(self.captain_method)}_",
            inline=True,
        )
        if has_veto:
            e.add_field(name=t("board.competitive"),
                        value=", ".join(self._competitive) if self._competitive
                        else DASH,
                        inline=False)
            if not self._maps:
                e.description = t("screen.create.no_maps")
        return e

    async def build(self) -> None:
        has_veto = games_svc.has_veto(self.game)
        if has_veto and not self._maps:
            self.add_item(self._Game(self.game))
            return
        if has_veto:
            self.add_item(self._Pool(self._maps, self.selected))
        self.add_item(self._DraftMode(self.draft_mode))
        self.add_item(self._Captains(self.captain_method))
        if has_veto:
            self.add_item(self._Competitive())
        self.add_item(self._Continue())
        self.add_item(self._Game(self.game))

    class _Game(discord.ui.Select):
        def __init__(self, current: str):
            super().__init__(
                placeholder=t("screen.create.game_ph"),
                options=[
                    discord.SelectOption(
                        label=games_svc.game_label(g), value=g, default=g == current,
                    )
                    for g in games_svc.GAMES
                ],
                row=3,
            )

        async def callback(self, itx: discord.Interaction):
            view: CreateScreen = self.view
            view.game = self.values[0]
            view.selected = []  # the previous game's map pool doesn't apply
            await view.reload(itx)

    class _Pool(discord.ui.Select):
        def __init__(self, maps: list[Map], selected: list[str]):
            opts = [
                discord.SelectOption(label=m.name, value=m.name, default=m.name in selected)
                for m in maps[:25]
            ]
            super().__init__(
                placeholder=t("screen.create.pool_ph"),
                options=opts, min_values=0, max_values=len(opts), row=0,
            )

        async def callback(self, itx: discord.Interaction):
            self.view.selected = list(self.values)
            await self.view.reload(itx)

    class _DraftMode(discord.ui.Select):
        def __init__(self, current: str):
            super().__init__(
                placeholder=t("screen.create.draft_ph"),
                options=[
                    discord.SelectOption(
                        label=t("draft.snake.label"), value="snake",
                        description=t("draft.snake.desc")[:100],
                        default=current == "snake",
                    ),
                    discord.SelectOption(
                        label=t("draft.alternate.label"), value="alternate",
                        description=t("draft.alternate.desc")[:100],
                        default=current == "alternate",
                    ),
                ],
                row=1,
            )

        async def callback(self, itx: discord.Interaction):
            self.view.draft_mode = self.values[0]
            await self.view.reload(itx)

    class _Captains(discord.ui.Select):
        """Fixed here, not at start time — how the game is run belongs to the
        game, not to whoever happens to press the button."""

        def __init__(self, current: str):
            super().__init__(
                placeholder=t("screen.create.captains_ph"),
                options=[
                    discord.SelectOption(
                        label=draft_svc.captain_label(m), value=m,
                        description=draft_svc.captain_help(m)[:100],
                        default=m == current,
                    )
                    for m in draft_svc.CREATE_METHODS
                ],
                row=2,
            )

        async def callback(self, itx: discord.Interaction):
            self.view.captain_method = self.values[0]
            await self.view.reload(itx)

    class _Competitive(discord.ui.Button):
        def __init__(self):
            super().__init__(label=t("btn.competitive_pool"),
                             style=discord.ButtonStyle.primary, row=4)

        async def callback(self, itx: discord.Interaction):
            view: CreateScreen = self.view
            if not view._competitive:
                return await reply(itx, t("screen.create.no_comp"))
            view.selected = list(view._competitive)
            await view.reload(itx)

    class _Continue(discord.ui.Button):
        def __init__(self):
            super().__init__(label=t("btn.continue"),
                             style=discord.ButtonStyle.success, row=4)

        async def callback(self, itx: discord.Interaction):
            view: CreateScreen = self.view
            if view.selected and len(view.selected) < 2:
                return await reply(itx, t("screen.create.min_maps"))
            await itx.response.send_modal(
                CreateCustomModal(view.selected, view.draft_mode, view.captain_method,
                                  game=view.game)
            )


# ------------------------------------------------------- admin: manage ------
class ManageListScreen(_Gated):
    """The customs this admin may run — all of them, for a superadmin."""

    LEVEL = ADMIN

    def __init__(self, guild: discord.Guild, owner_id: int | None, is_super: bool,
                 parent: Screen | None = None):
        super().__init__(parent)
        self.guild = guild
        self.guild_id = guild.id
        self.owner_id = owner_id  # None = every custom in the guild
        self.is_super = is_super
        self._customs: list[Custom] = []

    async def embed(self) -> discord.Embed:
        self._customs = await board.active_customs(self.guild_id, owned_by=self.owner_id)
        e = discord.Embed(
            title=t("screen.manage_list.title"),
            description=t("screen.manage_list.desc_all" if self.owner_id is None
                          else "screen.manage_list.desc_own"),
            color=EMBED_COLOR,
        )
        e.add_field(
            name=t("screen.manage_list.active", n=len(self._customs)),
            value=await board.customs_field(self._customs, with_owner=True, guild=self.guild),
            inline=False,
        )
        if not self._customs and self.owner_id is not None:
            e.description = t("screen.manage_list.empty_own")
        return e

    async def build(self) -> None:
        if self._customs:
            self.add_item(self._Picker(self._customs))

    class _Picker(discord.ui.Select):
        def __init__(self, customs: list[Custom]):
            super().__init__(placeholder=t("screen.manage_list.pick"),
                             options=_picker_options(customs), row=0)

        async def callback(self, itx: discord.Interaction):
            view: ManageListScreen = self.view
            await view.goto(
                itx, ManageScreen(int(self.values[0]), view.is_super, parent=view)
            )


class ManageScreen(_Gated):
    """Run one custom. Which buttons are live follows the custom's state:
    you can't start a match that's already running, or end one that hasn't."""

    LEVEL = ADMIN

    def __init__(self, custom_id: int, is_super: bool, parent: Screen | None = None):
        super().__init__(parent)
        self.cid = custom_id
        self.is_super = is_super
        self._state = "registration"
        self._alive = True
        self._roster_full = False

    async def embed(self) -> discord.Embed:
        async with SessionLocal() as s:
            c = await s.get(Custom, self.cid)
        if not c:
            self._alive = False
            return discord.Embed(
                title=t("screen.gone.title"),
                description=t("error.custom_gone", custom_id=self.cid),
                color=EMBED_COLOR,
            )
        self._alive, self._state = True, c.state
        r = await custom_svc.roster(self.cid)
        self._roster_full = bool(r.size) and len(r.starters) >= r.size
        method = c.captain_method or "random"
        e = discord.Embed(
            title=f"{game_mark(c.game)} "
                  + t("screen.manage.title", custom_id=c.custom_id, name=c.name),
            description=t(
                "screen.manage.body",
                dot=board.state_dot(c.state), state=board.state_name(c.state),
                fmt=c.format, size=c.team_size, start=start_line(c),
                pool=", ".join(json.loads(c.map_pool)),
                draft=draft_svc.draft_mode_label(c.draft_mode),
                captains=draft_svc.captain_label(method),
            ),
            color=game_color(c.game),
        )
        e.add_field(name=t("common.owner"), value=f"<@{c.owner_id}>", inline=True)
        e.add_field(name=t("common.seats"), value=f"{len(r.starters)}/{r.size}",
                    inline=True)
        e.add_field(name=t("common.waitlist"), value=str(len(r.waitlist)), inline=True)
        e.add_field(
            name=t("common.players"),
            value="\n".join(f"• <@{u}>" for u in r.starters) or DASH,
            inline=False,
        )
        if self._state == "ready":
            e.add_field(
                name=t("screen.manage.ready_title"),
                value=t("screen.manage.ready_body"),
                inline=False,
            )
        return e

    async def build(self) -> None:
        if not self._alive:
            return
        startable = self._state in ("registration", "full", "ready")
        endable = self._state in ("veto", "live")
        # A check needs an even lobby, and there's no point running one while
        # another is already on the clock.
        can_check = (self._state in ("registration", "full")
                     and self.cid not in actions.ACTIVE_READY
                     and self.cid not in actions.READY_COOLDOWN)
        self.add_item(self._Transfer())
        self.add_item(self._ReadyCheck(disabled=not can_check))
        self.add_item(self._Start("btn.start", False, discord.ButtonStyle.success,
                                  disabled=not startable))
        self.add_item(self._Start("btn.force_start", True, discord.ButtonStyle.success,
                                  disabled=not startable))
        self.add_item(self._End(disabled=not endable))
        self.add_item(self._Delete())

    class _ReadyCheck(discord.ui.Button):
        def __init__(self, *, disabled):
            super().__init__(label=t("btn.ready_check"),
                             style=discord.ButtonStyle.primary,
                             disabled=disabled, row=1)

        async def callback(self, itx: discord.Interaction):
            view: ManageScreen = self.view
            await itx.response.defer()
            try:
                msg = await actions.start_ready_check(
                    itx.guild, view.cid, actor_id=itx.user.id
                )
            except BotError as e:
                await view.reload(itx)
                return await reply(itx, str(e))
            await view.reload(itx)
            await reply(itx, msg)

    class _Transfer(discord.ui.UserSelect):
        def __init__(self):
            super().__init__(placeholder=t("screen.manage.transfer_ph"),
                             max_values=1, row=0)

        async def callback(self, itx: discord.Interaction):
            view: ManageScreen = self.view
            new = self.values[0]
            # Redraws the registration embed and DMs the new owner — defer first.
            await itx.response.defer()
            try:
                await actions.transfer_custom(itx, view.cid, new)
            except BotError as e:
                return await reply(itx, str(e))
            await view.reload(itx)
            board.schedule(itx.guild)
            await reply(itx, t("custom.transferred_short", custom_id=view.cid,
                               member=new.mention))

    class _Start(discord.ui.Button):
        def __init__(self, label_key, partial, style, *, disabled):
            super().__init__(label=t(label_key), style=style,
                             disabled=disabled, row=2)
            self.partial = partial

        async def callback(self, itx: discord.Interaction):
            view: ManageScreen = self.view
            try:
                # captains=None: use the method fixed when the custom was created.
                await actions.start_match(itx, view.cid, allow_partial=self.partial)
            except BotError as e:
                return await reply(itx, str(e))
            await view.reload(itx)     # start_match already answered; edits the message
            board.schedule(itx.guild)

    class _End(discord.ui.Button):
        def __init__(self, *, disabled):
            super().__init__(label=t("btn.end"), style=discord.ButtonStyle.primary,
                             disabled=disabled, row=2)

        async def callback(self, itx: discord.Interaction):
            view: ManageScreen = self.view

            async def done(itx: discord.Interaction):
                board.schedule(itx.guild)
                # The custom is gone from the active list — go back to it rather
                # than leaving a manage screen for something that no longer runs.
                if view.parent is not None:
                    await view.goto(itx, view.parent)
                else:
                    await view.reload(itx)

            # A match nobody has reported yet: ask for the score here too, or
            # the panel stays the one way to end a custom and lose its result.
            pending = await actions.pending_result(view.cid)
            if pending:
                match_id, maps, reported = pending
                caps = await actions.match_captains(match_id)
                return await itx.response.send_modal(
                    MatchResultModal(
                        view.cid, match_id, maps, reported, after=done,
                        cap_a_name=member_name(itx.guild, caps.get("A")) if caps.get("A") else "Team A",
                        cap_b_name=member_name(itx.guild, caps.get("B")) if caps.get("B") else "Team B",
                    )
                )
            # Ending deletes the custom's voice AND text channels — ack first.
            await itx.response.defer()
            try:
                await actions.end_custom(itx, view.cid)
            except BotError as e:
                return await reply(itx, str(e))
            await reply(itx, t("custom.ended", custom_id=view.cid))
            await done(itx)

    class _Delete(discord.ui.Button):
        def __init__(self):
            super().__init__(label=t("btn.delete"), style=discord.ButtonStyle.danger,
                             row=2)

        async def callback(self, itx: discord.Interaction):
            view: ManageScreen = self.view
            c = await _get_custom(itx, view.cid)
            if not c:
                return
            if not await can_manage_custom(c, itx.user):
                return await reply(itx, t("error.cant_manage"))
            await view.goto(itx, ConfirmScreen(
                parent=view,
                title=t("confirm.delete.title", custom_id=view.cid),
                description=t("confirm.delete.desc", name=c.name),
                confirm=_delete_custom_action(view.cid),
                allow_force=view.is_super,
                after=view.parent,
            ))


def _delete_custom_action(custom_id: int):
    async def run(itx: discord.Interaction, force: bool) -> str:
        await actions.cancel_ready_check(custom_id, t("ready.cancel.deleted"))
        await custom_svc.delete_custom(custom_id, itx.guild, force=force)
        await audit.log(itx.guild_id, itx.user.id, "custom_delete", str(custom_id),
                        force=force)
        board.schedule(itx.guild)
        return t("custom.deleted", custom_id=custom_id)

    return run


# ------------------------------------------------------------ admin: maps ---
class MapsScreen(_Gated):
    """The pool, its on/off state and the competitive rotation, all visible at
    once — tick as many as you like in one go."""

    LEVEL = ADMIN

    # Dota 2 has no map pool, so it isn't offered here.
    GAMES = tuple(g for g in games_svc.GAMES if games_svc.has_veto(g))

    def __init__(self, guild_id: int, parent: Screen | None = None):
        super().__init__(parent)
        self.guild_id = guild_id
        self.game = "valorant"
        self._maps: list[Map] = []

    async def embed(self) -> discord.Embed:
        self._maps = await maps_svc.all_maps(self.guild_id, self.game)
        e = discord.Embed(title=t("board.map_pool"), color=game_color(self.game))
        e.add_field(name=t("common.game"), value=games_svc.game_label(self.game), inline=False)
        if not self._maps:
            e.description = t("screen.maps.empty")
            return e
        comp = [m.name for m in self._maps if m.competitive]
        e.description = "\n".join(
            t("maps.list_line_comp" if m.competitive else "maps.list_line",
              dot=MAP_ON if m.enabled else MAP_OFF, name=m.name)
            for m in self._maps
        )[:4096]
        e.add_field(name=t("board.competitive"),
                    value=", ".join(comp) if comp else DASH,
                    inline=False)
        e.set_footer(text=t("screen.maps.footer"))
        return e

    async def build(self) -> None:
        if self._maps:
            self.add_item(self._Toggle(self._maps))
            self.add_item(self._Competitive(self._maps))
        self.add_item(self._Seed())
        self.add_item(self._Add())
        if self._maps:
            self.add_item(self._Remove())
        self.add_item(self._Game(self.game))

    class _Game(discord.ui.Select):
        def __init__(self, current: str):
            super().__init__(
                placeholder=t("screen.maps.game_ph"),
                options=[
                    discord.SelectOption(
                        label=games_svc.game_label(g), value=g, default=g == current,
                    )
                    for g in MapsScreen.GAMES
                ],
                row=3,
            )

        async def callback(self, itx: discord.Interaction):
            view: MapsScreen = self.view
            view.game = self.values[0]
            await view.reload(itx)

    class _Toggle(discord.ui.Select):
        def __init__(self, maps: list[Map]):
            opts = [
                discord.SelectOption(
                    label=m.name, value=m.name,
                    description=t("common.enabled" if m.enabled else "common.disabled"),
                    emoji=MAP_ON if m.enabled else MAP_OFF,
                )
                for m in maps[:25]
            ]
            super().__init__(placeholder=t("screen.maps.toggle_ph"),
                             options=opts, min_values=1, max_values=len(opts), row=0)

        async def callback(self, itx: discord.Interaction):
            flipped = []
            for name in self.values:
                state = await maps_svc.toggle_map(itx.guild_id, name, itx.user.id)
                if state is None:  # removed by someone else meanwhile
                    continue
                flipped.append(t(
                    "screen.maps.flipped", name=name,
                    state=t("common.enabled" if state else "common.disabled"),
                ))
            await self.view.reload(itx)
            board.schedule(itx.guild)
            await reply(itx, "\n".join(flipped) if flipped
                        else t("screen.maps.nothing"))

    class _Competitive(discord.ui.Select):
        """Sets the competitive pool to exactly what's ticked (empty clears it)."""

        def __init__(self, maps: list[Map]):
            opts = [
                discord.SelectOption(
                    label=m.name, value=m.name,
                    description=t("screen.maps.in_comp") if m.competitive else None,
                    default=m.competitive,
                )
                for m in maps[:25]
            ]
            super().__init__(placeholder=t("screen.maps.comp_ph"),
                             options=opts, min_values=0, max_values=len(opts), row=1)

        async def callback(self, itx: discord.Interaction):
            view: MapsScreen = self.view
            in_pool, _ = await maps_svc.set_competitive(
                itx.guild_id, list(self.values), itx.user.id, game=view.game
            )
            await view.reload(itx)
            board.schedule(itx.guild)
            await reply(
                itx,
                t("maps.comp_set", maps=", ".join(in_pool)) if in_pool
                else t("maps.comp_cleared"),
            )

    class _Seed(discord.ui.Button):
        def __init__(self):
            super().__init__(label=t("btn.seed"), style=discord.ButtonStyle.primary,
                             row=2)

        async def callback(self, itx: discord.Interaction):
            view: MapsScreen = self.view
            added = await maps_svc.seed(itx.guild_id, view.game)
            await view.reload(itx)
            board.schedule(itx.guild)
            await reply(itx, t("maps.seeded", n=len(added)) if added
                        else t("maps.already_seeded"))

    class _Add(discord.ui.Button):
        def __init__(self):
            super().__init__(label=t("btn.add_map"), style=discord.ButtonStyle.success,
                             row=2)

        async def callback(self, itx: discord.Interaction):
            await itx.response.send_modal(AddMapModal(self.view))

    class _Remove(discord.ui.Button):
        """Opens a dedicated picker rather than deleting inline: the main screen's
        rows are full, and dropping a map (and its competitive flag) is worth its
        own deliberate step."""

        def __init__(self):
            super().__init__(label=t("btn.remove_map"), style=discord.ButtonStyle.danger,
                             row=2)

        async def callback(self, itx: discord.Interaction):
            view: MapsScreen = self.view
            await view.goto(itx, MapDeleteScreen(view.guild_id, view.game, parent=view))


class MapDeleteScreen(_Gated):
    """Remove a map from the pool for good. Reachable from the Maps screen; a
    deleted map can always be brought back with Add or Seed."""

    LEVEL = ADMIN

    def __init__(self, guild_id: int, game: str, parent: Screen | None = None):
        super().__init__(parent)
        self.guild_id = guild_id
        self.game = game
        self._maps: list[Map] = []

    async def embed(self) -> discord.Embed:
        self._maps = await maps_svc.all_maps(self.guild_id, self.game)
        e = discord.Embed(
            title=t("screen.maps.delete.title"),
            description=t("screen.maps.delete.desc", game=games_svc.game_label(self.game)),
            color=EMBED_COLOR,
        )
        if not self._maps:
            e.description = t("screen.maps.empty")
            return e
        e.add_field(
            name=t("board.map_pool"),
            value=", ".join(m.name for m in self._maps)[:1024],
            inline=False,
        )
        return e

    async def build(self) -> None:
        if self._maps:
            self.add_item(self._Pick(self._maps))

    class _Pick(discord.ui.Select):
        def __init__(self, maps: list[Map]):
            super().__init__(
                placeholder=t("screen.maps.delete_ph"),
                options=[discord.SelectOption(label=m.name, value=m.name) for m in maps[:25]],
                min_values=1, max_values=1, row=0,
            )

        async def callback(self, itx: discord.Interaction):
            view: MapDeleteScreen = self.view
            name = self.values[0]
            removed = await maps_svc.remove_map(itx.guild_id, name, itx.user.id)
            await view.reload(itx)
            board.schedule(itx.guild)
            await reply(itx, t("maps.removed", name=name) if removed else t("maps.no_such"))


# ------------------------------------------------------------ admin: bans ---
class BansScreen(_Gated):
    LEVEL = ADMIN

    def __init__(self, guild_id: int, parent: Screen | None = None):
        super().__init__(parent)
        self.guild_id = guild_id
        self.target: discord.Member | None = None

    async def embed(self) -> discord.Embed:
        rows = await bans_svc.list_bans(self.guild_id)
        e = discord.Embed(
            title=t("screen.bans.title"),
            description=t("screen.bans.desc"),
            color=EMBED_COLOR,
        )
        e.add_field(
            name=t("screen.bans.count", n=len(rows)),
            value=("\n".join(f"• <@{b.user_id}>" + (f" — {b.reason}" if b.reason else "")
                             for b in rows[:20]) or DASH)[:1024],
            inline=False,
        )
        e.add_field(name=t("common.selected"),
                    value=self.target.mention if self.target
                    else t("screen.bans.pick_hint"),
                    inline=False)
        if len(rows) > 20:
            e.set_footer(text=t("screen.bans.more", n=len(rows) - 20))
        return e

    async def build(self) -> None:
        self.add_item(self._Member())
        self.add_item(self._Ban(disabled=self.target is None))
        self.add_item(self._Unban(disabled=self.target is None))

    class _Member(discord.ui.UserSelect):
        def __init__(self):
            super().__init__(placeholder=t("screen.bans.player_ph"), max_values=1, row=0)

        async def callback(self, itx: discord.Interaction):
            self.view.target = self.values[0]
            await self.view.reload(itx)

    class _Ban(discord.ui.Button):
        def __init__(self, *, disabled):
            super().__init__(label=t("btn.ban"), style=discord.ButtonStyle.danger,
                             disabled=disabled, row=1)

        async def callback(self, itx: discord.Interaction):
            view: BansScreen = self.view
            await itx.response.send_modal(BanReasonModal(view.target, view))

    class _Unban(discord.ui.Button):
        def __init__(self, *, disabled):
            super().__init__(label=t("btn.unban"), style=discord.ButtonStyle.success,
                             disabled=disabled, row=1)

        async def callback(self, itx: discord.Interaction):
            view: BansScreen = self.view
            removed = await bans_svc.unban(itx.guild_id, view.target.id)
            await audit.log(itx.guild_id, itx.user.id, "unban", str(view.target.id))
            await view.reload(itx)
            await reply(itx, t("bans.unbanned" if removed else "bans.not_banned",
                               member=view.target.mention))


# ---------------------------------------------------- admin: rank approvals
class RankApprovalsScreen(_Gated):
    """A submitted identity (Riot ID, Faceit nickname, Dota friend id) counts
    nowhere in the bot until an admin approves it here — no OAuth proves a
    Discord user owns any of these accounts, so a human is the trust step. One
    queue for all three games."""

    LEVEL = ADMIN

    def __init__(self, guild: discord.Guild, parent: Screen | None = None):
        super().__init__(parent)
        self.guild = guild
        # (user_id, game) of the highlighted submission, or None.
        self.target: tuple[int, str] | None = None
        self._pending: list = []

    async def embed(self) -> discord.Embed:
        self._pending = await appr_svc.list_pending()
        e = discord.Embed(
            title=t("screen.rank_approvals.title"),
            description=t("screen.rank_approvals.desc"),
            color=EMBED_COLOR,
        )
        e.add_field(
            name=t("screen.rank_approvals.count", n=len(self._pending)),
            value=("\n".join(
                t("screen.rank_approvals.line", mark=game_mark(p.game),
                  member=member_name(self.guild, p.user_id), identity=p.identity)
                for p in self._pending[:20]) or DASH)[:1024],
            inline=False,
        )
        if len(self._pending) > 20:
            e.set_footer(text=t("screen.rank_approvals.more", n=len(self._pending) - 20))
        return e

    async def build(self) -> None:
        if self._pending:
            self.add_item(self._Picker(self._pending, self.guild, self.target))
        self.add_item(self._Approve(disabled=self.target is None))
        self.add_item(self._Deny(disabled=self.target is None))

    class _Picker(discord.ui.Select):
        def __init__(self, pending: list, guild: discord.Guild, selected):
            opts = [
                discord.SelectOption(
                    label=f"{game_mark(p.game)} {p.identity}"[:100],
                    description=f"{games_svc.game_label(p.game)} · "
                                f"{member_name(guild, p.user_id)}"[:100],
                    value=f"{p.game}:{p.user_id}",
                    default=selected == (p.user_id, p.game),
                )
                for p in pending[:25]
            ]
            super().__init__(placeholder=t("screen.rank_approvals.pick"), options=opts, row=0)

        async def callback(self, itx: discord.Interaction):
            game, uid = self.values[0].split(":", 1)
            self.view.target = (int(uid), game)
            await self.view.reload(itx)

    class _Approve(discord.ui.Button):
        def __init__(self, *, disabled):
            super().__init__(label=t("btn.approve"), style=discord.ButtonStyle.success,
                             disabled=disabled, row=1)

        async def callback(self, itx: discord.Interaction):
            await _resolve_approval(itx, self.view, approve=True)

    class _Deny(discord.ui.Button):
        def __init__(self, *, disabled):
            super().__init__(label=t("btn.deny"), style=discord.ButtonStyle.danger,
                             disabled=disabled, row=1)

        async def callback(self, itx: discord.Interaction):
            await _resolve_approval(itx, self.view, approve=False)


def _pending_identity(u: User, game: str) -> str:
    return {"cs2": u.cs2_nick, "dota2": u.dota_friend_id}.get(game, u.riot_id) or ""


async def _resolve_approval(
    itx: discord.Interaction, view: RankApprovalsScreen, *, approve: bool
) -> None:
    await itx.response.defer()
    if not view.target:
        return await view.reload(itx)
    uid, game = view.target
    u = await appr_svc.resolve(uid, game, itx.user.id, approve=approve)
    view.target = None
    if not u:
        await view.reload(itx)
        return await reply(itx, t("rank_approvals.gone"))
    await audit.log(itx.guild_id, itx.user.id,
                    "rank_approve" if approve else "rank_deny", f"{game}:{u.user_id}")
    if approve:
        await rank_sync.refresh_for_game(u.user_id, game, force=True)
    member = itx.guild.get_member(u.user_id)
    if member:
        try:
            key = "rank.dm.approved" if approve else "rank.dm.denied"
            await member.send(t(key, identity=_pending_identity(u, game),
                                game=games_svc.game_label(game), guild=itx.guild.name))
        except discord.HTTPException:
            pass
    await view.reload(itx)
    board.schedule(itx.guild)
    await reply(itx, t("rank_approvals.approved" if approve else "rank_approvals.denied",
                       member=member.mention if member else member_name(itx.guild, u.user_id),
                       game=games_svc.game_label(game)))


# ----------------------------------------------------------- shared: audit --
class AuditScreen(_Gated):
    LEVEL = ADMIN

    def __init__(self, guild: discord.Guild, parent: Screen | None = None):
        super().__init__(parent)
        self.guild = guild
        self.guild_id = guild.id

    async def embed(self) -> discord.Embed:
        async with SessionLocal() as s:
            rows = await s.execute(
                select(AuditLog).where(AuditLog.guild_id == self.guild_id)
                .order_by(AuditLog.id.desc()).limit(15)
            )
            entries = [r[0] for r in rows.all()]
        e = discord.Embed(
            title=t("screen.audit.title"),
            description="\n".join(
                t("audit.line", ts=f"{en.ts:%m-%d %H:%M}",
                  actor=member_name(self.guild, en.actor_id),
                  action=en.action, target=en.target or "")
                for en in entries
            ) or t("screen.audit.empty"),
            color=EMBED_COLOR,
        )
        e.set_footer(text=t("screen.audit.footer"))
        return e


# ------------------------------------------------------- super: bot roles ---
class RolesScreen(_Gated):
    LEVEL = SUPER

    def __init__(self, guild_id: int, parent: Screen | None = None):
        super().__init__(parent)
        self.guild_id = guild_id
        self.target: discord.Member | None = None
        self.role = "admin"

    async def embed(self) -> discord.Embed:
        async with SessionLocal() as s:
            rows = await s.execute(
                select(MemberRole.user_id, MemberRole.role)
                .where(MemberRole.guild_id == self.guild_id)
            )
            by_role: dict[str, list[int]] = {}
            for uid, role in rows.all():
                by_role.setdefault(role, []).append(uid)
        e = discord.Embed(
            title=t("screen.roles.title"),
            description=t("screen.roles.desc"),
            color=EMBED_COLOR,
        )
        for role in ("superadmin", "admin"):
            ids = by_role.get(role, [])
            e.add_field(
                name=t("screen.roles.count", role=t(f"role.{role}"), n=len(ids)),
                value=", ".join(f"<@{u}>" for u in ids[:15]) or DASH,
                inline=False,
            )
        e.add_field(
            name=t("common.selected"),
            value=t("screen.roles.selected",
                    member=self.target.mention if self.target
                    else t("screen.roles.pick_hint"),
                    role=t(f"role.{self.role}")),
            inline=False,
        )
        return e

    async def build(self) -> None:
        self.add_item(self._Member())
        self.add_item(self._Role(self.role))
        self.add_item(self._Apply("btn.grant", True, discord.ButtonStyle.success,
                                  disabled=self.target is None))
        self.add_item(self._Apply("btn.revoke", False, discord.ButtonStyle.danger,
                                  disabled=self.target is None))

    class _Member(discord.ui.UserSelect):
        def __init__(self):
            super().__init__(placeholder=t("screen.roles.member_ph"), max_values=1, row=0)

        async def callback(self, itx: discord.Interaction):
            self.view.target = self.values[0]
            await self.view.reload(itx)

    class _Role(discord.ui.Select):
        def __init__(self, current: str):
            super().__init__(
                placeholder=t("screen.roles.role_ph"), row=1,
                options=[discord.SelectOption(label=t(f"role.{r}"), value=r,
                                              default=r == current)
                         for r in ("player", "admin", "superadmin")],
            )

        async def callback(self, itx: discord.Interaction):
            self.view.role = self.values[0]
            await self.view.reload(itx)

    class _Apply(discord.ui.Button):
        def __init__(self, label_key, grant, style, *, disabled):
            super().__init__(label=t(label_key), style=style, disabled=disabled, row=2)
            self.grant = grant

        async def callback(self, itx: discord.Interaction):
            view: RolesScreen = self.view
            if not await is_superadmin(itx.user):
                return await reply(itx, t("error.superadmin_only"))
            if self.grant:
                applied = await grant_role(itx.guild_id, view.target.id, view.role, itx.user.id)
                msg_key = "roles.granted" if applied else "roles.already_granted"
            else:
                applied = await revoke_role(itx.guild_id, view.target.id, view.role, itx.user.id)
                msg_key = "roles.revoked" if applied else "roles.not_granted"
            await view.reload(itx)
            board.schedule(itx.guild)
            await reply(itx, t(msg_key, role=t(f"role.{view.role}"),
                               member=view.target.mention))


# -------------------------------------------------------- super: language ---
class LanguageScreen(_Gated):
    """The server's language. Superadmin only, and it changes what *everyone*
    sees — the boards are redrawn on the way out."""

    LEVEL = SUPER

    def __init__(self, guild_id: int, parent: Screen | None = None):
        super().__init__(parent)
        self.guild_id = guild_id

    async def embed(self) -> discord.Embed:
        current = await guild_svc.get_lang(self.guild_id)
        e = discord.Embed(
            title=t("screen.language.title"),
            description=t("screen.language.desc"),
            color=EMBED_COLOR,
        )
        e.add_field(name=t("screen.language.current"),
                    value=LANG_NAME.get(current, current), inline=False)
        return e

    async def build(self) -> None:
        current = await guild_svc.get_lang(self.guild_id)
        self.add_item(self._Pick(current))

    class _Pick(discord.ui.Select):
        def __init__(self, current: str):
            super().__init__(
                placeholder=t("screen.language.pick"), row=0,
                options=[
                    discord.SelectOption(label=LANG_NAME.get(code, code), value=code,
                                         description=t(f"lang.name.{code}")[:100],
                                         default=code == current)
                    for code in LANGS
                ],
            )

        async def callback(self, itx: discord.Interaction):
            view: LanguageScreen = self.view
            chosen = self.values[0]
            changed = await set_guild_language(itx, chosen)
            # Re-bind so this very redraw already speaks the new language.
            await bind(itx)
            await view.reload(itx)
            await reply(itx, changed)


async def set_guild_language(itx: discord.Interaction, lang: str) -> str:
    """Persist the language, refresh the boards, and report in the *new* one."""
    before = await guild_svc.get_lang(itx.guild_id)
    await guild_svc.set_lang(itx.guild_id, lang)
    board.schedule(itx.guild)
    with lang_context(lang):
        key = "lang.unchanged" if before == lang else "lang.changed"
        return t(key, language=LANG_NAME.get(lang, lang))


# ------------------------------------------------------------ confirmation --
class ConfirmScreen(_Gated):
    """A dangerous action, spelled out before it happens.

    `confirm` is `async (itx, force) -> str` and returns the message to show.
    `description` may be an async callable so the blast radius stays accurate on
    a redraw. `level` is re-checked on the confirm click, not just on the click
    that opened this screen."""

    def __init__(self, *, parent, title, description, confirm, level: int = ADMIN,
                 allow_force: bool = False, after: Screen | None = None):
        super().__init__(parent)
        self.LEVEL = level
        self.heading = title
        self.description = description
        self.confirm = confirm
        self.allow_force = allow_force
        self.after = after

    async def embed(self) -> discord.Embed:
        body = self.description
        if callable(body):
            body = await body()
        if self.allow_force:
            body = f"{body}\n\n{t('confirm.force_note')}"
        return discord.Embed(title=self.heading, description=body, color=EMBED_COLOR)

    async def build(self) -> None:
        self.add_item(self._Go("btn.confirm", False))
        if self.allow_force:
            self.add_item(self._Go("btn.force", True))

    class _Go(discord.ui.Button):
        def __init__(self, label_key: str, force: bool):
            super().__init__(label=t(label_key), style=discord.ButtonStyle.danger, row=0)
            self.force = force

        async def callback(self, itx: discord.Interaction):
            view: ConfirmScreen = self.view
            await itx.response.defer()
            try:
                msg = await view.confirm(itx, self.force)
            except BotError as e:
                await view.reload(itx)
                return await reply(itx, str(e))
            target = view.after or view.parent
            if target is not None:
                await view.goto(itx, target)
            else:
                await view.reload(itx)
            await reply(itx, msg)


def _prune_action():
    async def run(itx: discord.Interaction, force: bool) -> str:
        deleted, skipped = await custom_svc.prune(itx.guild, force=force)
        await audit.log(itx.guild_id, itx.user.id, "custom_prune", meta=str(deleted))
        board.schedule(itx.guild)
        msg = t("custom.pruned", n=deleted)
        if skipped:
            msg += t("custom.pruned_skipped", ids=", ".join(map(str, skipped)))
        return msg

    return run


# ============================================================== boards =======
class _BoardOpen(discord.ui.Button):
    """A board button. `opener` is `async (itx) -> None`; the `custom_id` is
    fixed so the button keeps working across restarts, while the label is
    resolved fresh every time the board is drawn."""

    def __init__(self, label_key: str, custom_id: str, style, row: int, opener):
        super().__init__(label=t(label_key), style=style, row=row, custom_id=custom_id)
        self.opener = opener

    async def callback(self, itx: discord.Interaction):
        await self.opener(itx, self.view)


class _BoardView(discord.ui.View):
    """A persistent public board. Buttons only ever *open* a private screen, so
    the board message is never replaced and one board serves the whole channel.

    Items are added in `__init__` (never by decorator) because their labels come
    out of the catalog, and `board.refresh` rebuilds the view on every redraw so
    a language change reaches the buttons too.
    """

    TIER = "player"
    BUTTONS: tuple = ()

    def __init__(self):
        super().__init__(timeout=None)
        for label_key, custom_id, style, row, opener in self.BUTTONS:
            self.add_item(_BoardOpen(label_key, custom_id, style, row, opener))

    async def interaction_check(self, itx: discord.Interaction) -> bool:
        await bind(itx)
        return await _guard(itx, TIER_LEVEL[self.TIER])

    async def refresh_here(self, itx: discord.Interaction) -> None:
        """Redraw this board using the click's own interaction — instant, and
        it costs no extra API call."""
        await itx.response.edit_message(
            embed=await board.embed_for(itx.guild, self.TIER),
            view=type(self)(),
        )


async def _open_customs(itx, view):
    await CustomsScreen(itx.guild_id, itx.user.id).open(itx)


async def _open_create(itx, view):
    await CreateScreen(itx.guild_id).open(itx)


async def _open_manage_own(itx, view):
    is_super = await member_level(itx.user) >= SUPER
    await ManageListScreen(
        itx.guild, None if is_super else itx.user.id, is_super
    ).open(itx)


async def _open_manage_any(itx, view):
    await ManageListScreen(itx.guild, None, True).open(itx)


async def _open_maps(itx, view):
    await MapsScreen(itx.guild_id).open(itx)


async def _open_bans(itx, view):
    await BansScreen(itx.guild_id).open(itx)


async def _open_rank_approvals(itx, view):
    await RankApprovalsScreen(itx.guild).open(itx)


async def _open_audit(itx, view):
    await AuditScreen(itx.guild).open(itx)


async def _open_roles(itx, view):
    await RolesScreen(itx.guild_id).open(itx)


async def _open_language(itx, view):
    await LanguageScreen(itx.guild_id).open(itx)


async def _open_prune(itx, view):
    guild_id = itx.guild_id

    async def blast_radius() -> str:
        customs = await board.active_customs(guild_id)
        return t("confirm.prune.desc", n=len(customs))

    await ConfirmScreen(
        parent=None,
        title=t("confirm.prune.title"),
        description=blast_radius,
        confirm=_prune_action(),
        level=SUPER,
        allow_force=True,
    ).open(itx)


async def _do_refresh(itx, view):
    await view.refresh_here(itx)


SUCCESS = discord.ButtonStyle.success
PRIMARY = discord.ButtonStyle.primary
SECONDARY = discord.ButtonStyle.secondary
DANGER = discord.ButtonStyle.danger


class PlayerBoard(_BoardView):
    TIER = "player"
    BUTTONS = (
        ("btn.browse", "panel:player:customs", SUCCESS, 0, _open_customs),
        ("btn.refresh", "panel:player:refresh", SECONDARY, 0, _do_refresh),
    )


class AdminBoard(_BoardView):
    TIER = "admin"
    BUTTONS = (
        ("btn.create_custom", "panel:admin:create", SUCCESS, 0, _open_create),
        ("btn.manage_customs", "panel:admin:manage", PRIMARY, 0, _open_manage_own),
        ("btn.maps", "panel:admin:maps", SECONDARY, 0, _open_maps),
        ("btn.bans", "panel:admin:bans", DANGER, 1, _open_bans),
        ("btn.riot_approvals", "panel:admin:riot_approvals", PRIMARY, 1, _open_rank_approvals),
        ("btn.audit", "panel:admin:audit", SECONDARY, 1, _open_audit),
        ("btn.refresh", "panel:admin:refresh", SECONDARY, 1, _do_refresh),
    )


class SuperBoard(_BoardView):
    TIER = "superadmin"
    BUTTONS = (
        ("btn.bot_roles", "panel:super:roles", PRIMARY, 0, _open_roles),
        ("btn.manage_any", "panel:super:manage", PRIMARY, 0, _open_manage_any),
        ("btn.audit", "panel:super:audit", SECONDARY, 0, _open_audit),
        ("btn.language", "panel:super:language", SECONDARY, 0, _open_language),
        ("btn.riot_approvals", "panel:super:riot_approvals", PRIMARY, 1, _open_rank_approvals),
        ("btn.prune", "panel:super:prune", DANGER, 1, _open_prune),
        ("btn.refresh", "panel:super:refresh", SECONDARY, 1, _do_refresh),
    )


BOARD_VIEW = {"player": PlayerBoard, "admin": AdminBoard, "superadmin": SuperBoard}
board.register_board_views(BOARD_VIEW)


# ================================================================ the cog ====
def _channel_rule(tier: str) -> int | None:
    """The channel id this tier is pinned to, if one is configured."""
    key = TIER_CHANNEL.get(tier)
    return getattr(settings, key) if key else None


def _infer_tier(channel_id: int | None) -> str:
    if channel_id and channel_id == settings.superadmin_panel_channel:
        return "superadmin"
    if channel_id and channel_id == settings.admin_panel_channel:
        return "admin"
    return "player"


def _channel_error(itx: discord.Interaction, tier: str) -> str | None:
    """Refuse to post a board outside the channel it's pinned to, and refuse to
    put a lower tier into a staff channel."""
    pinned = _channel_rule(tier)
    if pinned and itx.channel_id != pinned:
        return t("panel.err.pinned", tier=tier_label(tier), channel_id=pinned,
                 env=TIER_CHANNEL[tier].upper())
    for other, key in TIER_CHANNEL.items():
        other_id = getattr(settings, key)
        if other != tier and other_id and itx.channel_id == other_id:
            return t("panel.err.reserved", other=tier_label(other),
                     tier=tier_label(tier))
    return None


async def _drop_old_board(guild: discord.Guild, previous: tuple[int, int] | None) -> None:
    """Delete the board this one replaces, so a channel never shows two."""
    if not previous:
        return
    channel = guild.get_channel(previous[0])
    if not isinstance(channel, discord.abc.Messageable):
        return
    try:
        await (await channel.fetch_message(previous[1])).delete()
    except discord.HTTPException:
        pass


class PanelCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(description=L("cmd.panel.desc"))
    @app_commands.guild_only()
    @app_commands.describe(tier=L("cmd.panel.tier"))
    @app_commands.choices(tier=[
        app_commands.Choice(name=L("cmd.panel.choice.player"), value="player"),
        app_commands.Choice(name=L("cmd.panel.choice.admin"), value="admin"),
        app_commands.Choice(name=L("cmd.panel.choice.superadmin"), value="superadmin"),
    ])
    async def panel(self, itx: discord.Interaction, tier: app_commands.Choice[str] | None = None):
        chosen = tier.value if tier else _infer_tier(itx.channel_id)

        if not await _guard(itx, TIER_LEVEL[chosen]):
            return
        problem = _channel_error(itx, chosen)
        if problem:
            return await reply(itx, problem)

        await itx.response.send_message(
            embed=await board.embed_for(itx.guild, chosen),
            view=BOARD_VIEW[chosen](),
        )
        msg = await itx.original_response()
        previous = await panel_svc.save(itx.guild_id, chosen, itx.channel_id, msg.id,
                                        itx.user.id)
        await _drop_old_board(itx.guild, previous)

    @app_commands.command(name="language", description=L("cmd.language.desc"))
    @app_commands.guild_only()
    @app_commands.describe(language=L("cmd.language.param"))
    @app_commands.choices(language=[
        app_commands.Choice(name=LANG_NAME[code], value=code) for code in LANGS
    ])
    async def language(self, itx: discord.Interaction,
                       language: app_commands.Choice[str]):
        """Superadmin-only: the language every message in this server is written in."""
        if not await _guard(itx, SUPER):
            return
        await reply(itx, await set_guild_language(itx, language.value))


async def setup(bot: commands.Bot):
    await bot.add_cog(PanelCog(bot))
