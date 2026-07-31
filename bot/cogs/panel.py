"""Button-driven control panel.

`/panel` posts a persistent board with three entry buttons — Customs (everyone),
Admin panel, Super Admin. Each opens the matching menu in a NEW ephemeral
message, so the board itself is never replaced and one board serves the whole
server. Every click re-checks the caller's level.

Action *results* go through ui.reply() so they self-dismiss after 30s; the
ephemeral menus self-dismiss 30s after the last interaction (AutoDismissView).
"""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import select

from bot.core import actions, audit
from bot.core.embeds import VAL_RED
from bot.core.errors import BotError
from bot.core.permissions import (
    ADMIN,
    PLAYER,
    RANK_NAME,
    SUPER,
    can_manage_custom,
    is_superadmin,
    member_level,
)
from bot.core.ui import AutoDismissView, ConfirmView, reply, spawn
from bot.db import SessionLocal
from bot.db.models import AuditLog, Custom, Map, MemberRole, PlayerStats, User
from bot.services import custom as custom_svc
from bot.services import bans as bans_svc
from bot.services import draft as draft_svc
from bot.services import maps as maps_svc
from bot.services import queue_svc
from bot.services.identity import normalize_tag

ROLE_CHOICES = ["Duelist", "Controller", "Initiator", "Sentinel", "Flex"]
CAPTAIN_METHODS = ["random", "manual", "highest_rr", "highest_peak"]


async def role_level(member: discord.Member) -> int:
    """Effective level: Discord owner/admin, the ADMIN_ROLE/SUPERADMIN_ROLE
    Discord roles from .env, or a bot role granted in the DB."""
    return await member_level(member)


async def _guard(itx: discord.Interaction, level: int) -> bool:
    """Shared level check; explains what the caller is missing."""
    if await role_level(itx.user) >= level:
        return True
    await reply(itx, f"This action needs the **{RANK_NAME[level]}** role.")
    return False


_enabled_maps = maps_svc.enabled_maps
_all_maps = maps_svc.all_maps


async def _active_customs(guild_id: int, owned_by: int | None = None) -> list[Custom]:
    async with SessionLocal() as s:
        q = select(Custom).where(
            Custom.guild_id == guild_id,
            Custom.state.in_(custom_svc.ACTIVE_STATES),
        )
        if owned_by is not None:
            q = q.where(Custom.owner_id == owned_by)
        rows = await s.execute(q.order_by(Custom.start_time))
        return [r[0] for r in rows.all()]


# ============================================================== modals =======
class ProfileModal(discord.ui.Modal, title="Your profile"):
    riot_id = discord.ui.TextInput(label="Riot ID (Name#TAG)", placeholder="TenZ#NA1", max_length=32)
    main_role = discord.ui.TextInput(
        label="Main role (optional)", required=False,
        placeholder="Duelist / Controller / Initiator / Sentinel / Flex",
    )
    cur_rank = discord.ui.TextInput(label="Current rank (optional)", required=False, placeholder="Ascendant 2")
    cur_rr = discord.ui.TextInput(label="Current RR (optional)", required=False, placeholder="74")
    peak_rank = discord.ui.TextInput(label="Peak rank (optional)", required=False, placeholder="Immortal 1")

    async def on_submit(self, itx: discord.Interaction):
        try:
            tag = normalize_tag(self.riot_id.value)
        except BotError as e:
            return await reply(itx, str(e))
        role = self.main_role.value.strip().title() or None
        if role and role not in ROLE_CHOICES:
            return await reply(itx, f"Role must be one of: {', '.join(ROLE_CHOICES)}.")
        rr = None
        if self.cur_rr.value.strip():
            try:
                rr = int(self.cur_rr.value)
            except ValueError:
                return await reply(itx, "RR must be a number.")
        async with SessionLocal() as s:
            u = await s.get(User, itx.user.id)
            if not u:
                u = User(user_id=itx.user.id)
                s.add(u)
            u.riot_id = tag
            u.main_role = role
            u.cur_rank = self.cur_rank.value.strip() or None
            u.cur_rr = rr
            u.peak_rank = self.peak_rank.value.strip() or None
            if not await s.get(MemberRole, (itx.guild_id, itx.user.id, "player")):
                s.add(MemberRole(guild_id=itx.guild_id, user_id=itx.user.id, role="player"))
            await s.commit()
        await reply(itx, f"Saved profile as **{tag}** ✅")


