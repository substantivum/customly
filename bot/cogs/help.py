"""/help — a categorized walkthrough of every command the caller can use."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.embeds import EMBED_COLOR
from bot.core.permissions import ADMIN, PLAYER, SUPER, member_level
from bot.core.ui import reply
from bot.i18n import t
from bot.i18n.translator import L

# (section header key, [(command text, description key, minimum role level), ...])
# Levels mirror each command's actual gate (see bot.core.permissions.require /
# the ownership checks in bot.core.actions) — a section with nothing the caller
# can use is simply left off the embed.
_SECTIONS: list[tuple[str, list[tuple[str, str, int]]]] = [
    ("help.section.customs", [
        ("/custom list", "cmd.custom.list.desc", PLAYER),
        ("/custom register", "cmd.custom.register.desc", PLAYER),
        ("/custom leave", "cmd.custom.leave.desc", PLAYER),
        ("/custom transfer", "cmd.custom.transfer.desc", PLAYER),
        ("/custom delete", "cmd.custom.delete.desc", PLAYER),
        ("/custom create", "cmd.custom.create.desc", ADMIN),
        ("/custom prune", "cmd.custom.prune.desc", SUPER),
    ]),
    ("help.section.match", [
        ("/match start", "cmd.match.start.desc", PLAYER),
        ("/match forcestart", "cmd.match.forcestart.desc", PLAYER),
        ("/match readycheck", "cmd.match.readycheck.desc", PLAYER),
        ("/match result", "cmd.match.result.desc", PLAYER),
        ("/match partycode", "cmd.match.partycode.desc", PLAYER),
        ("/match end", "cmd.match.end.desc", PLAYER),
    ]),
    ("help.section.queue", [
        ("/queue status", "cmd.queue.status.desc", PLAYER),
    ]),
    ("help.section.maps", [
        ("/maps list", "cmd.maps.list.desc", PLAYER),
        ("/maps seed", "cmd.maps.seed.desc", ADMIN),
        ("/maps competitive", "cmd.maps.competitive.desc", ADMIN),
        ("/maps add", "cmd.maps.add.desc", ADMIN),
        ("/maps remove", "cmd.maps.remove.desc", ADMIN),
        ("/maps toggle", "cmd.maps.toggle.desc", ADMIN),
    ]),
    ("help.section.profile", [
        ("/register", "cmd.profile.register.desc", PLAYER),
        ("/profile", "cmd.profile.view.desc", PLAYER),
        ("/refresh_rank", "cmd.profile.refresh.desc", PLAYER),
        ("/unregister", "cmd.profile.unregister.desc", PLAYER),
    ]),
    ("help.section.stats", [
        ("/stats me", "cmd.stats.me.desc", PLAYER),
        ("/stats leaderboard", "cmd.stats.leaderboard.desc", PLAYER),
    ]),
    ("help.section.panel", [
        ("/panel", "cmd.panel.desc", PLAYER),
        ("/language", "cmd.language.desc", SUPER),
    ]),
    ("help.section.admin", [
        ("/admin grant", "cmd.admin.grant.desc", ADMIN),
        ("/admin revoke", "cmd.admin.revoke.desc", ADMIN),
        ("/admin audit", "cmd.admin.audit.desc", ADMIN),
        ("/admin ban", "cmd.admin.ban.desc", ADMIN),
        ("/admin unban", "cmd.admin.unban.desc", ADMIN),
        ("/admin bans", "cmd.admin.bans.desc", ADMIN),
        ("/admin notify_role", "cmd.admin.notify_role.desc", ADMIN),
    ]),
]


class HelpCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(description=L("cmd.help.desc"))
    async def help(self, itx: discord.Interaction):
        level = await member_level(itx.user)
        e = discord.Embed(title=t("help.title"), description=t("help.desc"),
                          color=EMBED_COLOR)
        for header_key, entries in _SECTIONS:
            lines = [f"**`{name}`** — {t(desc_key)}"
                    for name, desc_key, min_level in entries if min_level <= level]
            if lines:
                e.add_field(name=t(header_key), value="\n".join(lines)[:1024], inline=False)
        e.set_footer(text=t("help.footer"))
        await reply(itx, embed=e, dismiss_after=None)


async def setup(bot: commands.Bot):
    await bot.add_cog(HelpCog(bot))
