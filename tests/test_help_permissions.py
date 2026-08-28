"""Guards bot.cogs.help._SECTIONS against drifting from each command's real
`@require(...)` gate.

Only commands gated via `bot.core.permissions.require()` are checked here —
a handful of commands (e.g. `/panel`, `/language`, and the ownership-checked
`/custom transfer`/`/custom delete`) enforce their level with a manual runtime
guard instead of the `require()` decorator, which isn't visible to
app_commands' check introspection. Those are outside what this test can
verify and are simply skipped.
"""
from __future__ import annotations

import asyncio

import discord
from discord import app_commands
from discord.ext import commands

from bot.cogs.admin import AdminCog
from bot.cogs.custom import CustomCog
from bot.cogs.help import _SECTIONS
from bot.cogs.maps import MapsCog
from bot.cogs.match import MatchCog
from bot.cogs.panel import PanelCog
from bot.cogs.profile import ProfileCog
from bot.cogs.queue import QueueCog
from bot.cogs.stats import StatsCog

COGS = [AdminCog, CustomCog, MapsCog, MatchCog, PanelCog, ProfileCog, QueueCog, StatsCog]


def _declared_levels() -> dict[str, int]:
    """{"group sub": level} from the help table, leading "/" stripped."""
    return {
        name.lstrip("/"): level
        for _, entries in _SECTIONS
        for name, _, level in entries
    }


def _real_min_level(cmd: app_commands.Command) -> int | None:
    """The level enforced by a `require(...)` check on `cmd`, or None if it
    isn't gated that way (a manual in-body guard, or open to any player)."""
    for check in cmd.checks:
        level = getattr(check, "min_level", None)
        if level is not None:
            return level
    return None


def _real_levels() -> dict[str, int | None]:
    async def build() -> commands.Bot:
        bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
        for cls in COGS:
            await bot.add_cog(cls(bot))
        return bot

    bot = asyncio.run(build())
    return {
        cmd.qualified_name: _real_min_level(cmd)
        for cmd in bot.tree.walk_commands()
        if isinstance(cmd, app_commands.Command)
    }


def test_help_levels_match_require_gates():
    real = _real_levels()
    declared = _declared_levels()

    mismatches = {
        name: {"help.py says": level, "actual @require gate": real[name]}
        for name, level in declared.items()
        if real.get(name) is not None and real[name] != level
    }
    assert not mismatches, f"help.py permission level drifted from the real gate: {mismatches}"


def test_every_declared_command_actually_exists():
    """Catches a help.py entry for a command that got renamed or removed."""
    missing = set(_declared_levels()) - set(_real_levels())
    assert not missing, f"help.py lists commands that don't exist: {missing}"
