"""/maps management."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.permissions import require
from bot.core.ui import reply
from bot.i18n import t
from bot.i18n.translator import L
from bot.services import maps as maps_svc

# Same on/off indicators the panel's map screen uses.
MAP_ON, MAP_OFF = "\U0001f7e2", "\U0001f534"

# Dota 2 has no map pool, so it isn't offered here.
GAME_CHOICES = [
    app_commands.Choice(name="Valorant", value="valorant"),
    app_commands.Choice(name="CS2", value="cs2"),
]


class MapsCog(commands.GroupCog, name="maps"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(description=L("cmd.maps.list.desc"))
    @app_commands.describe(game=L("cmd.maps.game"))
    @app_commands.choices(game=GAME_CHOICES)
    async def list(self, itx: discord.Interaction, game: app_commands.Choice[str] | None = None):
        maps = await maps_svc.all_maps(itx.guild_id, game.value if game else "valorant")
        if not maps:
            return await reply(itx, t("maps.none_configured"))
        lines = [
            t("maps.list_line_comp" if m.competitive else "maps.list_line",
              dot=MAP_ON if m.enabled else MAP_OFF, name=m.name)
            for m in maps
        ]
        await reply(itx, "\n".join(lines))

    @app_commands.command(description=L("cmd.maps.seed.desc"))
    @require("admin")
    @app_commands.describe(game=L("cmd.maps.game"))
    @app_commands.choices(game=GAME_CHOICES)
    async def seed(self, itx: discord.Interaction, game: app_commands.Choice[str] | None = None):
        await maps_svc.seed(itx.guild_id, game.value if game else "valorant")
        await reply(itx, t("maps.seeded_ok"))

    @app_commands.command(description=L("cmd.maps.competitive.desc"))
    @require("admin")
    @app_commands.describe(maps=L("cmd.maps.competitive.maps"), game=L("cmd.maps.game"))
    @app_commands.choices(game=GAME_CHOICES)
    async def competitive(
        self, itx: discord.Interaction, maps: str = "",
        game: app_commands.Choice[str] | None = None,
    ):
        in_pool, unknown = await maps_svc.set_competitive(
            itx.guild_id, maps.split(","), itx.user.id,
            game=game.value if game else "valorant",
        )
        msg = (t("maps.comp_set", maps=", ".join(in_pool)) if in_pool
               else t("maps.comp_cleared"))
        if unknown:
            msg += t("maps.comp_unknown", maps=", ".join(unknown))
        await reply(itx, msg)

    @app_commands.command(description=L("cmd.maps.add.desc"))
    @require("admin")
    @app_commands.describe(game=L("cmd.maps.game"))
    @app_commands.choices(game=GAME_CHOICES)
    async def add(self, itx: discord.Interaction, name: str, game: app_commands.Choice[str] | None = None):
        added = await maps_svc.add_map(
            itx.guild_id, name, itx.user.id, game=game.value if game else "valorant"
        )
        await reply(itx, t("maps.added_cmd" if added else "maps.err.exists", name=name))

    @app_commands.command(description=L("cmd.maps.remove.desc"))
    @require("admin")
    async def remove(self, itx: discord.Interaction, name: str):
        removed = await maps_svc.remove_map(itx.guild_id, name, itx.user.id)
        await reply(itx, t("maps.removed" if removed else "maps.no_such", name=name))

    @app_commands.command(description=L("cmd.maps.toggle.desc"))
    @require("admin")
    async def toggle(self, itx: discord.Interaction, name: str):
        state = await maps_svc.toggle_map(itx.guild_id, name, itx.user.id)
        if state is None:
            return await reply(itx, t("maps.no_such"))
        await reply(itx, t("maps.toggled", name=name,
                           state=t("common.enabled" if state else "common.disabled")))


async def setup(bot: commands.Bot):
    await bot.add_cog(MapsCog(bot))
