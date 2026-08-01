"""Control boards — one per tier, one per channel.

`/panel` posts a **live board**: a public message whose embed mirrors the server
state (open games, seats, map pool) and redraws itself whenever anything
changes. Its buttons never touch the board — each opens a *private* screen (see
`bot.core.nav`) that morphs in place as you navigate, so several people can use
one board at the same time.

There are three boards and they are meant to live in three different channels:

    #customs      /panel                 → 🎮 player board   (everyone)
    #admin-panel  /panel tier:admin      → 🛡 admin board    (Admin+)
    #super-panel  /panel tier:superadmin → 👑 super board    (SuperAdmin)

Set `ADMIN_PANEL_CHANNEL` / `SUPERADMIN_PANEL_CHANNEL` in `.env` and the staff
boards refuse to be posted anywhere else.

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
from bot.core.embeds import VAL_RED, custom_registration_embed, ts
from bot.core.errors import BotError
from bot.core.nav import Screen
from bot.core.permissions import (
    ADMIN,
    PLAYER,
    RANK_NAME,
    SUPER,
    can_manage_custom,
    is_superadmin,
    member_level,
)
from bot.core.ui import reply
from bot.db import SessionLocal
from bot.db.models import AuditLog, Custom, Map, MemberRole
from bot.services import bans as bans_svc
from bot.services import custom as custom_svc
from bot.services import draft as draft_svc
from bot.services import maps as maps_svc
from bot.services import panel_svc

TIER_LEVEL = {"player": PLAYER, "admin": ADMIN, "superadmin": SUPER}
TIER_LABEL = {"player": "🎮 Customs", "admin": "🛡 Admin", "superadmin": "👑 Super Admin"}
TIER_CHANNEL = {
    "admin": "admin_panel_channel",
    "superadmin": "superadmin_panel_channel",
}


async def _guard(itx: discord.Interaction, level: int) -> bool:
    """Shared level check; explains what the caller is missing."""
    if await member_level(itx.user) >= level:
        return True
    await reply(itx, f"This action needs the **{RANK_NAME[level]}** role.")
    return False


async def _get_custom(itx: discord.Interaction, custom_id: int) -> Custom | None:
    async with SessionLocal() as s:
        c = await s.get(Custom, custom_id)
    if not c or c.guild_id != itx.guild_id:
        await reply(itx, f"Custom #{custom_id} no longer exists.")
        return None
    return c


def _picker_options(customs: list[Custom]) -> list[discord.SelectOption]:
    return [
        discord.SelectOption(
            label=f"#{c.custom_id} {c.name}"[:100],
            description=f"{c.format} · {c.team_size}v{c.team_size} · {c.state}"[:100],
            value=str(c.custom_id),
            emoji=board.STATE_EMOJI.get(c.state),
        )
        for c in customs[:25]
    ]


# ============================================================== modals ========
class CreateCustomModal(discord.ui.Modal, title="Create custom"):
    """Step 2 of creation — map pool and draft mode were already chosen on the
    Create screen. (Discord modals cannot contain dropdowns, hence two steps.)"""

    name = discord.ui.TextInput(label="Name", placeholder="Friday 5v5", max_length=64)
    fmt = discord.ui.TextInput(label="Format (BO1/BO3/BO5)", default="BO1", max_length=3)
    team_size = discord.ui.TextInput(label="Team size (1-5)", default="5", max_length=1)
    start = discord.ui.TextInput(label="Start — HH:MM (server time) or ISO",
                                 placeholder="20:00")

    def __init__(self, maps: list[str] | None = None, draft_mode: str = "snake",
                 captain_method: str = "random"):
        super().__init__()
        self.maps = maps or []
        self.draft_mode = draft_mode
        self.captain_method = captain_method

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
                captain_method=self.captain_method,
            )
        except (BotError, ValueError) as e:
            return await reply(itx, str(e))
        reg = itx.guild.get_channel(c.reg_channel)
        await reply(itx, f"Created **Custom #{c.custom_id}** ({c.team_size}v{c.team_size}) → "
                         f"{reg.mention if reg else '#custom-' + str(c.custom_id)}")


class AddMapModal(discord.ui.Modal, title="Add map"):
    name = discord.ui.TextInput(label="Map name", placeholder="Ascent", max_length=32)

    def __init__(self, screen: "MapsScreen"):
        super().__init__()
        self.screen = screen

    async def on_submit(self, itx: discord.Interaction):
        name = self.name.value.strip()
        if not name:
            return await reply(itx, "Map name can't be empty.")
        async with SessionLocal() as s:
            if await s.get(Map, (itx.guild_id, name)):
                return await reply(itx, f"**{name}** is already in the pool.")
            s.add(Map(guild_id=itx.guild_id, name=name, enabled=True))
            await s.commit()
        await self.screen.repaint()        # redraw the pool behind the modal
        board.schedule(itx.guild)
        await reply(itx, f"Added **{name}**.")


class BanReasonModal(discord.ui.Modal, title="Ban player"):
    reason = discord.ui.TextInput(label="Reason (optional)", required=False,
                                  style=discord.TextStyle.paragraph)

    def __init__(self, member: discord.Member, screen: "BansScreen"):
        super().__init__()
        self.member = member
        self.screen = screen

    async def on_submit(self, itx: discord.Interaction):
        created = await bans_svc.ban(itx.guild_id, self.member.id, itx.user.id,
                                     self.reason.value or None)
        await audit.log(itx.guild_id, itx.user.id, "ban", str(self.member.id))
        await self.screen.repaint()
        board.schedule(itx.guild)
        await reply(itx, f"{'Banned' if created else 'Already banned'} {self.member.mention}.")


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
            title="🎮 Customs — pick a game",
            description="Choose one below to see its roster and register.",
            color=VAL_RED,
        )
        if not self._customs:
            e.description = "No games are open right now. Check back later."
            return e
        lines = []
        for c in self._customs[:25]:
            mine = await actions.is_registered(c.custom_id, self.user_id)
            lines.append(await board.custom_line(c) + ("  ✅ **you're in**" if mine else ""))
        e.add_field(name=f"Open games ({len(self._customs)})",
                    value="\n".join(lines)[:1024], inline=False)
        return e

    async def build(self) -> None:
        if self._customs:
            self.add_item(self._Picker(self._customs))

    class _Picker(discord.ui.Select):
        def __init__(self, customs: list[Custom]):
            super().__init__(placeholder="Choose a game…",
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
            return discord.Embed(title="Gone",
                                 description=f"Custom #{self.cid} no longer exists.",
                                 color=VAL_RED)
        r = await custom_svc.roster(self.cid)
        self._open = c.state in ("registration", "full")
        self._registered = self.user_id in r.all
        e = custom_registration_embed(c, r.starters, r.size, r.waitlist)
        if self._registered:
            seat = ("🪑 on the waitlist — you play if a starter drops"
                    if self.user_id in r.waitlist else "✅ you're in the game")
            e.add_field(name="You", value=seat, inline=False)
        elif not self._open:
            e.add_field(name="You", value="Registration is closed for this game.",
                        inline=False)
        return e

    async def build(self) -> None:
        self.add_item(self._Act("Register", "register", discord.ButtonStyle.success, "✅",
                                disabled=self._registered or not self._open))
        self.add_item(self._Act("Leave", "leave", discord.ButtonStyle.secondary, "🚪",
                                disabled=not self._registered))

    class _Act(discord.ui.Button):
        def __init__(self, label, action, style, emoji, *, disabled=False):
            super().__init__(label=label, style=style, emoji=emoji,
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
        self.selected: list[str] = []
        self.draft_mode = "snake"
        self.captain_method = "random"
        self._maps: list[Map] = []
        self._competitive: list[str] = []

    async def embed(self) -> discord.Embed:
        self._maps = await maps_svc.enabled_maps(self.guild_id)
        self._competitive = await maps_svc.competitive_names(self.guild_id)
        e = discord.Embed(
            title="➕ Create a custom",
            description="Set the map pool and draft mode here, then **Continue** "
                        "for name, format, team size and start time.",
            color=VAL_RED,
        )
        e.add_field(
            name="🗺 Map pool",
            value=", ".join(self.selected) if self.selected
            else f"_all {len(self._maps)} enabled maps_",
            inline=False,
        )
        e.add_field(name="🎲 Draft",
                    value=draft_svc.DRAFT_MODE_LABEL[self.draft_mode], inline=True)
        e.add_field(
            name="👑 Captains",
            value=f"{draft_svc.CAPTAIN_METHOD_LABEL[self.captain_method]}\n"
                  f"_{draft_svc.CAPTAIN_METHOD_HELP[self.captain_method]}_",
            inline=True,
        )
        e.add_field(name="⭐ Competitive pool",
                    value=", ".join(self._competitive) if self._competitive else "_not set_",
                    inline=False)
        if not self._maps:
            e.description = "⚠️ No enabled maps — seed the pool in **Maps** first."
        return e

    async def build(self) -> None:
        if not self._maps:
            return
        self.add_item(self._Pool(self._maps, self.selected))
        self.add_item(self._DraftMode(self.draft_mode))
        self.add_item(self._Captains(self.captain_method))
        self.add_item(self._Competitive())
        self.add_item(self._Continue())

    class _Pool(discord.ui.Select):
        def __init__(self, maps: list[Map], selected: list[str]):
            opts = [
                discord.SelectOption(label=m.name, value=m.name, default=m.name in selected)
                for m in maps[:25]
            ]
            super().__init__(
                placeholder="Map pool — pick 2+ maps (none = whole enabled pool)…",
                options=opts, min_values=0, max_values=len(opts), row=0,
            )

        async def callback(self, itx: discord.Interaction):
            self.view.selected = list(self.values)
            await self.view.reload(itx)

    class _DraftMode(discord.ui.Select):
        def __init__(self, current: str):
            super().__init__(
                placeholder="Draft mode — snake (default) or one by one…",
                options=[
                    discord.SelectOption(
                        label="Snake draft", value="snake", emoji="🐍",
                        description="A, BB, AA, BB … — evens out the first-pick edge",
                        default=current == "snake",
                    ),
                    discord.SelectOption(
                        label="One by one", value="alternate", emoji="🔁",
                        description="A, B, A, B … — strict alternating picks",
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
                placeholder="Captains — how the two captains are chosen…",
                options=[
                    discord.SelectOption(
                        label=draft_svc.CAPTAIN_METHOD_LABEL[m], value=m,
                        description=draft_svc.CAPTAIN_METHOD_HELP[m][:100],
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
            super().__init__(label="Competitive pool", style=discord.ButtonStyle.primary,
                             emoji="⭐", row=3)

        async def callback(self, itx: discord.Interaction):
            view: CreateScreen = self.view
            if not view._competitive:
                return await reply(
                    itx, "No competitive pool set yet — set it in **Maps → "
                         "⭐ Competitive pool**."
                )
            view.selected = list(view._competitive)
            await view.reload(itx)

    class _Continue(discord.ui.Button):
        def __init__(self):
            super().__init__(label="Continue", style=discord.ButtonStyle.success,
                             emoji="➡️", row=3)

        async def callback(self, itx: discord.Interaction):
            view: CreateScreen = self.view
            if view.selected and len(view.selected) < 2:
                return await reply(itx, "Pick at least 2 maps, or none for the whole pool.")
            await itx.response.send_modal(
                CreateCustomModal(view.selected, view.draft_mode, view.captain_method)
            )


# ------------------------------------------------------- admin: manage ------
class ManageListScreen(_Gated):
    """The customs this admin may run — all of them, for a superadmin."""

    LEVEL = ADMIN

    def __init__(self, guild_id: int, owner_id: int | None, is_super: bool,
                 parent: Screen | None = None):
        super().__init__(parent)
        self.guild_id = guild_id
        self.owner_id = owner_id  # None = every custom in the guild
        self.is_super = is_super
        self._customs: list[Custom] = []

    async def embed(self) -> discord.Embed:
        self._customs = await board.active_customs(self.guild_id, owned_by=self.owner_id)
        e = discord.Embed(
            title="🔧 Manage customs",
            description=("Every active custom in the server."
                         if self.owner_id is None else "The customs you own."),
            color=VAL_RED,
        )
        e.add_field(
            name=f"Active ({len(self._customs)})",
            value=await board.customs_field(self._customs, with_owner=True),
            inline=False,
        )
        if not self._customs and self.owner_id is not None:
            e.description = ("You don't own an active custom. Create one, or ask a "
                             "superadmin to transfer one to you.")
        return e

    async def build(self) -> None:
        if self._customs:
            self.add_item(self._Picker(self._customs))

    class _Picker(discord.ui.Select):
        def __init__(self, customs: list[Custom]):
            super().__init__(placeholder="Pick a custom to manage…",
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
            return discord.Embed(title="Gone",
                                 description=f"Custom #{self.cid} no longer exists.",
                                 color=VAL_RED)
        self._alive, self._state = True, c.state
        r = await custom_svc.roster(self.cid)
        self._roster_full = bool(r.size) and len(r.starters) >= r.size
        method = c.captain_method or "random"
        e = discord.Embed(
            title=f"🔧 Custom #{c.custom_id} — {c.name}",
            description=(
                f"{board.STATE_EMOJI.get(c.state, '•')} **{c.state}**  ·  "
                f"{c.format}  ·  **{c.team_size}v{c.team_size}**\n"
                f"**Starts:** {ts(c.start_time, 'F')} ({ts(c.start_time, 'R')})\n"
                f"**Map pool:** {', '.join(json.loads(c.map_pool))}\n"
                f"**Draft:** {draft_svc.DRAFT_MODE_LABEL.get(c.draft_mode, c.draft_mode)}\n"
                f"**Captains:** {draft_svc.CAPTAIN_METHOD_LABEL.get(method, method)} "
                f"_(set at creation)_"
            ),
            color=VAL_RED,
        )
        e.add_field(name="Owner", value=f"<@{c.owner_id}>", inline=True)
        e.add_field(name="Seats", value=f"{len(r.starters)}/{r.size}", inline=True)
        e.add_field(name="🪑 Waitlist", value=str(len(r.waitlist)), inline=True)
        e.add_field(
            name="Players",
            value="\n".join(f"• <@{u}>" for u in r.starters) or "_nobody yet_",
            inline=False,
        )
        if self._state == "ready":
            e.add_field(
                name="🔔 Ready check running",
                value="Players are confirming in the custom's channel. **Start** "
                      "or **Force start** cuts it short and begins anyway.",
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
                     and self.cid not in actions.ACTIVE_READY)
        self.add_item(self._Transfer())
        self.add_item(self._ReadyCheck(disabled=not can_check))
        self.add_item(self._Start("Start", False, discord.ButtonStyle.success, "▶️",
                                  disabled=not startable))
        self.add_item(self._Start("Force start", True, discord.ButtonStyle.success, "⏩",
                                  disabled=not startable))
        self.add_item(self._End(disabled=not endable))
        self.add_item(self._Delete())

    class _ReadyCheck(discord.ui.Button):
        def __init__(self, *, disabled):
            super().__init__(label="Ready check", style=discord.ButtonStyle.primary,
                             emoji="🔔", disabled=disabled, row=1)

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
            super().__init__(placeholder="Transfer ownership to…", max_values=1, row=0)

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
            await reply(itx, f"Ownership of #{view.cid} → {new.mention} "
                             f"(they've been notified).")

    class _Start(discord.ui.Button):
        def __init__(self, label, partial, style, emoji, *, disabled):
            super().__init__(label=label, style=style, emoji=emoji,
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
            super().__init__(label="End", style=discord.ButtonStyle.primary, emoji="🏁",
                             disabled=disabled, row=2)

        async def callback(self, itx: discord.Interaction):
            view: ManageScreen = self.view
            # Ending deletes the custom's voice AND text channels — ack first.
            await itx.response.defer()
            try:
                await actions.end_custom(itx, view.cid)
            except BotError as e:
                return await reply(itx, str(e))
            board.schedule(itx.guild)
            await reply(itx, f"Ended Custom #{view.cid}.")
            # The custom is gone from the active list — go back to it rather than
            # leaving a manage screen for something that no longer runs.
            if view.parent is not None:
                await view.goto(itx, view.parent)
            else:
                await view.reload(itx)

    class _Delete(discord.ui.Button):
        def __init__(self):
            super().__init__(label="Delete", style=discord.ButtonStyle.danger, emoji="🗑",
                             row=2)

        async def callback(self, itx: discord.Interaction):
            view: ManageScreen = self.view
            c = await _get_custom(itx, view.cid)
            if not c:
                return
            if not await can_manage_custom(c, itx.user):
                return await reply(itx, "You can't manage this custom.")
            await view.goto(itx, ConfirmScreen(
                parent=view,
                title=f"🗑 Delete Custom #{view.cid}?",
                description=f"**{c.name}** — its channel, voice channels and queue "
                            f"all go away. This can't be undone.",
                confirm=_delete_custom_action(view.cid),
                allow_force=view.is_super,
                after=view.parent,
            ))


def _delete_custom_action(custom_id: int):
    async def run(itx: discord.Interaction, force: bool) -> str:
        await actions.cancel_ready_check(custom_id, "🗑 Custom deleted.")
        await custom_svc.delete_custom(custom_id, itx.guild, force=force)
        await audit.log(itx.guild_id, itx.user.id, "custom_delete", str(custom_id),
                        force=force)
        board.schedule(itx.guild)
        return f"Deleted Custom #{custom_id}."

    return run


# ------------------------------------------------------------ admin: maps ---
class MapsScreen(_Gated):
    """The pool, its on/off state and the ⭐ competitive rotation, all visible
    at once — tick as many as you like in one go."""

    LEVEL = ADMIN

    def __init__(self, guild_id: int, parent: Screen | None = None):
        super().__init__(parent)
        self.guild_id = guild_id
        self._maps: list[Map] = []

    async def embed(self) -> discord.Embed:
        self._maps = await maps_svc.all_maps(self.guild_id)
        e = discord.Embed(title="🗺 Map pool", color=VAL_RED)
        if not self._maps:
            e.description = "No maps configured — hit **Seed defaults**."
            return e
        comp = [m.name for m in self._maps if m.competitive]
        e.description = "\n".join(
            f"{'🟢' if m.enabled else '🔴'} {m.name}{' ⭐' if m.competitive else ''}"
            for m in self._maps
        )[:4096]
        e.add_field(name="⭐ Competitive pool",
                    value=", ".join(comp) if comp else "_not set_", inline=False)
        e.set_footer(text="Ticking a map competitive enables it for play.")
        return e

    async def build(self) -> None:
        if self._maps:
            self.add_item(self._Toggle(self._maps))
            self.add_item(self._Competitive(self._maps))
        self.add_item(self._Seed())
        self.add_item(self._Add())

    class _Toggle(discord.ui.Select):
        def __init__(self, maps: list[Map]):
            opts = [
                discord.SelectOption(
                    label=m.name, value=m.name,
                    description="enabled" if m.enabled else "disabled",
                    emoji="🟢" if m.enabled else "🔴",
                )
                for m in maps[:25]
            ]
            super().__init__(placeholder="Toggle maps on/off (pick as many as you like)…",
                             options=opts, min_values=1, max_values=len(opts), row=0)

        async def callback(self, itx: discord.Interaction):
            flipped = []
            async with SessionLocal() as s:
                for name in self.values:
                    m = await s.get(Map, (itx.guild_id, name))
                    if not m:  # removed by someone else meanwhile
                        continue
                    m.enabled = not m.enabled
                    flipped.append(f"**{name}** → {'enabled' if m.enabled else 'disabled'}")
                await s.commit()
            await self.view.reload(itx)
            board.schedule(itx.guild)
            await reply(itx, "\n".join(flipped) if flipped else "Nothing to toggle.")

    class _Competitive(discord.ui.Select):
        """Sets the competitive pool to exactly what's ticked (empty clears it)."""

        def __init__(self, maps: list[Map]):
            opts = [
                discord.SelectOption(
                    label=m.name, value=m.name, emoji="⭐" if m.competitive else None,
                    description="in the competitive pool" if m.competitive else None,
                    default=m.competitive,
                )
                for m in maps[:25]
            ]
            super().__init__(placeholder="⭐ Competitive pool — tick the current rotation…",
                             options=opts, min_values=0, max_values=len(opts), row=1)

        async def callback(self, itx: discord.Interaction):
            in_pool, _ = await maps_svc.set_competitive(itx.guild_id, list(self.values))
            await audit.log(itx.guild_id, itx.user.id, "maps_competitive",
                            meta=",".join(in_pool))
            await self.view.reload(itx)
            board.schedule(itx.guild)
            await reply(
                itx,
                f"⭐ Competitive pool: **{', '.join(in_pool)}** (enabled for play)."
                if in_pool else "Competitive pool cleared.",
            )

    class _Seed(discord.ui.Button):
        def __init__(self):
            super().__init__(label="Seed defaults", style=discord.ButtonStyle.primary,
                             emoji="🌱", row=2)

        async def callback(self, itx: discord.Interaction):
            added = await maps_svc.seed(itx.guild_id)
            await self.view.reload(itx)
            board.schedule(itx.guild)
            await reply(itx, f"Seeded {len(added)} map(s)." if added else "Pool already seeded.")

    class _Add(discord.ui.Button):
        def __init__(self):
            super().__init__(label="Add map", style=discord.ButtonStyle.success,
                             emoji="➕", row=2)

        async def callback(self, itx: discord.Interaction):
            await itx.response.send_modal(AddMapModal(self.view))


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
            title="🔨 Bans",
            description="Banned players can't register for any game in this server.",
            color=VAL_RED,
        )
        e.add_field(
            name=f"Banned ({len(rows)})",
            value="\n".join(f"• <@{b.user_id}>" + (f" — {b.reason}" if b.reason else "")
                            for b in rows[:20]) or "_nobody_",
            inline=False,
        )
        e.add_field(name="Selected",
                    value=self.target.mention if self.target else "_pick a player below_",
                    inline=False)
        return e

    async def build(self) -> None:
        self.add_item(self._Member())
        self.add_item(self._Ban(disabled=self.target is None))
        self.add_item(self._Unban(disabled=self.target is None))

    class _Member(discord.ui.UserSelect):
        def __init__(self):
            super().__init__(placeholder="Player…", max_values=1, row=0)

        async def callback(self, itx: discord.Interaction):
            self.view.target = self.values[0]
            await self.view.reload(itx)

    class _Ban(discord.ui.Button):
        def __init__(self, *, disabled):
            super().__init__(label="Ban", style=discord.ButtonStyle.danger, emoji="🔨",
                             disabled=disabled, row=1)

        async def callback(self, itx: discord.Interaction):
            view: BansScreen = self.view
            await itx.response.send_modal(BanReasonModal(view.target, view))

    class _Unban(discord.ui.Button):
        def __init__(self, *, disabled):
            super().__init__(label="Unban", style=discord.ButtonStyle.success, emoji="♻️",
                             disabled=disabled, row=1)

        async def callback(self, itx: discord.Interaction):
            view: BansScreen = self.view
            removed = await bans_svc.unban(itx.guild_id, view.target.id)
            await audit.log(itx.guild_id, itx.user.id, "unban", str(view.target.id))
            await view.reload(itx)
            await reply(itx, f"{'Unbanned' if removed else 'Was not banned'} "
                             f"{view.target.mention}.")


