"""Discord UI views (buttons / selects). Kept thin; logic lives in services.

Everything user-visible here goes through `t()`, which reads the language from a
ContextVar. Two places have to put it there by hand:

* `DynamicItem` callbacks. Discord.py rebuilds a bare `discord.ui.View` from the
  message to dispatch these, so no `interaction_check` of ours ever runs — each
  callback calls `bind()` itself.
* The per-turn timers. `asyncio.create_task` copies the current context, so an
  armed timer *usually* inherits the right language, but a view can also be
  cancelled from outside any interaction — so the language is captured once at
  construction and re-entered whenever the view redraws on its own.
"""
from __future__ import annotations

import asyncio

import discord

from bot.config import settings
from bot.core.controllers import (
    CoinflipController,
    DraftController,
    ReadyCheckController,
    VetoController,
)
from bot.core.errors import BotError
from bot.i18n import current_lang, lang_context, t
from bot.i18n.ui import LocalizedModal, LocalizedView, bind


class RegisterButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"reg:register:(?P<cid>\d+)",
):
    """Persistent Register button; the custom id is encoded in the custom_id."""

    def __init__(self, custom_id: int):
        self.cid = custom_id
        super().__init__(
            discord.ui.Button(
                label=t("btn.register"), style=discord.ButtonStyle.success,
                custom_id=f"reg:register:{custom_id}",
            )
        )

    @classmethod
    async def from_custom_id(cls, itx, item, match):  # noqa: ANN001
        await bind(itx)
        return cls(int(match["cid"]))

    async def callback(self, itx: discord.Interaction):
        from bot.core import actions

        await bind(itx)
        await itx.response.defer(ephemeral=True)
        try:
            msg = await actions.join_custom(
                itx.guild, self.cid, itx.user.id, itx.message
            )
        except BotError as e:
            return await itx.followup.send(str(e), ephemeral=True)
        await itx.followup.send(msg, ephemeral=True)


class LeaveButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"reg:leave:(?P<cid>\d+)",
):
    def __init__(self, custom_id: int):
        self.cid = custom_id
        super().__init__(
            discord.ui.Button(
                label=t("btn.leave"), style=discord.ButtonStyle.secondary,
                custom_id=f"reg:leave:{custom_id}",
            )
        )

    @classmethod
    async def from_custom_id(cls, itx, item, match):  # noqa: ANN001
        await bind(itx)
        return cls(int(match["cid"]))

    async def callback(self, itx: discord.Interaction):
        from bot.core import actions

        await bind(itx)
        await itx.response.defer(ephemeral=True)
        try:
            msg = await actions.leave_custom(
                itx.guild, self.cid, itx.user.id, itx.message
            )
        except BotError as e:
            return await itx.followup.send(str(e), ephemeral=True)
        await itx.followup.send(msg, ephemeral=True)


def registration_view(custom_id: int) -> discord.ui.View:
    """Build the registration view for a custom. Buttons are persistent, so they
    keep working after a bot restart once add_dynamic_items() is called on boot."""
    v = LocalizedView(timeout=None)
    v.add_item(RegisterButton(custom_id))
    v.add_item(LeaveButton(custom_id))
    return v


# ------------------------------------------------------------ match lobby ---
class PartyCodeModal(LocalizedModal):
    """Set the code, then redraw the lobby message the button lives on."""

    def __init__(self, custom_id: int, message: discord.Message | None = None):
        super().__init__(title=t("modal.code.title"))
        self.cid = custom_id
        self.message = message
        self.code = discord.ui.TextInput(
            label=t("modal.code.label"), placeholder=t("modal.code.ph"), max_length=16
        )
        self.add_item(self.code)

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
        await itx.followup.send(t("code.updated"), ephemeral=True)


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
                label=t("btn.set_code"), style=discord.ButtonStyle.success,
                custom_id=f"lobby:code:{custom_id}",
            )
        )

    @classmethod
    async def from_custom_id(cls, itx, item, match):  # noqa: ANN001
        await bind(itx)
        return cls(int(match["cid"]))

    async def callback(self, itx: discord.Interaction):
        from bot.core import actions

        await bind(itx)
        if not await actions.can_play_custom(self.cid, itx.user):
            return await itx.response.send_message(t("error.code_perm"), ephemeral=True)
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
                label=t("btn.end_custom"), style=discord.ButtonStyle.danger,
                custom_id=f"lobby:end:{custom_id}",
            )
        )

    @classmethod
    async def from_custom_id(cls, itx, item, match):  # noqa: ANN001
        await bind(itx)
        return cls(int(match["cid"]))

    async def callback(self, itx: discord.Interaction):
        from bot.core import actions

        await bind(itx)
        if not await actions.can_play_custom(self.cid, itx.user):
            return await itx.response.send_message(t("error.end_perm"), ephemeral=True)
        # Answer before ending — end_custom deletes the channel we're sitting in.
        await itx.response.send_message(t("custom.ending"), ephemeral=True)
        try:
            await actions.end_custom(itx, self.cid)
        except BotError as e:
            await itx.followup.send(str(e), ephemeral=True)


