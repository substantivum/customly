"""Bot entrypoint."""
from __future__ import annotations

import logging

import discord
from discord.ext import commands

from bot.config import settings
from bot.core.errors import BotError
from bot.db import init_db
from bot.i18n import t
from bot.i18n.translator import BotTranslator
from bot.i18n.ui import LocalizedTree
from bot.tasks import start as start_scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("valbot")

COGS = [
    "bot.cogs.profile",
    "bot.cogs.panel",
    "bot.cogs.custom",
    "bot.cogs.match",
    "bot.cogs.maps",
    "bot.cogs.admin",
    "bot.cogs.queue",
    "bot.cogs.stats",
    "bot.cogs.help",
]


class ValBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True       # needed to resolve members + move them
        intents.voice_states = True  # needed for straggler moves
        super().__init__(
            command_prefix="!",
            intents=intents,
            # Binds the guild's language onto the task handling each interaction,
            # before any command callback runs. See bot.i18n.ui.
            tree_cls=LocalizedTree,
            # User-supplied strings (party codes, custom/map names, Riot IDs) are
            # echoed into public channels — never let them ping @everyone/@here
            # or a role. <@id> mentions the bot builds itself still work.
            allowed_mentions=discord.AllowedMentions(
                everyone=False, roles=False, users=True, replied_user=True
            ),
        )

    async def setup_hook(self) -> None:
        await init_db()
        # Localizes command/parameter/choice descriptions. Discord resolves
        # these from each *user's client locale*, not the server setting — the
        # runtime text the bot sends is what follows `/language`.
        await self.tree.set_translator(BotTranslator())
        from bot.core.views import (
            EndCustomButton,
            LeaveButton,
            PartyCodeButton,
            RegisterButton,
        )
        # persistent registration + lobby buttons (survive restarts)
        self.add_dynamic_items(
            RegisterButton, LeaveButton, PartyCodeButton, EndCustomButton
        )
        from bot.cogs.panel import AdminBoard, PlayerBoard, SuperBoard
        # persistent control boards, one per tier (survive restarts)
        for boardview in (PlayerBoard, AdminBoard, SuperBoard):
            self.add_view(boardview())
        # A ready check lives in memory; anything the last shutdown stranded in
        # the `ready` state would otherwise refuse to start forever.
        from bot.services.custom import clear_stale_ready_checks
        stale = await clear_stale_ready_checks()
        if stale:
            log.info("Reset %d custom(s) stuck in a ready check: %s", len(stale), stale)
        for c in COGS:
            await self.load_extension(c)
        if settings.guild_id:
            guild = discord.Object(id=settings.guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)   # instant in dev
        else:
            await self.tree.sync()              # global (up to 1h propagation)
        start_scheduler()
        log.info("Setup complete; commands synced.")

    async def on_ready(self):
        log.info("Logged in as %s (%s)", self.user, self.user.id)

    async def close(self) -> None:
        from bot.services import henrik
        await henrik.close()
        await super().close()


async def _on_app_error(itx: discord.Interaction, error: Exception):
    err = getattr(error, "original", error)
    # The tree's interaction_check already bound the guild language, so both the
    # BotError text and the fallback come out in the right one.
    msg = str(err) if isinstance(err, BotError) else t("error.generic")
    if isinstance(err, BotError):
        log.info("Handled BotError: %s", err)
    else:
        log.exception("Unhandled command error", exc_info=error)
    try:
        if itx.response.is_done():
            await itx.followup.send(msg, ephemeral=True)
        else:
            await itx.response.send_message(msg, ephemeral=True)
    except discord.HTTPException:
        pass


def main() -> None:
    bot = ValBot()
    bot.tree.on_error = _on_app_error
    bot.run(settings.discord_token)


if __name__ == "__main__":
    main()