class CreateCustomModal(discord.ui.Modal, title="Create custom"):
    """Step 2 of creation — map pool and draft mode were already chosen in
    CreateCustomView. (Discord modals cannot contain dropdowns, hence two steps.)"""

    name = discord.ui.TextInput(label="Name", placeholder="Friday 5v5", max_length=64)
    fmt = discord.ui.TextInput(label="Format (BO1/BO3/BO5)", default="BO1", max_length=3)
    team_size = discord.ui.TextInput(label="Team size (1-5)", default="5", max_length=1)
    start = discord.ui.TextInput(label="Start — HH:MM (server time) or ISO",
                                 placeholder="20:00")

    def __init__(self, maps: list[str] | None = None, draft_mode: str = "snake"):
        super().__init__()
        self.maps = maps or []
        self.draft_mode = draft_mode

    async def on_submit(self, itx: discord.Interaction):
        # Creating a custom writes to the DB and makes two REST calls (create
        # channel, post the embed) — far more than the 3s an un-acknowledged
        # interaction token survives. Ack first, answer on the followup.
        await itx.response.defer(ephemeral=True)
        try:
            ts = int(self.team_size.value)
            c = await actions.create_custom_flow(
                itx, name=self.name.value, fmt=self.fmt.value,
                start_raw=self.start.value, maps_csv=",".join(self.maps),
                team_size=ts, draft_mode=self.draft_mode,
            )
        except (BotError, ValueError) as e:
            return await reply(itx, str(e))
        reg = itx.guild.get_channel(c.reg_channel)
        await reply(itx, f"Created **Custom #{c.custom_id}** ({c.team_size}v{c.team_size}) → "
                         f"{reg.mention if reg else '#custom-' + str(c.custom_id)}")


class CreateCustomView(AutoDismissView):
    """Step 1 of creation — map pool and draft mode from dropdowns, then Continue."""

    def __init__(self, maps: list[Map], competitive: list[str] | None = None):
        super().__init__(timeout=120)  # longer: the modal comes after this
        self.selected: list[str] = []
        self.draft_mode = "snake"
        self.competitive = competitive or []
        self.pool = self._Pool(maps)
        self.add_item(self.pool)
        self.add_item(self._DraftMode())

    class _Pool(discord.ui.Select):
        def __init__(self, maps: list[Map]):
            opts = [discord.SelectOption(label=m.name, value=m.name) for m in maps[:25]]
            super().__init__(
                placeholder="Map pool — pick 2+ maps (none = whole enabled pool)…",
                options=opts, min_values=0, max_values=len(opts), row=0,
            )

        def sync(self, selected: list[str]) -> None:
            """Keep the ticks in step with the view's selection — the
            Competitive button changes it without touching the dropdown."""
            for o in self.options:
                o.default = o.value in selected

        async def callback(self, itx: discord.Interaction):
            self.view.selected = list(self.values)
            self.sync(self.view.selected)
            await itx.response.edit_message(
                content=self.view.summary(), view=self.view
            )

    class _DraftMode(discord.ui.Select):
        def __init__(self):
            super().__init__(
                placeholder="Draft mode — snake (default) or one by one…",
                options=[
                    discord.SelectOption(
                        label="Snake draft", value="snake", emoji="🐍",
                        description="A, BB, AA, BB … — evens out the first-pick edge",
                        default=True,
                    ),
                    discord.SelectOption(
                        label="One by one", value="alternate", emoji="🔁",
                        description="A, B, A, B … — strict alternating picks",
                    ),
                ],
                row=1,
            )

        async def callback(self, itx: discord.Interaction):
            self.view.draft_mode = self.values[0]
            for o in self.options:
                o.default = o.value == self.view.draft_mode
            await itx.response.edit_message(content=self.view.summary(), view=self.view)

    def summary(self) -> str:
        chosen = ", ".join(self.selected) if self.selected else "_all enabled maps_"
        return (
            f"**Map pool:** {chosen}\n"
            f"**Draft:** {draft_svc.DRAFT_MODE_LABEL[self.draft_mode]}\n"
            "Then hit **Continue** for the rest of the details."
        )

    @discord.ui.button(label="Competitive pool", style=discord.ButtonStyle.primary,
                       emoji="⭐", row=2)
    async def use_competitive(self, itx: discord.Interaction, _b: discord.ui.Button):
        if not self.competitive:
            return await reply(
                itx, "No competitive pool set yet — an admin can set it in "
                     "**Maps → Competitive pool**."
            )
        self.selected = list(self.competitive)
        self.pool.sync(self.selected)
        await itx.response.edit_message(content=self.summary(), view=self)

    @discord.ui.button(label="Continue", style=discord.ButtonStyle.success, emoji="➡️", row=2)
    async def go(self, itx: discord.Interaction, _b: discord.ui.Button):
        if self.selected and len(self.selected) < 2:
            return await reply(itx, "Pick at least 2 maps, or none to use the whole pool.")
        await itx.response.send_modal(CreateCustomModal(self.selected, self.draft_mode))


