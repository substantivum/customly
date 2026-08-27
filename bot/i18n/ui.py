"""Binding the guild's language onto the task that handles an interaction.

discord.py dispatches the `on_interaction` *event* in a task of its own, so a
`ContextVar` set there never reaches the command or component callback. The
hooks used here — `CommandTree.interaction_check`, `View.interaction_check`,
`Modal.interaction_check` — all run in the same task that goes on to await the
callback, which is what makes the binding stick for everything downstream.

Persistent dynamic items are the one exception: discord.py dispatches them
through a plain `discord.ui.View` rebuilt from the message, so their callbacks
call `bind()` themselves.
"""
from __future__ import annotations

import discord
from discord import app_commands

from bot.i18n.core import set_current_lang


async def bind(itx: discord.Interaction) -> str:
    """Bind the interaction's guild language for the rest of this task."""
    from bot.services import guild_svc

    lang = await guild_svc.get_lang(itx.guild_id)
    set_current_lang(lang)
    return lang


class LocalizedTree(app_commands.CommandTree):
    """Command tree that binds the guild language before any command runs."""

    async def interaction_check(self, itx: discord.Interaction) -> bool:
        await bind(itx)
        return True


class LocalizedView(discord.ui.View):
    """Base for every view in the bot.

    Subclasses that need their own `interaction_check` must call
    `super().interaction_check(itx)` first, or their items lose the binding.
    """

    async def interaction_check(self, itx: discord.Interaction) -> bool:
        await bind(itx)
        return True


class LocalizedModal(discord.ui.Modal):
    async def interaction_check(self, itx: discord.Interaction) -> bool:
        await bind(itx)
        return True
