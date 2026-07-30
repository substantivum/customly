"""Ephemeral reply helpers with 30s auto-dismiss.

`reply()` is for one-shot command/return messages.
`AutoDismissView` is for interactive panels: its 30s timeout resets on each
button click (discord.py refreshes the timeout per interaction) and deletes the
message once the user stops interacting.
"""
from __future__ import annotations

import asyncio

import discord

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


class AutoDismissView(discord.ui.View):
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


class ConfirmView(discord.ui.View):
    """Confirm / (optional) Force / Cancel. `result` is set on click."""

    def __init__(self, *, allow_force: bool = False, timeout: int = 30):
        super().__init__(timeout=timeout)
        self.result: str | None = None  # "yes" | "force" | "no" | None(timeout)
        if not allow_force:
            self.remove_item(self.force)

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def yes(self, itx: discord.Interaction, _b: discord.ui.Button):
        self.result = "yes"
        self.stop()
        await itx.response.defer()

    @discord.ui.button(label="Force", style=discord.ButtonStyle.danger)
    async def force(self, itx: discord.Interaction, _b: discord.ui.Button):
        self.result = "force"
        self.stop()
        await itx.response.defer()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def no(self, itx: discord.Interaction, _b: discord.ui.Button):
        self.result = "no"
        self.stop()
        await itx.response.defer()
