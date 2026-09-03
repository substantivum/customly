"""/match commands — thin wrappers over core.actions."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from bot.core import actions
from bot.core.errors import BotError, PermissionDenied
from bot.core.permissions import is_admin
from bot.core.ui import reply
from bot.db import SessionLocal
from bot.i18n import t
from bot.i18n.translator import L
from bot.services import draft as draft_svc
from bot.services import games as games_svc

# Overrides for `/match start`. The custom already carries a captain method
# chosen at creation; these are here for the one-off ("actually, let's have X and
# Y captain this one") that a stored setting can't express.
CAPTAIN_METHODS = [
    "random", "manual", "highest_rr", "highest_peak",
    "highest_wins_peak", "highest_wins_rr",
]

_CAPTAIN_CHOICES = [
    app_commands.Choice(name=L(draft_svc.CAPTAIN_METHOD_KEY[m]), value=m)
    for m in CAPTAIN_METHODS
]


class MatchCog(commands.GroupCog, name="match"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(description=L("cmd.match.start.desc"))
    @app_commands.describe(
        custom_id=L("cmd.match.custom_id"), captains=L("cmd.match.captains"),
        captain_a=L("cmd.match.captain_a"), captain_b=L("cmd.match.captain_b"),
    )
    @app_commands.choices(captains=_CAPTAIN_CHOICES)
    async def start(
        self, itx: discord.Interaction, custom_id: int,
        captains: app_commands.Choice[str] | None = None,
        captain_a: discord.Member | None = None,
        captain_b: discord.Member | None = None,
    ):
        await actions.start_match(itx, custom_id, captains.value if captains else None,
                                  captain_a, captain_b, allow_partial=False)

    @app_commands.command(description=L("cmd.match.forcestart.desc"))
    @app_commands.describe(
        custom_id=L("cmd.match.custom_id"), captains=L("cmd.match.captains"),
        captain_a=L("cmd.match.captain_a"), captain_b=L("cmd.match.captain_b"),
    )
    @app_commands.choices(captains=_CAPTAIN_CHOICES)
    async def forcestart(
        self, itx: discord.Interaction, custom_id: int,
        captains: app_commands.Choice[str] | None = None,
        captain_a: discord.Member | None = None,
        captain_b: discord.Member | None = None,
    ):
        await actions.start_match(itx, custom_id, captains.value if captains else None,
                                  captain_a, captain_b, allow_partial=True)

    @app_commands.command(description=L("cmd.match.readycheck.desc"))
    @app_commands.describe(custom_id=L("cmd.match.readycheck.custom_id"))
    async def readycheck(self, itx: discord.Interaction, custom_id: int):
        from bot.core.permissions import can_manage_custom
        from bot.db.models import Custom

        async with SessionLocal() as s:
            c = await s.get(Custom, custom_id)
        if not c or c.guild_id != itx.guild_id:
            raise BotError(t("error.custom_not_found"))
        if not await can_manage_custom(c, itx.user):
            raise PermissionDenied(t("error.manage_perm"))
        await itx.response.defer(ephemeral=True)
        await reply(itx, await actions.start_ready_check(
            itx.guild, custom_id, actor_id=itx.user.id
        ))

    @app_commands.command(description=L("cmd.match.result.desc"))
    async def result(
        self, itx: discord.Interaction, match_id: int, map_name: str, score_a: int, score_b: int
    ):
        from bot.db.models import Match, MatchResult

        if score_a == score_b:
            raise BotError(t("error.no_draw"))
        async with SessionLocal() as s:
            match = await s.get(Match, match_id)
        if not match or match.guild_id != itx.guild_id:
            raise BotError(t("error.match_not_found"))
        if not (await actions.is_match_captain(match_id, itx.user.id)
                or await is_admin(itx.user)):
            raise PermissionDenied(t("error.result_perm"))

        winner = "A" if score_a > score_b else "B"
        # `map_index` is part of MatchResult's primary key. Two near-simultaneous
        # submissions (both captains reporting at once) can both count the same
        # number of existing rows before either commits; the second's insert then
        # collides on the PK instead of silently duplicating — retry with a fresh
        # count rather than let that IntegrityError crash the interaction.
        attempts = 3
        for attempt in range(attempts):
            async with SessionLocal() as s:
                idx = len((await s.execute(
                    select(MatchResult).where(MatchResult.match_id == match_id)
                )).all())
                s.add(MatchResult(match_id=match_id, map_index=idx, map_name=map_name,
                                  score_a=score_a, score_b=score_b, winner_side=winner))
                try:
                    await s.commit()
                    break
                except IntegrityError:
                    await s.rollback()
                    if attempt == attempts - 1:
                        raise BotError(t("error.result_race"))
        await reply(itx, t("match.result_recorded", map=map_name, score_a=score_a,
                           score_b=score_b, winner=winner))

    @app_commands.command(description=L("cmd.match.partycode.desc"))
    @app_commands.describe(custom_id=L("cmd.match.partycode.custom_id"),
                           code=L("cmd.match.partycode.code"),
                           password=L("cmd.match.partycode.password"))
    async def partycode(self, itx: discord.Interaction, custom_id: int, code: str,
                        password: str = ""):
        match = await actions.active_match_for_custom(custom_id)
        if match and games_svc.uses_name_password(match.game):
            # Dota 2: `code` doubles as the lobby name, `password` its password.
            game = await actions.set_lobby_info(itx, custom_id, code, password)
        else:
            game = await actions.set_party_code(itx, custom_id, code)
        await reply(itx, games_svc.code_text("set", game, custom_id=custom_id))

    @app_commands.command(description=L("cmd.match.end.desc"))
    @app_commands.describe(custom_id=L("cmd.match.end.custom_id"),
                           force=L("cmd.match.end.force"))
    async def end(self, itx: discord.Interaction, custom_id: int, force: bool = False):
        # Ending a match whose result nobody reported throws the game away, so
        # the command refuses by default and points at the result form. `force`
        # is for the custom that genuinely has no result — abandoned, half the
        # lobby gone — and is staff-only because it writes off everyone's wins.
        if force and not await is_admin(itx.user):
            raise PermissionDenied(t("error.force_admin"))
        # Reply first — end_custom deletes the custom's channels.
        await itx.response.send_message(t("custom.ending_cmd", custom_id=custom_id),
                                        ephemeral=True)
        await actions.end_custom(itx, custom_id, require_result=not force)


async def setup(bot: commands.Bot):
    await bot.add_cog(MatchCog(bot))