# ----------------------------------------------------------- shared: audit --
class AuditScreen(_Gated):
    LEVEL = ADMIN

    def __init__(self, guild_id: int, parent: Screen | None = None):
        super().__init__(parent)
        self.guild_id = guild_id

    async def embed(self) -> discord.Embed:
        async with SessionLocal() as s:
            rows = await s.execute(
                select(AuditLog).where(AuditLog.guild_id == self.guild_id)
                .order_by(AuditLog.id.desc()).limit(15)
            )
            entries = [r[0] for r in rows.all()]
        e = discord.Embed(
            title="📜 Audit log",
            description="\n".join(
                f"`{en.ts:%m-%d %H:%M}` <@{en.actor_id}> **{en.action}** {en.target or ''}"
                for en in entries
            ) or "_No audit entries yet._",
            color=VAL_RED,
        )
        e.set_footer(text="15 most recent entries")
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
            title="🛡 Bot roles",
            description="Roles granted here are on top of the `ADMIN_ROLE` / "
                        "`SUPERADMIN_ROLE` Discord roles from `.env`.",
            color=VAL_RED,
        )
        for role in ("superadmin", "admin"):
            ids = by_role.get(role, [])
            e.add_field(
                name=f"{role} ({len(ids)})",
                value=", ".join(f"<@{u}>" for u in ids[:15]) or "_none granted_",
                inline=False,
            )
        e.add_field(
            name="Selected",
            value=f"{self.target.mention if self.target else '_pick a member_'} → "
                  f"**{self.role}**",
            inline=False,
        )
        return e

    async def build(self) -> None:
        self.add_item(self._Member())
        self.add_item(self._Role(self.role))
        self.add_item(self._Apply("Grant", True, discord.ButtonStyle.success,
                                  disabled=self.target is None))
        self.add_item(self._Apply("Revoke", False, discord.ButtonStyle.danger,
                                  disabled=self.target is None))

    class _Member(discord.ui.UserSelect):
        def __init__(self):
            super().__init__(placeholder="Member…", max_values=1, row=0)

        async def callback(self, itx: discord.Interaction):
            self.view.target = self.values[0]
            await self.view.reload(itx)

    class _Role(discord.ui.Select):
        def __init__(self, current: str):
            super().__init__(
                placeholder="Role…", row=1,
                options=[discord.SelectOption(label=r, value=r, default=r == current)
                         for r in ("player", "admin", "superadmin")],
            )

        async def callback(self, itx: discord.Interaction):
            self.view.role = self.values[0]
            await self.view.reload(itx)

    class _Apply(discord.ui.Button):
        def __init__(self, label, grant, style, *, disabled):
            super().__init__(label=label, style=style, disabled=disabled, row=2)
            self.grant = grant

        async def callback(self, itx: discord.Interaction):
            view: RolesScreen = self.view
            if not await is_superadmin(itx.user):
                return await reply(itx, "Superadmin only.")
            key = (itx.guild_id, view.target.id, view.role)
            async with SessionLocal() as s:
                row = await s.get(MemberRole, key)
                if self.grant and not row:
                    s.add(MemberRole(guild_id=key[0], user_id=key[1], role=key[2]))
                elif not self.grant and row:
                    await s.delete(row)
                await s.commit()
            action = "grant" if self.grant else "revoke"
            await audit.log(itx.guild_id, itx.user.id, action, str(view.target.id),
                            role=view.role)
            await view.reload(itx)
            board.schedule(itx.guild)
            await reply(itx, f"{'Granted' if self.grant else 'Revoked'} **{view.role}** "
                             f"{'to' if self.grant else 'from'} {view.target.mention}.")


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
        e = discord.Embed(title=self.heading, description=body, color=VAL_RED)
        if self.allow_force:
            e.set_footer(text="Force also overrides the in-progress guard "
                              "(disconnects anyone in the team voice channels).")
        return e

    async def build(self) -> None:
        self.add_item(self._Go("Confirm", False))
        if self.allow_force:
            self.add_item(self._Go("Force", True))

    class _Go(discord.ui.Button):
        def __init__(self, label: str, force: bool):
            super().__init__(label=label, style=discord.ButtonStyle.danger, row=0)
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
        msg = f"Pruned {deleted} custom(s)."
        if skipped:
            msg += f" Skipped (in progress): {', '.join(map(str, skipped))}."
        return msg

    return run