def lobby_view(custom_id: int) -> discord.ui.View:
    """Persistent controls on the match lobby message."""
    v = LocalizedView(timeout=None)
    v.add_item(PartyCodeButton(custom_id))
    v.add_item(EndCustomButton(custom_id))
    return v


class _TimedView(LocalizedView):
    """Base for the run-of-match views: one message, one per-turn timer.

    Discord's own view timeout can't be used — it fires once and can't be reset
    per turn — so each of these runs an asyncio timer it re-arms after every
    step, and auto-decides for whoever is stalling."""

    SECONDS = 30

    def __init__(self):
        super().__init__(timeout=None)
        self.message = None
        self.channel = None
        self._timer = None
        # The language this match is being played in. A timer firing on its own
        # has no interaction to read it from.
        self.lang = current_lang()

    async def arm(self):
        await self._cancel()
        self._timer = asyncio.create_task(self._countdown())

    async def _cancel(self):
        # A timer that fires calls this on itself (from on_timeout_step, via a
        # "done" branch in a subclass) as well as being called from a captain's
        # click (a *different* task, cancelling the still-sleeping timer).
        # Cancelling your own currently-running task doesn't raise right there —
        # it raises at the *next* await, which would silently abort whatever
        # comes after (persisting the final pick, advancing to the next match
        # stage). A task that's already unwinding to a natural return doesn't
        # need cancelling, so skip it in that one case.
        if (
            self._timer
            and not self._timer.done()
            and self._timer is not asyncio.current_task()
        ):
            self._timer.cancel()

    async def _countdown(self):
        try:
            await asyncio.sleep(self.SECONDS)
        except asyncio.CancelledError:
            return
        with lang_context(self.lang):
            await self.on_timeout_step()

    async def on_timeout_step(self):    # pragma: no cover - overridden
        raise NotImplementedError

    async def _redraw(self, embed, *, itx, view):
        if itx is not None and not itx.response.is_done():
            await itx.response.edit_message(embed=embed, view=view)
        elif self.message:
            try:
                await self.message.edit(embed=embed, view=view)
            except discord.HTTPException:
                pass


class ReadyCheckView(_TimedView):
    """Ready / Can't play for every starter, on one message in the custom's channel.

    Resolves early the moment everyone has answered — waiting out a two-minute
    clock when the answer is already known just annoys the people who did click.
    """

    def __init__(self, controller: ReadyCheckController, on_resolve):
        super().__init__()
        self.c: ReadyCheckController = controller
        # async () -> None. It takes no arguments on purpose: resolution reads
        # the roster back from the database, so how we got here — everyone
        # answered, or the clock ran out — changes nothing about what happens.
        self.on_resolve = on_resolve
        self.SECONDS = settings.ready_check_seconds
        self._resolved = False
        self.add_item(self._Answer("btn.ready", True, discord.ButtonStyle.success))
        self.add_item(self._Answer("btn.cant_play", False, discord.ButtonStyle.danger))

    async def _apply(self, user_id: int, ok: bool, *, itx):
        self.c.mark(user_id, ok)
        if self.c.all_answered:
            return await self._finish(itx=itx)
        await self._redraw(self.c.embed(), itx=itx, view=self)

    async def _finish(self, *, itx):
        if self._resolved:
            return
        self._resolved = True
        await self._cancel()
        self.stop()
        await self._redraw(self.c.embed(outcome=t("ready.resolving")), itx=itx, view=None)
        await self.on_resolve()

    async def on_timeout_step(self):
        await self._finish(itx=None)

    async def cancel(self, note: str) -> None:
        """Called off from outside — a manual start, or the custom going away."""
        if self._resolved:
            return
        self._resolved = True
        await self._cancel()
        self.stop()
        with lang_context(self.lang):
            await self._redraw(self.c.embed(outcome=note), itx=None, view=None)

    class _Answer(discord.ui.Button):
        def __init__(self, label_key: str, ok: bool, style):
            super().__init__(label=t(label_key), style=style)
            self.ok = ok

        async def callback(self, itx: discord.Interaction):
            view: "ReadyCheckView" = self.view
            if not view.c.is_starter(itx.user.id):
                return await itx.response.send_message(
                    t("error.not_starter"), ephemeral=True
                )
            await view._apply(itx.user.id, self.ok, itx=itx)