class AddMapModal(discord.ui.Modal, title="Add map"):
    name = discord.ui.TextInput(label="Map name", placeholder="Ascent", max_length=32)

    def __init__(self, parent: "MapsAdminView | None" = None):
        super().__init__()
        self.parent = parent

    async def on_submit(self, itx: discord.Interaction):
        name = self.name.value.strip()
        if not name:
            return await reply(itx, "Map name can't be empty.")
        async with SessionLocal() as s:
            if await s.get(Map, (itx.guild_id, name)):
                return await reply(itx, f"**{name}** is already in the pool.")
            s.add(Map(guild_id=itx.guild_id, name=name, enabled=True))
            await s.commit()
        if self.parent:
            await self.parent.refresh()  # redraw the pool list behind the modal
        await reply(itx, f"Added **{name}**.")


class BanReasonModal(discord.ui.Modal, title="Ban player"):
    reason = discord.ui.TextInput(label="Reason (optional)", required=False,
                                  style=discord.TextStyle.paragraph)

    def __init__(self, member: discord.Member):
        super().__init__()
        self.member = member

    async def on_submit(self, itx: discord.Interaction):
        created = await bans_svc.ban(itx.guild_id, self.member.id, itx.user.id,
                                     self.reason.value or None)
        await audit.log(itx.guild_id, itx.user.id, "ban", str(self.member.id))
        await reply(itx, f"{'Banned' if created else 'Already banned'} {self.member.mention}.")


# ====================================================== sub-panel: customs ===
class CustomActionView(AutoDismissView):
    """Pick a custom, then register / leave it."""

    def __init__(self, customs: list[Custom]):
        super().__init__()
        self.add_item(self._Picker(customs))

    class _Picker(discord.ui.Select):
        def __init__(self, customs: list[Custom]):
            opts = [
                discord.SelectOption(
                    label=f"#{c.custom_id} {c.name}"[:100],
                    description=f"{c.format} · {c.team_size}v{c.team_size} · {c.state}",
                    value=str(c.custom_id),
                )
                for c in customs[:25]
            ]
            super().__init__(placeholder="Choose a custom…", options=opts)

        async def callback(self, itx: discord.Interaction):
            cid = int(self.values[0])
            await itx.response.edit_message(
                content=f"Custom **#{cid}** — choose an action:",
                view=_RegLeaveView(cid),
            )


