"""A tiny screen stack for private, in-place panels.

A `Screen` is one page: an embed that shows the current state plus the controls
that make sense *for that state*. Navigating doesn't send a new message — the
same ephemeral message is edited, so the panel morphs under the user instead of
burying them in a stack of menus.

Two rules make this work:

* Screens hold **ids, not ORM rows.** Every render re-reads the database, so a
  screen you came *back* to is never stale.
* Screens build their items in `build()`, not with `@discord.ui.button`
  decorators — `compose()` clears and rebuilds the item list on every render,
  which is what lets a button appear or disappear as the state changes.
"""
from __future__ import annotations

import discord

from bot.core.ui import AutoDismissView, spawn
from bot.i18n import t

NAV_TIMEOUT = 180  # private panels are for reading as well as clicking


class Screen(AutoDismissView):
    """One page of a private panel."""

    def __init__(self, parent: "Screen | None" = None, *, timeout: float = NAV_TIMEOUT):
        super().__init__(timeout=timeout)
        self.parent = parent

    # ----------------------------------------------------------- to override --
    async def embed(self) -> discord.Embed:
        """The page itself. Re-read your data here — this runs on every render."""
        raise NotImplementedError

    async def build(self) -> None:
        """Add this page's items. Back/Reload are added for you, on row 4."""

    # ---------------------------------------------------------------- render --
    async def compose(self) -> discord.Embed:
        self.clear_items()
        e = await self.embed()
        await self.build()
        if self.parent is not None:
            self.add_item(_Back())
        self.add_item(_Reload())
        return e

    async def open(self, itx: discord.Interaction) -> None:
        """First render — a NEW ephemeral message, leaving the board untouched."""
        embed = await self.compose()
        await spawn(itx, self, embed=embed)

    async def show(self, itx: discord.Interaction) -> None:
        """Render in place, replacing whatever the message currently holds."""
        embed = await self.compose()
        if not itx.response.is_done():
            await itx.response.edit_message(embed=embed, view=self)
            if self.message is None:
                self.message = await itx.original_response()
        elif self.message is not None:
            try:
                await self.message.edit(embed=embed, view=self)
            except discord.HTTPException:
                pass

    async def goto(self, itx: discord.Interaction, screen: "Screen") -> None:
        """Hand this message over to another screen."""
        screen.message = self.message
        self.message = None  # the new screen owns the cleanup now
        self.stop()
        await screen.show(itx)

    async def reload(self, itx: discord.Interaction) -> None:
        """Redraw this screen after an action changed the data behind it."""
        await self.show(itx)

    async def repaint(self) -> None:
        """Redraw without an interaction.

        A modal submit is its own interaction — spending it on the panel message
        would leave the modal unanswered, so the panel is edited directly and the
        modal answers for itself."""
        if self.message is None:
            return
        embed = await self.compose()
        try:
            await self.message.edit(embed=embed, view=self)
        except discord.HTTPException:
            pass


class _Back(discord.ui.Button):
    def __init__(self):
        super().__init__(label=t("btn.back"), style=discord.ButtonStyle.secondary, row=4)

    async def callback(self, itx: discord.Interaction):
        view: Screen = self.view
        await view.goto(itx, view.parent)


class _Reload(discord.ui.Button):
    def __init__(self):
        super().__init__(label=t("btn.refresh"), style=discord.ButtonStyle.secondary, row=4)

    async def callback(self, itx: discord.Interaction):
        await self.view.reload(itx)
