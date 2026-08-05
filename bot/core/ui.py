"""Ephemeral reply helpers with 30s auto-dismiss.

`reply()` is for one-shot command/return messages.
`AutoDismissView` is for interactive panels: its 30s timeout resets on each
button click (discord.py refreshes the timeout per interaction) and deletes the
message once the user stops interacting.
"""
from __future__ import annotations

import asyncio

import discord

from bot.i18n import t
from bot.i18n.ui import LocalizedView

DISMISS_AFTER = 30  # seconds

# keep strong refs so scheduled deletions aren't garbage-collected
_pending: set[asyncio.Task] = set()


def _schedule_delete(msg: discord.Message | discord.InteractionMessage, after: int) -> None:
    async def _run():
        await asyncio.sleep(after)
        try:
            await msg.delete()
        except discord.HTTPException:
            pass

    task = asyncio.create_task(_run())
    _pending.add(task)
    task.add_done_callback(_pending.discard)


async def reply(
    itx: discord.Interaction,
    content: str | None = None,
    *,
    embed: discord.Embed | None = None,
    ephemeral: bool = True,
    dismiss_after: int | None = DISMISS_AFTER,
):
    """Send an ephemeral response/followup and auto-delete it after `dismiss_after`s."""
    if itx.response.is_done():
        msg = await itx.followup.send(content=content, embed=embed, ephemeral=ephemeral, wait=True)
    else:
        await itx.response.send_message(content=content, embed=embed, ephemeral=ephemeral)
        msg = await itx.original_response()
    if dismiss_after and msg is not None:
        _schedule_delete(msg, dismiss_after)
    return msg


class AutoDismissView(LocalizedView):
    """Ephemeral panel whose message self-deletes 30s after the last interaction."""

    def __init__(self, *, timeout: float | None = DISMISS_AFTER):
        super().__init__(timeout=timeout)
        self.message: discord.Message | discord.InteractionMessage | None = None

    async def send(self, itx: discord.Interaction, *, content=None, embed=None):
        if itx.response.is_done():
            self.message = await itx.followup.send(
                content=content, embed=embed, view=self, ephemeral=True, wait=True
            )
        else:
            await itx.response.send_message(content=content, embed=embed, view=self, ephemeral=True)
            self.message = await itx.original_response()
        return self.message

    async def on_timeout(self) -> None:
        if self.message:
            try:
                await self.message.delete()
            except discord.HTTPException:
                pass


async def spawn(itx: discord.Interaction, view: discord.ui.View, *, content=None, embed=None):
    """Open a sub-panel as a NEW ephemeral message, leaving the caller's message
    (e.g. the persistent control board) untouched."""
    if itx.response.is_done():
        msg = await itx.followup.send(content=content, embed=embed, view=view,
                                      ephemeral=True, wait=True)
    else:
        await itx.response.send_message(content=content, embed=embed, view=view, ephemeral=True)
        msg = await itx.original_response()
    if hasattr(view, "message"):
        view.message = msg  # lets AutoDismissView clean itself up
    return msg


class ConfirmView(LocalizedView):
    """Confirm / (optional) Force / Cancel. `result` is set on click.

    The buttons are built here rather than declared with `@discord.ui.button`:
    a decorator's label is fixed at import time, before any language is known.
    """

    def __init__(self, *, allow_force: bool = False, timeout: int = 30):
        super().__init__(timeout=timeout)
        self.result: str | None = None  # "yes" | "force" | "no" | None(timeout)
        self.add_item(self._Choice("btn.confirm", "yes", discord.ButtonStyle.danger))
        if allow_force:
            self.add_item(self._Choice("btn.force", "force", discord.ButtonStyle.danger))
        self.add_item(self._Choice("btn.cancel", "no", discord.ButtonStyle.secondary))

    class _Choice(discord.ui.Button):
        def __init__(self, label_key: str, result: str, style):
            super().__init__(label=t(label_key), style=style)
            self.result = result

        async def callback(self, itx: discord.Interaction):
            self.view.result = self.result
            self.view.stop()
            await itx.response.defer()