class _RegLeaveView(AutoDismissView):
    def __init__(self, custom_id: int):
        super().__init__()
        self.cid = custom_id

    @discord.ui.button(label="Register", style=discord.ButtonStyle.success, emoji="✅")
    async def register(self, itx: discord.Interaction, _b: discord.ui.Button):
        try:
            await custom_svc.register(self.cid, itx.user.id, itx.guild_id)
        except BotError as e:
            return await reply(itx, str(e))
        await reply(itx, f"Registered for Custom #{self.cid} ✅ — be in voice before ready check.")

    @discord.ui.button(label="Leave", style=discord.ButtonStyle.secondary, emoji="🚪")
    async def leave(self, itx: discord.Interaction, _b: discord.ui.Button):
        try:
            await custom_svc.leave(self.cid, itx.user.id, itx.guild_id)
        except BotError as e:
            return await reply(itx, str(e))
        await reply(itx, f"Left Custom #{self.cid}.")

    @discord.ui.button(label="Queue status", style=discord.ButtonStyle.primary, emoji="📋")
    async def status(self, itx: discord.Interaction, _b: discord.ui.Button):
        q = await queue_svc.queue_for_custom(self.cid)
        ids = await queue_svc.members(q.queue_id) if q else []
        body = "\n".join(f"• <@{u}>" for u in ids) or "_empty_"
        size = q.size if q else "?"
        await reply(itx, f"**Queue #{self.cid}** ({len(ids)}/{size})\n{body}")


# ===================================================== sub-panel: my customs =
class MyCustomsView(AutoDismissView):
    def __init__(self, customs: list[Custom], is_super: bool):
        super().__init__()
        self.is_super = is_super
        self.add_item(self._Picker(customs))

    class _Picker(discord.ui.Select):
        def __init__(self, customs):
            super().__init__(
                placeholder="Your customs…",
                options=[discord.SelectOption(label=f"#{c.custom_id} {c.name}"[:100],
                                              value=str(c.custom_id)) for c in customs[:25]],
            )

        async def callback(self, itx: discord.Interaction):
            cid = int(self.values[0])
            await itx.response.edit_message(
                content=f"Manage Custom **#{cid}**:", view=_ManageCustomView(cid, self.view.is_super)
            )


class _ManageCustomView(AutoDismissView):
    def __init__(self, custom_id: int, is_super: bool):
        super().__init__()
        self.cid = custom_id
        self.is_super = is_super
        self.method = "random"
        self.add_item(self._Method())
        self.add_item(self._TransferTo(custom_id))

    class _Method(discord.ui.Select):
        def __init__(self):
            super().__init__(
                placeholder="Captain method (for Start)…",
                options=[discord.SelectOption(label=m, value=m)
                         for m in ("random", "highest_rr", "highest_peak")],
            )

        async def callback(self, itx: discord.Interaction):
            self.view.method = self.values[0]
            await itx.response.defer()

    class _TransferTo(discord.ui.UserSelect):
        def __init__(self, custom_id: int):
            super().__init__(placeholder="Transfer ownership to…", max_values=1)
            self.cid = custom_id

        async def callback(self, itx: discord.Interaction):
            new = self.values[0]
            # Redraws the registration embed and DMs the new owner — defer first.
            await itx.response.defer(ephemeral=True)
            try:
                await actions.transfer_custom(itx, self.cid, new)
            except BotError as e:
                return await reply(itx, str(e))
            await reply(itx, f"Ownership of #{self.cid} → {new.mention} "
                             f"(they've been notified).")

    async def _start(self, itx: discord.Interaction, allow_partial: bool):
        try:
            await actions.start_match(itx, self.cid, self.method, allow_partial=allow_partial)
        except BotError as e:
            await reply(itx, str(e))

    @discord.ui.button(label="Start", style=discord.ButtonStyle.success, emoji="▶️", row=2)
    async def start(self, itx: discord.Interaction, _b: discord.ui.Button):
        await self._start(itx, allow_partial=False)

    @discord.ui.button(label="Force start", style=discord.ButtonStyle.success, emoji="⏩", row=2)
    async def force(self, itx: discord.Interaction, _b: discord.ui.Button):
        await self._start(itx, allow_partial=True)

    @discord.ui.button(label="End", style=discord.ButtonStyle.primary, emoji="🏁", row=2)
    async def end(self, itx: discord.Interaction, _b: discord.ui.Button):
        # Answer first: ending deletes the custom's voice AND text channels.
        await itx.response.send_message(f"Ending Custom #{self.cid}…", ephemeral=True)
        try:
            await actions.end_custom(itx, self.cid)
        except BotError as e:
            await itx.followup.send(str(e), ephemeral=True)

    @discord.ui.button(label="Delete", style=discord.ButtonStyle.danger, emoji="🗑", row=2)
    async def delete(self, itx: discord.Interaction, _b: discord.ui.Button):
        async with SessionLocal() as s:
            c = await s.get(Custom, self.cid)
        if not c or not await can_manage_custom(c, itx.user):
            return await reply(itx, "You can't manage this custom.")
        cv = ConfirmView(allow_force=self.is_super)
        await itx.response.send_message(f"Delete Custom #{self.cid}?", view=cv, ephemeral=True)
        await cv.wait()
        if cv.result in ("yes", "force"):
            try:
                await custom_svc.delete_custom(self.cid, itx.guild, force=(cv.result == "force"))
                await audit.log(itx.guild_id, itx.user.id, "custom_delete", str(self.cid))
                await reply(itx, f"Deleted Custom #{self.cid}.")
            except BotError as e:
                await reply(itx, str(e))