class CoinflipView(_TimedView):
    """Heads/tails, then Team A or Team B. Only the captain on the clock can
    click; the timer decides for them if they don't."""

    def __init__(self, controller: CoinflipController, on_done):
        super().__init__()
        self.c: CoinflipController = controller
        self.on_done = on_done          # async (controller) -> None
        self.SECONDS = settings.draft_pick_seconds
        self._render()

    def _render(self):
        self.clear_items()
        if self.c.stage == "call":
            self.add_item(self._Choice("coin.heads", "heads"))
            self.add_item(self._Choice("coin.tails", "tails"))
        elif self.c.stage == "letter":
            self.add_item(self._Choice("common.team_a", "A"))
            self.add_item(self._Choice("common.team_b", "B"))

    async def _apply(self, value: str, *, itx, auto: bool):
        if self.c.stage == "call":
            self.c.flip(value, auto=auto)
        elif self.c.stage == "letter":
            self.c.choose_letter(value, auto=auto)
        self._render()
        done = self.c.done
        await self._redraw(self.c.embed(), itx=itx, view=None if done else self)
        if done:
            await self._cancel()
            self.stop()
            # the captains may have swapped letters — hand the controller back
            await self.on_done(self.c)
        else:
            await self.arm()

    async def on_timeout_step(self):
        if self.c.done:
            return
        value = self.c.random_call() if self.c.stage == "call" else self.c.random_letter()
        await self._apply(value, itx=None, auto=True)

    class _Choice(discord.ui.Button):
        def __init__(self, label_key: str, value: str):
            super().__init__(label=t(label_key), style=discord.ButtonStyle.primary)
            self.value = value

        async def callback(self, itx: discord.Interaction):
            view: "CoinflipView" = self.view     # capture before _render detaches us
            if itx.user.id != view.c.actor_id():
                return await itx.response.send_message(
                    t("error.not_your_call"), ephemeral=True
                )
            await view._apply(self.value, itx=itx, auto=False)


class VetoView(_TimedView):
    """Drives the whole map selection on one message: map buttons on a ban/pick
    step, Attack/Defence on a side step. The captain on the clock is the only
    one who can click, and a per-turn timer decides at random if they stall."""

    def __init__(self, controller: VetoController):
        super().__init__()
        self.c: VetoController = controller
        self.on_done = None  # async callback fired once veto completes
        self.SECONDS = settings.veto_pick_seconds
        self._render()

    def _render(self):
        self.clear_items()
        cur = self.c.current
        if cur is not None and cur.action == "side":
            self.add_item(self._SideButton("btn.attack", "attack"))
            self.add_item(self._SideButton("btn.defence", "defence"))
            return
        for m in self.c.remaining:
            self.add_item(self._MapButton(m))

    async def on_timeout_step(self):
        if self.c.done:
            return
        done = (
            self.c.auto_pick_side() if self.c.current.action == "side"
            else self.c.auto_pick_map()
        )
        self._render()
        await self._update(done, itx=None, auto=True)

    async def _update(self, done: bool, *, itx, auto: bool):
        await self._redraw(self.c.embed(), itx=itx, view=None if done else self)
        if done:
            await self._cancel()
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
            await self.arm()

    class _MapButton(discord.ui.Button):
        def __init__(self, map_name: str):
            super().__init__(label=map_name, style=discord.ButtonStyle.primary)
            self.map_name = map_name

        async def callback(self, itx: discord.Interaction):
            view: "VetoView" = self.view  # capture BEFORE _render detaches this button
            if itx.user.id != view.c.captain_for_turn():
                return await itx.response.send_message(
                    t("error.not_your_turn"), ephemeral=True
                )
            done = view.c.apply(self.map_name)
            view._render()
            await view._update(done, itx=itx, auto=False)

    class _SideButton(discord.ui.Button):
        def __init__(self, label_key: str, choice: str):
            super().__init__(label=t(label_key), style=discord.ButtonStyle.primary)
            self.choice = choice

        async def callback(self, itx: discord.Interaction):
            view: "VetoView" = self.view  # capture BEFORE _render detaches this button
            if itx.user.id != view.c.captain_for_turn():
                return await itx.response.send_message(
                    t("error.not_your_side"), ephemeral=True
                )
            done = view.c.apply_side(self.choice)
            view._render()
            await view._update(done, itx=itx, auto=False)


class DraftView(_TimedView):
    """Captain on the clock picks from a Select of remaining players.
    A per-turn timer auto-picks a random player if the captain stalls."""

    def __init__(self, controller: DraftController, on_done, guild: discord.Guild | None = None):
        super().__init__()
        self.c: DraftController = controller
        self.on_done = on_done
        self.guild = guild
        self.SECONDS = settings.draft_pick_seconds
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

    async def on_timeout_step(self):
        if self.c.done:
            return
        done = await self.c.pick(self.c.autopick(), auto=True)
        self._render()
        await self._advance(done, itx=None)

    async def _advance(self, done: bool, *, itx):
        await self._redraw(self.c.embed(), itx=itx, view=None if done else self)
        if done:
            await self._cancel()
            await self.c.persist_teams()
            self.stop()
            await self.on_done()
        else:
            await self.arm()

    class _PlayerSelect(discord.ui.Select):
        def __init__(self, options):
            super().__init__(placeholder=t("draft.pick_ph"), options=options)

        async def callback(self, itx: discord.Interaction):
            view: "DraftView" = self.view  # capture before _render
            if itx.user.id != view.c.captain_for_turn():
                return await itx.response.send_message(
                    t("error.not_your_pick"), ephemeral=True
                )
            done = await view.c.pick(int(self.values[0]))
            view._render()
            await view._advance(done, itx=itx)
