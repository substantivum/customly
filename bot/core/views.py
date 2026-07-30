"""Discord UI views (buttons / selects). Kept thin; logic lives in services."""
from __future__ import annotations

import asyncio

import discord
from sqlalchemy import select

from bot.config import settings
from bot.core.embeds import custom_registration_embed
from bot.core.errors import BotError
from bot.services import custom as custom_svc


async def _refresh_registration(itx: discord.Interaction, custom_id: int) -> None:
    from bot.db import SessionLocal
    from bot.db.models import Custom, Queue

    async with SessionLocal() as s:
        c = await s.get(Custom, custom_id)
        q = (await s.execute(
            select(Queue).where(Queue.custom_id == custom_id)
        )).scalar_one_or_none()
    if not c:
        return
    size = q.size if q else c.team_size * 2
    regs = await custom_svc.registrants(custom_id)
    await itx.message.edit(embed=custom_registration_embed(c, regs, size))


class RegisterButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"reg:register:(?P<cid>\d+)",
):
    """Persistent Register button; the custom id is encoded in the custom_id."""

    def __init__(self, custom_id: int):
        self.cid = custom_id
        super().__init__(
            discord.ui.Button(
                label="Register", style=discord.ButtonStyle.success, emoji="✅",
                custom_id=f"reg:register:{custom_id}",
            )
        )

    @classmethod
    async def from_custom_id(cls, itx, item, match):  # noqa: ANN001
        return cls(int(match["cid"]))

    async def callback(self, itx: discord.Interaction):
        try:
            await custom_svc.register(self.cid, itx.user.id, itx.guild_id)
        except BotError as e:
            return await itx.response.send_message(str(e), ephemeral=True)
        await itx.response.send_message(
            "Registered ✅ — be in voice before the ready check.", ephemeral=True
        )
        await _refresh_registration(itx, self.cid)


class LeaveButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"reg:leave:(?P<cid>\d+)",
):
    def __init__(self, custom_id: int):
        self.cid = custom_id
        super().__init__(
            discord.ui.Button(
                label="Leave", style=discord.ButtonStyle.secondary, emoji="🚪",
                custom_id=f"reg:leave:{custom_id}",
            )
        )

    @classmethod
    async def from_custom_id(cls, itx, item, match):  # noqa: ANN001
        return cls(int(match["cid"]))

    async def callback(self, itx: discord.Interaction):
        try:
            await custom_svc.leave(self.cid, itx.user.id, itx.guild_id)
        except BotError as e:
            return await itx.response.send_message(str(e), ephemeral=True)
        await itx.response.send_message("You left the custom.", ephemeral=True)
        await _refresh_registration(itx, self.cid)


def registration_view(custom_id: int) -> discord.ui.View:
    """Build the registration view for a custom. Buttons are persistent, so they
    keep working after a bot restart once add_dynamic_items() is called on boot."""
    v = discord.ui.View(timeout=None)
    v.add_item(RegisterButton(custom_id))
    v.add_item(LeaveButton(custom_id))
    return v


# ------------------------------------------------------------ match lobby ---
class PartyCodeModal(discord.ui.Modal, title="Party code"):
    """Set the code, then redraw the lobby message the button lives on."""

    code = discord.ui.TextInput(label="Party / group code", placeholder="7F3K2", max_length=16)

    def __init__(self, custom_id: int, message: discord.Message | None = None):
        super().__init__()
        self.cid = custom_id
        self.message = message

    async def on_submit(self, itx: discord.Interaction):
        from bot.core import actions

        await itx.response.defer(ephemeral=True)
        try:
            # announce=False: the lobby embed below is the announcement
            await actions.set_party_code(itx, self.cid, self.code.value, announce=False)
        except BotError as e:
            return await itx.followup.send(str(e), ephemeral=True)
        if self.message:
            embed = await actions.build_lobby_embed(itx.guild, self.cid)
            if embed:
                try:
                    await self.message.edit(embed=embed)
                except discord.HTTPException:
                    pass
        await itx.followup.send("Party code updated ✅", ephemeral=True)


class PartyCodeButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"lobby:code:(?P<cid>\d+)",
):
    """On the lobby message in the custom's own channel. Visible to everyone —
    Discord can't hide a button per-viewer — but only players registered for
    this custom (or an admin) can actually use it."""

    def __init__(self, custom_id: int):
        self.cid = custom_id
        super().__init__(
            discord.ui.Button(
                label="Set party code", style=discord.ButtonStyle.success, emoji="🔑",
                custom_id=f"lobby:code:{custom_id}",
            )
        )

    @classmethod
    async def from_custom_id(cls, itx, item, match):  # noqa: ANN001
        return cls(int(match["cid"]))

    async def callback(self, itx: discord.Interaction):
        from bot.core import actions

        if not await actions.can_play_custom(self.cid, itx.user):
            return await itx.response.send_message(
                "Only players registered for this custom (or an admin) can set the code.",
                ephemeral=True,
            )
        await itx.response.send_modal(PartyCodeModal(self.cid, itx.message))


class EndCustomButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"lobby:end:(?P<cid>\d+)",
):
    """Ends the match and tears down this custom's channels. Any registered
    player can call it — they're the ones who know the game is over."""

    def __init__(self, custom_id: int):
        self.cid = custom_id
        super().__init__(
            discord.ui.Button(
                label="End custom", style=discord.ButtonStyle.danger, emoji="🏁",
                custom_id=f"lobby:end:{custom_id}",
            )
        )

    @classmethod
    async def from_custom_id(cls, itx, item, match):  # noqa: ANN001
        return cls(int(match["cid"]))

    async def callback(self, itx: discord.Interaction):
        from bot.core import actions

        if not await actions.can_play_custom(self.cid, itx.user):
            return await itx.response.send_message(
                "Only players registered for this custom (or an admin) can end it.",
                ephemeral=True,
            )
        # Answer before ending — end_custom deletes the channel we're sitting in.
        await itx.response.send_message(
            "Ending the custom — voice and this channel will be removed.", ephemeral=True
        )
        try:
            await actions.end_custom(itx, self.cid)
        except BotError as e:
            await itx.followup.send(str(e), ephemeral=True)


def lobby_view(custom_id: int) -> discord.ui.View:
    """Persistent controls on the match lobby message."""
    v = discord.ui.View(timeout=None)
    v.add_item(PartyCodeButton(custom_id))
    v.add_item(EndCustomButton(custom_id))
    return v


class VetoView(discord.ui.View):
    """One button per remaining map; the active side bans/picks on their turn.
    A per-turn timer auto-picks a random remaining map if the captain stalls."""

    def __init__(self, controller: "VetoController"):
        super().__init__(timeout=None)  # we run our own per-turn timer
        self.c = controller
        self.message = None
        self.channel = None
        self.on_done = None  # async callback fired once veto completes
        self._timer = None
        self._render()

    def _render(self):
        self.clear_items()
        for m in self.c.remaining:
            self.add_item(self._MapButton(m))

    def arm(self):
        self._cancel()
        if not self.c.done:
            self._timer = asyncio.create_task(self._countdown())

    def _cancel(self):
        if self._timer and not self._timer.done():
            self._timer.cancel()

    async def _countdown(self):
        try:
            await asyncio.sleep(settings.veto_pick_seconds)
        except asyncio.CancelledError:
            return
        if self.c.done:
            return
        done = self.c.auto_pick_map()
        self._render()
        await self._update(done, itx=None, auto=True)

    async def _update(self, done: bool, *, itx, auto: bool):
        new_view = None if done else self
        if itx is not None and not itx.response.is_done():
            await itx.response.edit_message(embed=self.c.embed(), view=new_view)
        elif self.message:
            try:
                await self.message.edit(embed=self.c.embed(), view=new_view)
            except discord.HTTPException:
                pass
        if done:
            self._cancel()
            await self.c.persist()
            text = self.c.result_text(auto=auto)
            if self.channel:
                await self.channel.send(text)
            elif itx is not None:
                await itx.followup.send(text)
            self.stop()
            if self.on_done:
                await self.on_done()
        else:
            self.arm()

    class _MapButton(discord.ui.Button):
        def __init__(self, map_name: str):
            super().__init__(label=map_name, style=discord.ButtonStyle.primary)
            self.map_name = map_name

        async def callback(self, itx: discord.Interaction):
            view: "VetoView" = self.view  # capture BEFORE _render detaches this button
            if itx.user.id != view.c.captain_for_turn():
                return await itx.response.send_message(
                    "Not your turn to ban/pick.", ephemeral=True
                )
            done = view.c.apply(self.map_name)
            view._render()
            await view._update(done, itx=itx, auto=False)


class DraftView(discord.ui.View):
    """Captain on the clock picks from a Select of remaining players.
    A per-turn timer auto-picks a random player if the captain stalls."""

    def __init__(self, controller, on_done, guild: discord.Guild | None = None):
        super().__init__(timeout=None)
        self.c = controller
        self.on_done = on_done
        self.guild = guild
        self.message = None
        self.channel = None
        self._timer = None
        self._render()

    def _label(self, uid: int) -> str:
        m = self.guild.get_member(uid) if self.guild else None
        return (m.display_name if m else str(uid))[:100]

    def _render(self):
        self.clear_items()
        if self.c.done:
            return
        opts = [
            discord.SelectOption(label=self._label(uid), value=str(uid))
            for uid in self.c.pool[:25]
        ]
        self.add_item(self._PlayerSelect(opts))

    def arm(self):
        self._cancel()
        if not self.c.done:
            self._timer = asyncio.create_task(self._countdown())

    def _cancel(self):
        if self._timer and not self._timer.done():
            self._timer.cancel()

    async def _countdown(self):
        try:
            await asyncio.sleep(settings.draft_pick_seconds)
        except asyncio.CancelledError:
            return
        if self.c.done:
            return
        done = await self.c.pick(self.c.autopick(), auto=True)
        self._render()
        await self._advance(done, itx=None)

    async def _advance(self, done: bool, *, itx):
        new_view = None if done else self
        if itx is not None and not itx.response.is_done():
            await itx.response.edit_message(embed=self.c.embed(), view=new_view)
        elif self.message:
            try:
                await self.message.edit(embed=self.c.embed(), view=new_view)
            except discord.HTTPException:
                pass
        if done:
            self._cancel()
            await self.c.persist_teams()
            self.stop()
            await self.on_done()
        else:
            self.arm()

    class _PlayerSelect(discord.ui.Select):
        def __init__(self, options):
            super().__init__(placeholder="Pick a player…", options=options)

        async def callback(self, itx: discord.Interaction):
            view: "DraftView" = self.view  # capture before _render
            if itx.user.id != view.c.captain_for_turn():
                return await itx.response.send_message("Not your pick.", ephemeral=True)
            done = await view.c.pick(int(self.values[0]))
            view._render()
            await view._advance(done, itx=itx)