# ============================================================== boards =======
class _BoardView(discord.ui.View):
    """A persistent public board. Buttons only ever *open* a private screen, so
    the board message is never replaced and one board serves the whole channel."""

    TIER = "player"

    def __init__(self):
        super().__init__(timeout=None)

    async def interaction_check(self, itx: discord.Interaction) -> bool:
        return await _guard(itx, TIER_LEVEL[self.TIER])

    async def refresh_here(self, itx: discord.Interaction) -> None:
        """Redraw this board using the click's own interaction — instant, and
        it costs no extra API call."""
        await itx.response.edit_message(embed=await board.embed_for(itx.guild, self.TIER))


class PlayerBoard(_BoardView):
    TIER = "player"

    @discord.ui.button(label="Browse & join", style=discord.ButtonStyle.success,
                       emoji="🎮", row=0, custom_id="panel:player:customs")
    async def customs(self, itx: discord.Interaction, _b: discord.ui.Button):
        await CustomsScreen(itx.guild_id, itx.user.id).open(itx)

    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.secondary,
                       emoji="🔄", row=0, custom_id="panel:player:refresh")
    async def refresh(self, itx: discord.Interaction, _b: discord.ui.Button):
        await self.refresh_here(itx)


class AdminBoard(_BoardView):
    TIER = "admin"

    @discord.ui.button(label="Create custom", style=discord.ButtonStyle.success,
                       emoji="➕", row=0, custom_id="panel:admin:create")
    async def create(self, itx: discord.Interaction, _b: discord.ui.Button):
        await CreateScreen(itx.guild_id).open(itx)

    @discord.ui.button(label="Manage customs", style=discord.ButtonStyle.primary,
                       emoji="🔧", row=0, custom_id="panel:admin:manage")
    async def manage(self, itx: discord.Interaction, _b: discord.ui.Button):
        is_super = await member_level(itx.user) >= SUPER
        await ManageListScreen(
            itx.guild_id, None if is_super else itx.user.id, is_super
        ).open(itx)

    @discord.ui.button(label="Maps", style=discord.ButtonStyle.secondary,
                       emoji="🗺", row=0, custom_id="panel:admin:maps")
    async def maps(self, itx: discord.Interaction, _b: discord.ui.Button):
        await MapsScreen(itx.guild_id).open(itx)

    @discord.ui.button(label="Bans", style=discord.ButtonStyle.danger,
                       emoji="🔨", row=1, custom_id="panel:admin:bans")
    async def bans(self, itx: discord.Interaction, _b: discord.ui.Button):
        await BansScreen(itx.guild_id).open(itx)

    @discord.ui.button(label="Audit", style=discord.ButtonStyle.secondary,
                       emoji="📜", row=1, custom_id="panel:admin:audit")
    async def auditlog(self, itx: discord.Interaction, _b: discord.ui.Button):
        await AuditScreen(itx.guild_id).open(itx)

    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.secondary,
                       emoji="🔄", row=1, custom_id="panel:admin:refresh")
    async def refresh(self, itx: discord.Interaction, _b: discord.ui.Button):
        await self.refresh_here(itx)


