"""/match commands — thin wrappers over core.actions."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
from sqlalchemy import select

from bot.core import actions
from bot.core.errors import BotError, PermissionDenied
from bot.core.permissions import is_admin
from bot.core.ui import reply
from bot.db import SessionLocal
from bot.services import draft as draft_svc

# Overrides for `/match start`. The custom already carries a captain method
# chosen at creation; these are here for the one-off ("actually, let's have X and
# Y captain this one") that a stored setting can't express.
CAPTAIN_METHODS = ["random", "manual", "highest_rr", "highest_peak"]

_CAPTAIN_CHOICES = [
    app_commands.Choice(name=draft_svc.CAPTAIN_METHOD_LABEL.get(m, m), value=m)
    for m in CAPTAIN_METHODS
]
_CAPTAIN_DESC = (
    "Override the custom's captain method just for this start (optional)"
)


class MatchCog(commands.GroupCog, name="match"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(description="Start a full custom: captains → draft → veto.")
    @app_commands.describe(
        custom_id="Custom to start", captains=_CAPTAIN_DESC,
        captain_a="(manual only) Team A captain", captain_b="(manual only) Team B captain",
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

    @app_commands.command(
        description="Manual start: begin with the currently registered players."
    )
    @app_commands.describe(
        custom_id="Custom to start", captains=_CAPTAIN_DESC,
        captain_a="(manual only) Team A captain", captain_b="(manual only) Team B captain",
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

    @app_commands.command(
        description="Post a ready check: every starter has to confirm before the match runs."
    )
    @app_commands.describe(custom_id="Custom to run the check on")
    async def readycheck(self, itx: discord.Interaction, custom_id: int):
        from bot.core.permissions import can_manage_custom
        from bot.db.models import Custom

        async with SessionLocal() as s:
            c = await s.get(Custom, custom_id)
        if not c or c.guild_id != itx.guild_id:
            raise BotError("Custom not found.")
        if not await can_manage_custom(c, itx.user):
            raise PermissionDenied("Only the owner or a superadmin can do that.")
        await itx.response.defer(ephemeral=True)
        await reply(itx, await actions.start_ready_check(
            itx.guild, custom_id, actor_id=itx.user.id
        ))

    @app_commands.command(description="Report a map result (captain or admin).")
    async def result(
        self, itx: discord.Interaction, match_id: int, map_name: str, score_a: int, score_b: int
    ):
        from bot.db.models import Match, MatchResult

        if score_a == score_b:
            raise BotError("A map can't end in a draw — scores must differ.")
        async with SessionLocal() as s:
            match = await s.get(Match, match_id)
        if not match or match.guild_id != itx.guild_id:
            raise BotError("Match not found.")
        if not (await actions.is_match_captain(match_id, itx.user.id)
                or await is_admin(itx.user)):
            raise PermissionDenied("Only a captain of this match or an admin can report results.")

        winner = "A" if score_a > score_b else "B"
        async with SessionLocal() as s:
            idx = len((await s.execute(
                select(MatchResult).where(MatchResult.match_id == match_id)
            )).all())
            s.add(MatchResult(match_id=match_id, map_index=idx, map_name=map_name,
                              score_a=score_a, score_b=score_b, winner_side=winner))
            await s.commit()
        await reply(itx, f"Recorded {map_name}: A {score_a}–{score_b} B (winner {winner}).")

    @app_commands.command(description="Set/update the party code (any registered player). Shown to everyone.")
    @app_commands.describe(custom_id="Custom whose match this is", code="Party/group code")
    async def partycode(self, itx: discord.Interaction, custom_id: int, code: str):
        await actions.set_party_code(itx, custom_id, code)
        await reply(itx, f"Party code for Custom #{custom_id} set ✅")

    @app_commands.command(
        description="End the match: mark it done and delete its voice + text channels."
    )
    @app_commands.describe(custom_id="Custom whose match to end")
    async def end(self, itx: discord.Interaction, custom_id: int):
        # Reply first — end_custom deletes the custom's channels.
        await itx.response.send_message(f"Ending Custom #{custom_id}…", ephemeral=True)
        await actions.end_custom(itx, custom_id)


async def setup(bot: commands.Bot):
    await bot.add_cog(MatchCog(bot))