# ====================================================== sub-panel: maps =======
class MapsAdminView(AutoDismissView):
    """Multi-select: tick every map you want to flip, in one go.
    A second select holds the *competitive* pool — the rotation admins keep in
    sync with Riot's, offered as one click when a custom is created."""

    DEFAULT = maps_svc.DEFAULT_POOL

    def __init__(self, guild_id: int, maps: list[Map]):
        super().__init__()
        self.guild_id = guild_id
        self._sync(maps)

    def _sync(self, maps: list[Map]) -> None:
        """Rebuild the selects so their 🟢/🔴/⭐ labels match the DB."""
        for item in list(self.children):
            if isinstance(item, (self._Toggle, self._Competitive)):
                self.remove_item(item)
        if maps:
            self.add_item(self._Toggle(maps))
            self.add_item(self._Competitive(maps))

    @staticmethod
    def status_text(maps: list[Map]) -> str:
        if not maps:
            return "No maps configured — hit **Seed defaults**."
        comp = [m.name for m in maps if m.competitive]
        body = "Map pool:\n" + "\n".join(
            f"{'🟢' if m.enabled else '🔴'} {m.name}{' ⭐' if m.competitive else ''}"
            for m in maps
        )
        return body + "\n\n⭐ **Competitive pool:** " + (
            ", ".join(comp) if comp else "_not set_"
        )

    async def refresh(self, itx: discord.Interaction | None = None) -> None:
        """Re-read the pool and redraw. Uses the interaction response when one
        is still free, otherwise edits the panel message directly (modal submit)."""
        maps = await _all_maps(self.guild_id)
        self._sync(maps)
        body = self.status_text(maps)
        try:
            if itx is not None and not itx.response.is_done():
                await itx.response.edit_message(content=body, view=self)
            elif self.message:
                await self.message.edit(content=body, view=self)
        except discord.HTTPException:
            pass  # panel already auto-dismissed

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
            super().__init__(
                placeholder="Toggle maps on/off (pick as many as you like)…",
                options=opts, min_values=1, max_values=len(opts), row=0,
            )

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
            await self.view.refresh(itx)
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
            super().__init__(
                placeholder="⭐ Competitive pool — tick the current rotation…",
                options=opts, min_values=0, max_values=len(opts), row=1,
            )

        async def callback(self, itx: discord.Interaction):
            in_pool, _ = await maps_svc.set_competitive(itx.guild_id, list(self.values))
            await audit.log(itx.guild_id, itx.user.id, "maps_competitive",
                            meta=",".join(in_pool))
            await self.view.refresh(itx)
            await reply(
                itx,
                f"⭐ Competitive pool: **{', '.join(in_pool)}** "
                f"(enabled for play)." if in_pool else "Competitive pool cleared.",
            )

    @discord.ui.button(label="Seed defaults", style=discord.ButtonStyle.primary,
                       emoji="🌱", row=2)
    async def seed(self, itx: discord.Interaction, _b: discord.ui.Button):
        added = await maps_svc.seed(itx.guild_id)
        await self.refresh(itx)
        await reply(itx, f"Seeded {len(added)} map(s)." if added else "Pool already seeded.")

    @discord.ui.button(label="Add map", style=discord.ButtonStyle.success, emoji="➕", row=2)
    async def add(self, itx: discord.Interaction, _b: discord.ui.Button):
        await itx.response.send_modal(AddMapModal(self))