class SuperBoard(_BoardView):
    TIER = "superadmin"

    @discord.ui.button(label="Bot roles", style=discord.ButtonStyle.primary,
                       emoji="🛡", row=0, custom_id="panel:super:roles")
    async def roles(self, itx: discord.Interaction, _b: discord.ui.Button):
        await RolesScreen(itx.guild_id).open(itx)

    @discord.ui.button(label="Manage any custom", style=discord.ButtonStyle.primary,
                       emoji="🔧", row=0, custom_id="panel:super:manage")
    async def manage(self, itx: discord.Interaction, _b: discord.ui.Button):
        await ManageListScreen(itx.guild_id, None, True).open(itx)

    @discord.ui.button(label="Audit", style=discord.ButtonStyle.secondary,
                       emoji="📜", row=0, custom_id="panel:super:audit")
    async def auditlog(self, itx: discord.Interaction, _b: discord.ui.Button):
        await AuditScreen(itx.guild_id).open(itx)

    @discord.ui.button(label="Prune all customs", style=discord.ButtonStyle.danger,
                       emoji="🧹", row=1, custom_id="panel:super:prune")
    async def prune(self, itx: discord.Interaction, _b: discord.ui.Button):
        guild_id = itx.guild_id

        async def blast_radius() -> str:
            customs = await board.active_customs(guild_id)
            return (f"**{len(customs)} active** custom(s) plus any finished ones, "
                    f"with their channels and queues. This can't be undone.")

        await ConfirmScreen(
            parent=None,
            title="🧹 Delete every custom in this server?",
            description=blast_radius,
            confirm=_prune_action(),
            level=SUPER,
            allow_force=True,
        ).open(itx)

    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.secondary,
                       emoji="🔄", row=1, custom_id="panel:super:refresh")
    async def refresh(self, itx: discord.Interaction, _b: discord.ui.Button):
        await self.refresh_here(itx)


BOARD_VIEW = {"player": PlayerBoard, "admin": AdminBoard, "superadmin": SuperBoard}


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
        return (f"The **{TIER_LABEL[tier]}** board is pinned to <#{pinned}> "
                f"(`{TIER_CHANNEL[tier].upper()}`). Run it there.")
    for other, key in TIER_CHANNEL.items():
        other_id = getattr(settings, key)
        if other != tier and other_id and itx.channel_id == other_id:
            return (f"This channel is reserved for the **{TIER_LABEL[other]}** board — "
                    f"post the {TIER_LABEL[tier]} board somewhere else.")
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

    @app_commands.command(description="Post a live control board in this channel.")
    @app_commands.guild_only()
    @app_commands.describe(
        tier="Which board to post. Defaults to the one this channel is configured for."
    )
    @app_commands.choices(tier=[
        app_commands.Choice(name="🎮 Customs — everyone", value="player"),
        app_commands.Choice(name="🛡 Admin", value="admin"),
        app_commands.Choice(name="👑 Super Admin", value="superadmin"),
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


async def setup(bot: commands.Bot):
    await bot.add_cog(PanelCog(bot))