# ====================================================== sub-panel: roles =====
class RolesView(AutoDismissView):
    def __init__(self):
        super().__init__()
        self.target: discord.Member | None = None
        self.role = "admin"
        self.add_item(self._Member())
        self.add_item(self._Role())

    class _Member(discord.ui.UserSelect):
        def __init__(self):
            super().__init__(placeholder="Member…", max_values=1)

        async def callback(self, itx: discord.Interaction):
            self.view.target = self.values[0]
            await itx.response.defer()

    class _Role(discord.ui.Select):
        def __init__(self):
            super().__init__(placeholder="Role…",
                             options=[discord.SelectOption(label=r, value=r)
                                      for r in ("player", "admin", "superadmin")])

        async def callback(self, itx: discord.Interaction):
            self.view.role = self.values[0]
            await itx.response.defer()

    async def _need(self, itx) -> bool:
        if not await is_superadmin(itx.user):
            await reply(itx, "Superadmin only.")
            return False
        if not self.target:
            await reply(itx, "Pick a member first.")
            return False
        return True

    @discord.ui.button(label="Grant", style=discord.ButtonStyle.success)
    async def grant(self, itx: discord.Interaction, _b: discord.ui.Button):
        if not await self._need(itx):
            return
        async with SessionLocal() as s:
            if not await s.get(MemberRole, (itx.guild_id, self.target.id, self.role)):
                s.add(MemberRole(guild_id=itx.guild_id, user_id=self.target.id, role=self.role))
                await s.commit()
        await audit.log(itx.guild_id, itx.user.id, "grant", str(self.target.id), role=self.role)
        await reply(itx, f"Granted **{self.role}** to {self.target.mention}.")

    @discord.ui.button(label="Revoke", style=discord.ButtonStyle.danger)
    async def revoke(self, itx: discord.Interaction, _b: discord.ui.Button):
        if not await self._need(itx):
            return
        async with SessionLocal() as s:
            mr = await s.get(MemberRole, (itx.guild_id, self.target.id, self.role))
            if mr:
                await s.delete(mr)
                await s.commit()
        await audit.log(itx.guild_id, itx.user.id, "revoke", str(self.target.id), role=self.role)
        await reply(itx, f"Revoked **{self.role}** from {self.target.mention}.")


# ========================================================= sub-panel: bans ====
class BansView(AutoDismissView):
    def __init__(self):
        super().__init__()
        self.member: discord.Member | None = None
        self.add_item(self._Member())

    class _Member(discord.ui.UserSelect):
        def __init__(self):
            super().__init__(placeholder="Player…", max_values=1)

        async def callback(self, itx: discord.Interaction):
            self.view.member = self.values[0]
            await itx.response.defer()

    @discord.ui.button(label="Ban", style=discord.ButtonStyle.danger, emoji="🔨")
    async def ban(self, itx: discord.Interaction, _b: discord.ui.Button):
        if not self.member:
            return await reply(itx, "Pick a player first.")
        await itx.response.send_modal(BanReasonModal(self.member))

    @discord.ui.button(label="Unban", style=discord.ButtonStyle.success, emoji="♻️")
    async def unban(self, itx: discord.Interaction, _b: discord.ui.Button):
        if not self.member:
            return await reply(itx, "Pick a player first.")
        removed = await bans_svc.unban(itx.guild_id, self.member.id)
        await audit.log(itx.guild_id, itx.user.id, "unban", str(self.member.id))
        await reply(itx, f"{'Unbanned' if removed else 'Was not banned'} {self.member.mention}.")

    @discord.ui.button(label="List bans", style=discord.ButtonStyle.secondary, emoji="📋")
    async def listing(self, itx: discord.Interaction, _b: discord.ui.Button):
        rows = await bans_svc.list_bans(itx.guild_id)
        if not rows:
            return await reply(itx, "No banned players.")
        await reply(itx, "\n".join(f"• <@{b.user_id}>" + (f" — {b.reason}" if b.reason else "")
                                   for b in rows))


# ================================================== sub-panel: audit log =====
async def _show_audit(itx: discord.Interaction) -> None:
    async with SessionLocal() as s:
        rows = await s.execute(
            select(AuditLog).where(AuditLog.guild_id == itx.guild_id)
            .order_by(AuditLog.id.desc()).limit(10)
        )
        entries = [r[0] for r in rows.all()]
    if not entries:
        return await reply(itx, "No audit entries.")
    lines = [f"`{e.ts:%m-%d %H:%M}` <@{e.actor_id}> **{e.action}** {e.target or ''}"
             for e in entries]
    await reply(itx, "\n".join(lines))


# ============================================================== menus ========
class _LevelMenu(AutoDismissView):
    """Ephemeral menu gated on a level. The message is already private to the
    opener, but every click re-checks in case the role was revoked meanwhile."""

    LEVEL = PLAYER

    async def interaction_check(self, itx: discord.Interaction) -> bool:
        return await _guard(itx, self.LEVEL)


class PlayerMenu(_LevelMenu):
    """Pure customs view — what every member gets."""

    LEVEL = PLAYER

    @discord.ui.button(label="Profile", style=discord.ButtonStyle.primary, emoji="👤")
    async def profile(self, itx: discord.Interaction, _b: discord.ui.Button):
        await itx.response.send_modal(ProfileModal())

    @discord.ui.button(label="Join / leave a custom", style=discord.ButtonStyle.success,
                       emoji="📋")
    async def customs(self, itx: discord.Interaction, _b: discord.ui.Button):
        customs = await _active_customs(itx.guild_id)
        if not customs:
            return await reply(itx, "No active customs right now.")
        await spawn(itx, CustomActionView(customs), content="Register / leave a custom:")

    @discord.ui.button(label="My stats", style=discord.ButtonStyle.secondary, emoji="📊")
    async def stats(self, itx: discord.Interaction, _b: discord.ui.Button):
        async with SessionLocal() as s:
            ps = await s.get(PlayerStats, (itx.guild_id, 0, itx.user.id))
        if not ps:
            return await reply(itx, "No stats yet.")
        e = discord.Embed(title="Your stats", color=VAL_RED)
        e.add_field(name="Played", value=ps.played)
        e.add_field(name="W/L", value=f"{ps.wins}/{ps.losses}")
        e.add_field(name="MVPs", value=ps.mvps)
        await reply(itx, embed=e)


class AdminMenu(_LevelMenu):
    """Running customs: create, maps, manage, match tools, bans, audit."""

    LEVEL = ADMIN

    @discord.ui.button(label="Create custom", style=discord.ButtonStyle.success,
                       emoji="➕", row=0)
    async def create_custom(self, itx: discord.Interaction, _b: discord.ui.Button):
        maps = await _enabled_maps(itx.guild_id)
        if not maps:
            return await reply(itx, "No enabled maps yet — use **Maps → Seed defaults** first.")
        v = CreateCustomView(maps, await maps_svc.competitive_names(itx.guild_id))
        await spawn(itx, v, content=v.summary())

    @discord.ui.button(label="Maps", style=discord.ButtonStyle.secondary, emoji="🗺", row=0)
    async def maps(self, itx: discord.Interaction, _b: discord.ui.Button):
        maps = await _all_maps(itx.guild_id)
        await spawn(itx, MapsAdminView(itx.guild_id, maps),
                    content=MapsAdminView.status_text(maps))

    @discord.ui.button(label="Manage customs", style=discord.ButtonStyle.secondary,
                       emoji="🔧", row=0)
    async def my_customs(self, itx: discord.Interaction, _b: discord.ui.Button):
        is_super = await role_level(itx.user) >= SUPER
        owner = None if is_super else itx.user.id
        customs = await _active_customs(itx.guild_id, owned_by=owner)
        if not customs:
            return await reply(itx, "No customs to manage.")
        await spawn(itx, MyCustomsView(customs, is_super),
                    content="Pick a custom to start / force start / end / transfer / delete:")

    @discord.ui.button(label="Bans", style=discord.ButtonStyle.danger, emoji="🔨", row=1)
    async def bans(self, itx: discord.Interaction, _b: discord.ui.Button):
        await spawn(itx, BansView(), content="Ban / unban players:")

    @discord.ui.button(label="Audit", style=discord.ButtonStyle.secondary, emoji="📜", row=1)
    async def auditlog(self, itx: discord.Interaction, _b: discord.ui.Button):
        await _show_audit(itx)


class SuperMenu(_LevelMenu):
    """Server-wide controls: bot roles, mass prune, audit."""

    LEVEL = SUPER

    @discord.ui.button(label="Roles", style=discord.ButtonStyle.primary, emoji="🛡")
    async def roles(self, itx: discord.Interaction, _b: discord.ui.Button):
        await spawn(itx, RolesView(), content="Grant / revoke bot roles:")

    @discord.ui.button(label="Prune all customs", style=discord.ButtonStyle.danger, emoji="🧹")
    async def prune(self, itx: discord.Interaction, _b: discord.ui.Button):
        cv = ConfirmView(allow_force=True)
        await itx.response.send_message(
            "⚠️ Delete **all** customs in this server?", view=cv, ephemeral=True
        )
        await cv.wait()
        if cv.result in ("yes", "force"):
            deleted, skipped = await custom_svc.prune(itx.guild, force=(cv.result == "force"))
            msg = f"Pruned {deleted} custom(s)."
            if skipped:
                msg += f" Skipped (in progress): {', '.join(map(str, skipped))}."
            await audit.log(itx.guild_id, itx.user.id, "custom_prune", meta=str(deleted))
            await reply(itx, msg)

    @discord.ui.button(label="Audit", style=discord.ButtonStyle.secondary, emoji="📜")
    async def auditlog(self, itx: discord.Interaction, _b: discord.ui.Button):
        await _show_audit(itx)


# =========================================================== main board ======
class ControlPanel(discord.ui.View):
    """Persistent public control board. One message, lives across restarts.

    Three entry buttons instead of every action at once — each opens the
    matching menu in a NEW ephemeral message (via spawn), so the board itself
    is never replaced or dismissed and one board serves everyone. The admin
    buttons are shown to all but check the caller's level on click."""

    def __init__(self):
        super().__init__(timeout=None)  # persistent

    @discord.ui.button(label="Customs", style=discord.ButtonStyle.success, emoji="🎮",
                       row=0, custom_id="panel:menu:player")
    async def player_view(self, itx: discord.Interaction, _b: discord.ui.Button):
        await spawn(itx, PlayerMenu(), content="🎮 **Customs** — your profile, games and stats:")

    @discord.ui.button(label="Admin panel", style=discord.ButtonStyle.primary, emoji="🛡",
                       row=0, custom_id="panel:menu:admin")
    async def admin_view(self, itx: discord.Interaction, _b: discord.ui.Button):
        if not await _guard(itx, ADMIN):
            return
        await spawn(itx, AdminMenu(), content="🛡 **Admin panel** — run the customs:")

    @discord.ui.button(label="Super Admin", style=discord.ButtonStyle.danger, emoji="👑",
                       row=0, custom_id="panel:menu:super")
    async def super_view(self, itx: discord.Interaction, _b: discord.ui.Button):
        if not await _guard(itx, SUPER):
            return
        await spawn(itx, SuperMenu(), content="👑 **Super Admin** — server-wide controls:")


class PanelCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(description="Post the persistent control board in this channel.")
    @app_commands.guild_only()
    async def panel(self, itx: discord.Interaction):
        await itx.response.send_message(
            content=(
                "🎛 **Control Board**\n"
                "Pick your view — it opens in a private message just for you. "
                "This board stays put.\n"
                "🎮 **Customs** — everyone · 🛡 **Admin panel** — admins · "
                "👑 **Super Admin** — superadmins"
            ),
            view=ControlPanel(),
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(PanelCog(bot))
