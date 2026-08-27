"""English catalog — the reference language.

Every key the bot uses must exist here; `ru.py` mirrors it. Placeholders are
`str.format` named fields, never positional, so a translator can reorder them.

Emoji policy: only *indicators* survive — the state dots (defined in
`bot.core.board`), the status marks used here (OK / warning / ready / declined /
unanswered) and the lock on data a viewer may not see. Nothing decorative.
"""
from __future__ import annotations

STRINGS: dict[str, str] = {
    # ------------------------------------------------------------- common ---
    "common.owner": "Owner",
    "common.state": "State",
    "common.seats": "Seats",
    "common.players": "Players",
    "common.waitlist": "Waitlist",
    "common.maps": "Maps",
    "common.draft": "Draft",
    "common.captains": "Captains",
    "common.selected": "Selected",
    "common.teams": "Teams",
    "common.waiting_on": "Waiting on",
    "common.team_a": "Team A",
    "common.team_b": "Team B",
    "common.enabled": "enabled",
    "common.disabled": "disabled",
    "common.auto_note": " _(auto)_",
    "common.auto_paren": " (auto)",
    "common.its_channel": "its channel",
    "common.hidden": "🔒 hidden",

    # roles / ranks
    "rank.player": "Player",
    "rank.admin": "Admin",
    "rank.superadmin": "SuperAdmin",
    "role.player": "player",
    "role.admin": "admin",
    "role.superadmin": "superadmin",

    # custom states, as shown to a player
    "state.registration": "registration",
    "state.full": "full",
    "state.ready": "ready check",
    "state.veto": "map veto",
    "state.live": "live",
    "state.done": "done",

    # tiers
    "tier.player": "Customs",
    "tier.admin": "Admin",
    "tier.superadmin": "Super Admin",

    # ------------------------------------------------------------ buttons ---
    "btn.register": "Register",
    "btn.leave": "Leave",
    "btn.confirm": "Confirm",
    "btn.force": "Force",
    "btn.cancel": "Cancel",
    "btn.back": "Back",
    "btn.refresh": "Refresh",
    "btn.continue": "Continue",
    "btn.browse": "Browse & join",
    "btn.create_custom": "Create custom",
    "btn.manage_customs": "Manage customs",
    "btn.manage_any": "Manage any custom",
    "btn.maps": "Maps",
    "btn.bans": "Bans",
    "btn.riot_approvals": "Riot ID Approvals",
    "btn.approve": "Approve",
    "btn.deny": "Deny",
    "btn.audit": "Audit",
    "btn.bot_roles": "Bot roles",
    "btn.prune": "Prune all customs",
    "btn.language": "Language",
    "btn.ready_check": "Ready check",
    "btn.start": "Start",
    "btn.force_start": "Force start",
    "btn.end": "End",
    "btn.delete": "Delete",
    "btn.seed": "Seed defaults",
    "btn.add_map": "Add map",
    "btn.competitive_pool": "Competitive pool",
    "btn.ban": "Ban",
    "btn.unban": "Unban",
    "btn.grant": "Grant",
    "btn.revoke": "Revoke",
    "btn.set_code": "Set party code",
    "btn.end_custom": "End custom",
    "btn.ready": "Ready",
    "btn.cant_play": "Can't play",
    "btn.attack": "Attack",
    "btn.defence": "Defence",

    # -------------------------------------------------------------- errors ---
    "error.generic": "Something went wrong.",
    "error.need_role": "This action needs the **{role}** role.",
    "error.need_role_cmd": "You need the **{role}** role for this.",
    "error.config_channel": "Run this in the configured config channel.",
    "error.custom_gone": "Custom #{custom_id} no longer exists.",
    "error.custom_not_found": "Custom not found.",
    "error.cant_manage": "You can't manage this custom.",
    "error.superadmin_only": "Superadmin only.",
    "error.force_superadmin": "Only superadmin may force.",
    "error.delete_perm": "Only the owner or a superadmin can delete this.",
    "error.manage_perm": "Only the owner or a superadmin can do that.",
    "error.start_perm": "Only the owner or a superadmin can start this custom.",
    "error.transfer_perm": "Only the owner or a superadmin can transfer this custom.",
    "error.already_owner": "{name} already owns Custom #{custom_id}.",
    "error.bot_owner": "A bot can't own a custom.",
    "error.code_perm": (
        "Only players registered for this custom (or an admin) can set the code."
    ),
    "error.end_perm": "Only players registered for this custom (or an admin) can end it.",
    "error.not_starter": "You're not one of the starters for this game.",
    "error.not_your_call": "Not your call.",
    "error.not_your_turn": "Not your turn to ban/pick.",
    "error.not_your_side": "Not your side to pick.",
    "error.not_your_pick": "Not your pick.",
    "error.bad_start": "Start must be `HH:MM` or ISO `2026-06-24T20:00`.",
    "error.no_queue": "No queue for this custom.",
    "error.no_channel": "This custom has no channel left to run the match in.",
    "error.no_match_yet": "That custom hasn't started a match yet.",
    "error.code_charset": "Party code must be alphanumeric (`-` and `_` allowed).",
    "error.already_ended": "This custom is already ended.",
    "error.not_started": "This custom hasn't started yet — delete it instead.",
    "error.match_not_found": "Match not found.",
    "error.result_perm": "Only a captain of this match or an admin can report results.",
    "error.no_draw": "A map can't end in a draw — scores must differ.",
    "error.riot_id": "Riot ID must look like `TenZ#NA1` (Name#TAG).",
    "error.riot_not_found": (
        "No Valorant account found for `{tag}` — check the spelling and try again."
    ),
    "error.riot_rate_limited": "The rank service is busy right now — try again in a minute.",
    "error.riot_timeout": "The rank service didn't respond in time — try again shortly.",
    "error.riot_unavailable": "Couldn't reach the rank service right now — try again later.",
    "error.flow_step": (
        "⚠️ Couldn't continue to **{what}** — `{error}`.\n"
        "Ask an admin to end this custom and start it again "
        "(the error is in the bot log)."
    ),
    "error.team_vcs": (
        "⚠️ Couldn't create the team voice channels — `{error}`. "
        "Carrying on with the veto; make them by hand or free up the "
        "customs category, then start the next one."
    ),

    # match-start guards
    "error.ready_running": (
        "A ready check is running on Custom #{custom_id}. Wait for it, or "
        "use **Start** / **Force start** to cut it short."
    ),
    "error.match_in_progress": (
        "Custom #{custom_id} already has a match in progress (state: {state}). "
        "Finish it, or run `/custom delete` to reset and start over."
    ),
    "error.pool_recreate": "{reason} Recreate the custom with a pool that fits.",
    "error.partial_even": "Manual start needs an even number of players ≥ 2 (have {n}).",
    "error.queue_not_full": (
        "Queue not full ({have}/{size}). "
        "Use force-start to begin with the current players."
    ),
    "error.manual_both": "Manual captains: provide both captains.",
    "error.manual_distinct": "Captains must be two different players.",
    "error.manual_registered": "Both captains must be registered in this custom.",

    # ready-check guards
    "error.ready_already": "A ready check is already running on Custom #{custom_id}.",
    "error.ready_state": (
        "Custom #{custom_id} is `{state}` — a ready check only makes sense "
        "before the match starts."
    ),
    "error.ready_no_channel": "This custom has no channel to run a ready check in.",
    "error.ready_even": "A ready check needs an even number of players ≥ 2 (have {n}).",

    # registration / creation guards
    "error.banned": "You are banned from joining games in this server.",
    "error.not_open": "Custom #{custom_id} is not open for registration.",
    "error.match_started": (
        "Custom #{custom_id} has already started — you can't leave once the "
        "match is running."
    ),
    "error.conflict": "Conflicts with **{name}** ({start}–{end}).",
    "error.already_registered": "Already registered.",
    "error.format": "Format must be BO1, BO3 or BO5.",
    "error.team_size": "Team size must be between 1 and 5 (1v1 to 5v5).",
    "error.draft_mode": "Draft mode must be one of: {modes}.",
    "error.captain_method": "Captain method must be one of: {methods}.",
    "error.unknown_captain": "Unknown captain method: {method}",
    "error.manual_two": "Manual method needs two captain picks.",
    "error.volunteers": "Need at least two volunteers.",
    "error.no_votes": "No votes recorded.",
    "error.no_comp_pool": (
        "No competitive pool set for this server yet — an admin can "
        "set it in **Admin panel → Maps → Competitive pool**."
    ),
    "error.no_maps_pool": (
        "No maps specified and the server has no enabled map pool. "
        "Run `/maps seed` first, or pass maps."
    ),
    "error.maps_not_enabled": "Maps not in enabled pool: {maps}",
    "error.in_progress_guard": (
        "Both team VCs are occupied — match in progress. "
        "End it first, or (superadmin) pass force:true."
    ),

    # veto pool rules
    "veto.pool.exact": "exactly {n} maps",
    "veto.pool.min": "at least {n} maps",
    "error.veto_format": "Format must be one of: {formats}.",
    "error.veto_pool": "{fmt} needs {requirement} in the pool (got {n}).",
    "error.veto_pool_hint": " Use `competitive` for the current competitive pool.",
    "error.veto_pool_max": (
        "{fmt} needs at most {max} maps in the pool (got {n}) — a veto can't "
        "show more ban/pick buttons than that. Trim the pool or pass an "
        "explicit, smaller map list."
    ),

    # ------------------------------------------------------------- custom ---
    "custom.asap": "**ASAP**",
    "custom.asap_full": "**ASAP** — as soon as the lobby is ready",
    "custom.reg.title": "Custom #{custom_id} — {name}",
    "custom.reg.body": (
        "**Format:** {fmt}  ·  **{size}v{size}**\n"
        "**Starts:** {start}\n"
        "**Block:** {from_time} – {to_time}\n"
        "**Map pool:** {pool}\n"
        "**Draft:** {draft}\n"
        "**Captains:** {captains}"
    ),
    "custom.reg.registered": "Registered ({n}/{size})",
    "custom.reg.waitlist": "Waitlist ({n})",
    "custom.reg.waitlist_more": "\n_…and {n} more_",
    "custom.reg.waitlist_note": "\n_Subs move up automatically when a starter leaves._",
    "custom.reg.footer": "Use the buttons below to register or leave.",
    "custom.created": "Created **Custom #{custom_id}** ({size}v{size}) → {channel}",
    "custom.joined": "Registered for Custom #{custom_id} — watch for the ready check.",
    "custom.joined_waitlist": (
        "Custom #{custom_id} is full — you're **#{position} on the waitlist** "
        "and move up automatically if someone drops out."
    ),
    "custom.left": "Left Custom #{custom_id}.",
    "custom.promoted_channel": (
        "<@{user_id}> — a seat opened up in **{name}**, you're in the game now."
    ),
    "custom.promoted_dm": (
        "You moved off the waitlist into **Custom #{custom_id} — {name}** "
        "in **{guild}**. You're playing."
    ),
    "custom.transfer_note": (
        "Ownership of **Custom #{custom_id} — {name}** transferred to "
        "{new_owner} by {actor}."
    ),
    "custom.transfer_dm": (
        "You now own **Custom #{custom_id} — {name}** in **{guild}** "
        "(handed over by {actor}).\n"
        "You can start, force start, end, transfer or delete it from "
        "**Admin panel → Manage customs**, or in {where}."
    ),
    "custom.transferred": "Ownership of Custom #{custom_id} → {member} (they've been notified).",
    "custom.transferred_short": "Ownership of #{custom_id} → {member} (they've been notified).",
    "custom.ending": "Ending the custom — voice and this channel will be removed.",
    "custom.ending_cmd": "Ending Custom #{custom_id}…",
    "custom.ended": "Ended Custom #{custom_id}.",
    "custom.deleted": "Deleted Custom #{custom_id}.",
    "custom.pruned": "Pruned {n} custom(s).",
    "custom.pruned_skipped": " Skipped (in progress): {ids}.",
    "custom.none_active": "No active customs.",
    "custom.list_line": (
        "**#{custom_id}** {name} · {fmt} · {size}v{size} · owner <@{owner_id}> · {state}"
    ),

    # -------------------------------------------------------------- boards ---
    "board.player.title": "Customs",
    "board.player.desc": (
        "Every open game is listed below. Press **Browse & join** to pick a "
        "game, register or leave, and check the roster."
    ),
    "board.admin.title": "Admin Panel",
    "board.admin.desc": "Create and run customs.",
    "board.super.title": "Super Admin",
    "board.super.desc": "Server-wide controls.",
    "board.open_games": "Open games ({n})",
    "board.active_customs": "Active customs ({n})",
    "board.customs_active": "Customs ({n} active)",
    "board.map_pool": "Map pool",
    "board.map_pool_count": "**{enabled}/{total}** enabled",
    "board.map_pool_unseeded": "_Not seeded — use **Maps → Seed defaults**._",
    "board.competitive": "Competitive pool",
    "board.admins": "Admins",
    "board.superadmins": "Superadmins",
    "board.banned": "Banned players",
    "board.config": "Config",
    "board.language": "Language",
    "board.more_granted": "_+{n} more_",
    "board.nothing_running": "_Nothing running right now._",
    "board.and_more": "_…and {n} more._",
    "board.none_active": "_none active_",
    "board.line.seats": "{fmt} · {size}v{size} · **{taken}/{total}** seats",
    "board.line.waiting": " (+{n} waiting)",
    "board.line.starts": "starts {when}",
    "board.line.owner": "owner {owner}",
    "board.footer.player": "Updates itself · your menu is private to you",
    "board.footer.staff": "Updates itself when a custom changes",
    "board.cfg.category": "customs category",
    "board.cfg.config_channel": "config channel",
    "board.cfg.admin_channel": "admin channel",
    "board.cfg.super_channel": "superadmin channel",

    # -------------------------------------------------------------- panel ---
    "panel.err.pinned": (
        "The **{tier}** board is pinned to <#{channel_id}> (`{env}`). Run it there."
    ),
    "panel.err.reserved": (
        "This channel is reserved for the **{other}** board — "
        "post the {tier} board somewhere else."
    ),
    "picker.desc": "{fmt} · {size}v{size} · {state}",

    # ------------------------------------------------------------- screens ---
    "screen.gone.title": "Gone",
    "screen.customs.title": "Customs — pick a game",
    "screen.customs.desc": "Choose one below to see its roster and register.",
    "screen.customs.empty": "No games are open right now. Check back later.",
    "screen.customs.youre_in": "  ✅ **you're in**",
    "screen.customs.pick": "Choose a game…",
    "screen.custom.you": "You",
    "screen.custom.you_waitlist": "On the waitlist — you play if a starter drops.",
    "screen.custom.you_in": "✅ You're in the game.",
    "screen.custom.closed": "Registration is closed for this game.",

    "screen.create.title": "Create a custom",
    "screen.create.desc": (
        "Set the map pool and draft mode here, then **Continue** for name, "
        "format, team size and start time."
    ),
    "screen.create.all_maps": "_all {n} enabled maps_",
    "screen.create.no_maps": "⚠️ No enabled maps — seed the pool in **Maps** first.",
    "screen.create.no_comp": (
        "No competitive pool set yet — set it in **Maps → Competitive pool**."
    ),
    "screen.create.min_maps": "Pick at least 2 maps, or none for the whole pool.",
    "screen.create.pool_ph": "Map pool — pick 2+ maps (none = whole enabled pool)…",
    "screen.create.draft_ph": "Draft mode — snake (default) or one by one…",
    "screen.create.captains_ph": "Captains — how the two captains are chosen…",

    "screen.manage_list.title": "Manage customs",
    "screen.manage_list.desc_all": "Every active custom in the server.",
    "screen.manage_list.desc_own": "The customs you own.",
    "screen.manage_list.active": "Active ({n})",
    "screen.manage_list.empty_own": (
        "You don't own an active custom. Create one, or ask a superadmin to "
        "transfer one to you."
    ),
    "screen.manage_list.pick": "Pick a custom to manage…",

    "screen.manage.title": "Custom #{custom_id} — {name}",
    "screen.manage.body": (
        "{dot} **{state}**  ·  {fmt}  ·  **{size}v{size}**\n"
        "**Starts:** {start}\n"
        "**Map pool:** {pool}\n"
        "**Draft:** {draft}\n"
        "**Captains:** {captains} _(set at creation)_"
    ),
    "screen.manage.ready_title": "Ready check running",
    "screen.manage.ready_body": (
        "Players are confirming in the custom's channel. **Start** or "
        "**Force start** cuts it short and begins anyway."
    ),
    "screen.manage.transfer_ph": "Transfer ownership to…",

    "screen.maps.empty": "No maps configured — press **Seed defaults**.",
    "screen.maps.footer": "Ticking a map competitive enables it for play.",
    "screen.maps.toggle_ph": "Toggle maps on/off (pick as many as you like)…",
    "screen.maps.comp_ph": "Competitive pool — tick the current rotation…",
    "screen.maps.in_comp": "in the competitive pool",
    "screen.maps.flipped": "**{name}** → {state}",
    "screen.maps.nothing": "Nothing to toggle.",

    "screen.bans.title": "Bans",
    "screen.bans.desc": "Banned players can't register for any game in this server.",
    "screen.bans.count": "Banned ({n})",
    "screen.bans.more": "_…and {n} more._",
    "screen.bans.pick_hint": "_pick a player below_",
    "screen.bans.player_ph": "Player…",

    "screen.riot_approvals.title": "Riot ID Approvals",
    "screen.riot_approvals.desc": (
        "Review pending Riot ID submissions before a player's rank counts "
        "anywhere in the bot."
    ),
    "screen.riot_approvals.count": "Pending ({n})",
    "screen.riot_approvals.pick": "Pick a submission to review",
    "screen.riot_approvals.more": "_…and {n} more._",

    "screen.audit.title": "Audit log",
    "screen.audit.empty": "_No audit entries yet._",
    "screen.audit.footer": "15 most recent entries",

    "screen.roles.title": "Bot roles",
    "screen.roles.desc": (
        "Roles granted here are on top of the `ADMIN_ROLE` / `SUPERADMIN_ROLE` "
        "Discord roles from `.env`."
    ),
    "screen.roles.count": "{role} ({n})",
    "screen.roles.selected": "{member} → **{role}**",
    "screen.roles.pick_hint": "_pick a member_",
    "screen.roles.member_ph": "Member…",
    "screen.roles.role_ph": "Role…",

    "screen.language.title": "Language",
    "screen.language.desc": (
        "The language the bot speaks in this server. It applies to everyone: "
        "boards, menus, match messages and errors."
    ),
    "screen.language.current": "Current",
    "screen.language.pick": "Choose a language…",

    "confirm.force_note": (
        "Force also overrides the in-progress guard "
        "(disconnects anyone in the team voice channels)."
    ),
    "confirm.delete.title": "⚠️ Delete Custom #{custom_id}?",
    "confirm.delete.desc": (
        "**{name}** — its channel, voice channels and queue all go away. "
        "This can't be undone."
    ),
    "confirm.prune.title": "⚠️ Delete every custom in this server?",
    "confirm.prune.desc": (
        "**{n} active** custom(s) plus any finished ones, with their channels "
        "and queues. This can't be undone."
    ),

    # ---------------------------------------------------------------- maps ---
    "maps.added": "Added **{name}**.",
    "maps.err.empty": "Map name can't be empty.",
    "maps.err.exists": "**{name}** is already in the pool.",
    "maps.comp_set": "Competitive pool: **{maps}** (enabled for play).",
    "maps.comp_cleared": "Competitive pool cleared.",
    "maps.comp_unknown": "\nNot in this server's map list (ignored): {maps}",
    "maps.seeded": "Seeded {n} map(s).",
    "maps.already_seeded": "Pool already seeded.",
    "maps.none_configured": "No maps configured. Admin: `/maps seed` to load defaults.",
    "maps.seeded_ok": "Default pool seeded.",
    "maps.added_cmd": "Added {name}.",
    "maps.removed": "Removed {name}.",
    "maps.no_such": "No such map.",
    "maps.toggled": "{name} is now {state}.",
    "maps.list_line": "{dot} {name}",
    "maps.list_line_comp": "{dot} {name} — competitive",

    # ---------------------------------------------------------------- bans ---
    "bans.banned": "Banned {member}.",
    "bans.already_banned": "Already banned {member}.",
    "bans.unbanned": "Unbanned {member}.",
    "bans.not_banned": "Was not banned {member}.",
    "bans.reason_suffix": "\nReason: {reason}",
    "bans.none": "No banned players.",

    # ------------------------------------------------------- riot approvals ---
    "riot_approvals.approved": "{member} approved.",
    "riot_approvals.denied": "{member} denied.",
    "riot_approvals.gone": "That submission was already reviewed.",
    "riot.dm.approved": (
        "Your Riot ID **{tag}** was approved on **{guild}** — your rank is "
        "now visible on your profile."
    ),
    "riot.dm.denied": (
        "Your Riot ID **{tag}** was denied on **{guild}**. Re-run /register "
        "with the correct Riot ID to try again."
    ),

    # --------------------------------------------------------------- roles ---
    "roles.granted": "Granted **{role}** to {member}.",
    "roles.revoked": "Revoked **{role}** from {member}.",
    "admin.notify_role.set": "Notify role set to {role}.",
    "admin.notify_role.cleared": "Notify role cleared.",

    # --------------------------------------------------------------- audit ---
    "audit.none": "No audit entries.",
    "audit.line": "`{ts}` {actor} **{action}** {target}",

    # -------------------------------------------------------------- captain ---
    "captain.random": "Random",
    "captain.highest_rr": "Highest RR",
    "captain.highest_peak": "Highest peak rank",
    "captain.highest_wins_peak": "Most customs won (peak rank tiebreak)",
    "captain.highest_wins_rr": "Most customs won (RR tiebreak)",
    "captain.manual": "Manually chosen",
    "captain.volunteer": "Volunteers",
    "captain.vote": "Voted",
    "captain.help.random": "two random players from the lobby",
    "captain.help.highest_rr": "the two highest current RR — needs profiles filled in",
    "captain.help.highest_peak": "the two highest peak ranks — needs profiles filled in",
    "captain.help.highest_wins_peak": (
        "the two with the most customs won — ties broken by peak rank"
    ),
    "captain.help.highest_wins_rr": (
        "the two with the most customs won — ties broken by current RR"
    ),

    # --------------------------------------------------------------- draft ---
    "draft.mode.snake": "Snake (A, BB, AA, …)",
    "draft.mode.alternate": "One by one (A, B, A, B, …)",
    "draft.snake.label": "Snake draft",
    "draft.snake.desc": "A, BB, AA, BB … — evens out the first-pick edge",
    "draft.alternate.label": "One by one",
    "draft.alternate.desc": "A, B, A, B … — strict alternating picks",
    "draft.title.snake": "Snake Draft",
    "draft.title.alternate": "Draft (one by one)",
    "draft.title": "{mode} — Match #{match_id}",
    "draft.on_clock": "On the clock",
    "draft.on_clock_value": "{captain} ({side}) — {n} left",
    "draft.complete": "Complete",
    "draft.complete_value": "All players drafted.",
    "draft.pick_ph": "Pick a player…",

    # ---------------------------------------------------------------- coin ---
    "coin.title": "Coin Toss — Match #{match_id}",
    "coin.heads": "Heads",
    "coin.tails": "Tails",
    "coin.calling": "Calling",
    "coin.call": "Call",
    "coin.landed": "Landed",
    "coin.winner": "Toss winner",
    "coin.wait_call": "heads or tails",
    "coin.wait_letter": (
        "{captain} — **Team A** or **Team B**\n"
        "Team A drafts first and bans first."
    ),
    "coin.teams_value": (
        "Team A {cap_a} · Team B {cap_b}\nTeam A drafts first and bans first."
    ),

    # ---------------------------------------------------------------- veto ---
    "veto.title": "Map Veto — Match #{match_id}",
    "veto.remaining": "Remaining",
    "veto.picked": "Picked",
    "veto.sides": "Sides",
    "veto.turn": "Turn",
    "veto.attack": "attack",
    "veto.defence": "defence",
    "veto.action.ban": "ban",
    "veto.action.pick": "pick",
    "veto.turn_action": "{captain} to {action}",
    "veto.turn_side": "{captain} picks a side on **{map}**",
    "veto.side_text": "**{map}** — Team {chooser} {choice}, Team {other} {flip}",
    "veto.result_maps": "Map selection complete{note}.\n{lines}",
    "veto.result_simple": "Veto complete{note}. Maps: **{maps}**",

    # --------------------------------------------------------------- ready ---
    "ready.title": "Ready check — Custom #{custom_id} · {name}",
    "ready.round": " (round {n})",
    "ready.desc": (
        "Everyone below has to be ready before the match starts.\nCloses {when}.\n"
        "**Can't play** frees your seat for a sub straight away."
    ),
    "ready.count": "Ready {n}/{total}",
    "ready.ping": "**Ready check** — {mentions}",
    "ready.posted": (
        "Ready check posted in {channel} — {n} player(s) have {seconds}s to confirm."
    ),
    "ready.resolving": "Resolving…",
    "ready.cancel.manual": "Cut short — {actor} started the match manually.",
    "ready.cancel.deleted": "Custom deleted.",
    "ready.outcome.all_ready": "✅ Everyone ready — starting the match.",
    "ready.outcome.incomplete": "⚠️ Not everyone confirmed. Dropped: {dropped}",
    "ready.subs_round": (
        "{dropped} lost their seat — subs moved up. "
        "Running ready check round **{round}**."
    ),
    "ready.failed": (
        "⚠️ **Ready check failed** for Custom #{custom_id} — {why}. "
        "{filled}/{size} seats filled; registration is open again. "
        "An admin can re-run the check or force start."
    ),
    "ready.why.no_subs": "no subs were waiting",
    "ready.cooldown_retry": (
        "⚠️ Ready check failed {n} times in a row — retrying automatically "
        "in {seconds}s."
    ),

    # --------------------------------------------------------------- match ---
    "match.announce": (
        "**Match #{match_id}** ({per_side}v{per_side}) — "
        "captains <@{cap_a}> vs <@{cap_b}> ({method})."
    ),
    "match.subs": (
        "**Subs (not in this match):** {subs} — you signed up after the seats filled."
    ),
    "match.captains_fallback_random": (
        "⚠️ Not enough players have an approved rank yet — falling back to "
        "random captains instead of **{method}**."
    ),
    "match.starting": (
        "Match #{match_id} starting ({per_side}v{per_side}) in {channel}. "
        "Captains: <@{cap_a}> vs <@{cap_b}> — the coin toss decides who's Team A."
    ),
    "match.result_recorded": "Recorded {map}: A {score_a}–{score_b} B (winner {winner}).",

    # --------------------------------------------------------------- lobby ---
    "lobby.title": "Match Lobby — Custom #{custom_id}",
    "lobby.full_title": "{name} — Match #{match_id} ({fmt})",
    "lobby.team_cap": "{team} (cap {captain})",
    "lobby.party_code": "Party Code",
    "lobby.voice": "Voice",
    "lobby.map_line": "**{index}. {map}** — Team A {side_a} · Team B {side_b}",
    "lobby.map_line_plain": "**{index}. {map}**",
    "lobby.footer": "Anyone playing this custom can set the code or end the match.",
    "code.updated": "Party code updated.",
    "modal.create.title": "Create custom",
    "modal.create.name": "Name",
    "modal.create.name_ph": "Friday 5v5",
    "modal.create.fmt": "Format (BO1/BO3/BO5)",
    "modal.create.team_size": "Team size (1-5)",
    "modal.create.start": "Start — blank = ASAP",
    "modal.create.start_ph": "20:00 (server time) or ISO — leave empty to play now",
    "modal.addmap.title": "Add map",
    "modal.addmap.name": "Map name",
    "modal.addmap.name_ph": "Ascent",
    "modal.ban.title": "Ban player",
    "modal.ban.reason": "Reason (optional)",
    "modal.code.title": "Party code",
    "modal.code.label": "Party / group code",
    "modal.code.ph": "7F3K2",
    "code.set": "Party code for Custom #{custom_id} set.",
    "code.announced": "**Party Code — Custom #{custom_id}:** `{code}`  (set by {actor})",

    # ------------------------------------------------------------- profile ---
    "profile.register.pending": (
        "Submitted **{tag}** for review — an admin will approve or deny it "
        "before your rank shows up."
    ),
    "profile.register.unchanged": "Still **{tag}** — no change to your review status.",
    "profile.none": "No profile registered.",
    "profile.unregister.done": (
        "Your Riot ID has been unregistered. Run `/register` again anytime "
        "to re-verify."
    ),
    "profile.refresh.not_approved": "Your Riot ID isn't approved yet — nothing to refresh.",
    "profile.refresh.done": "Rank updated: **{rank}** ({rr} RR), peak **{peak}**.",
    "profile.refresh.failed": "Couldn't reach Riot's servers just now — try again in a bit.",
    "profile.title": "Profile — {name}",
    "profile.riot_id": "Riot ID",
    "profile.main_role": "Main role",
    "profile.rank": "Rank",
    "profile.rr": "RR",
    "profile.peak": "Peak",
    "profile.wins": "Customs won",
    "profile.role.duelist": "Duelist",
    "profile.role.controller": "Controller",
    "profile.role.initiator": "Initiator",
    "profile.role.sentinel": "Sentinel",
    "profile.role.flex": "Flex",

    # --------------------------------------------------------------- stats ---
    "stats.none": "No stats yet.",
    "stats.title": "Your stats",
    "stats.played": "Played",
    "stats.wl": "W/L",
    "stats.mvps": "MVPs",
    "stats.leaderboard.title": "Leaderboard",
    "stats.top": "Top {n}",
    "stats.leader_line": "{rank}. {name} — {wins} wins",

    # --------------------------------------------------------------- queue ---
    "queue.none": "No queue for that custom.",
    "queue.empty": "_empty_",
    "queue.header": "**Queue for Custom #{custom_id}** ({n}/{size})",
    "queue.waitlist": "\n**Waitlist:** {members}",

    # ------------------------------------------------------------ language ---
    "lang.changed": "Server language set to **{language}**.",
    "lang.unchanged": "Server language is already **{language}**.",
    "lang.unknown": "Unknown language `{lang}`. Available: {available}.",
    "lang.name.en": "English",
    "lang.name.ru": "Russian",

    # ------------------------------------------------- command descriptions ---
    "cmd.panel.desc": "Post a live control board in this channel.",
    "cmd.panel.tier": "Which board to post. Defaults to the one this channel is "
                      "configured for.",
    "cmd.panel.choice.player": "Customs — everyone",
    "cmd.panel.choice.admin": "Admin",
    "cmd.panel.choice.superadmin": "Super Admin",

    "cmd.language.desc": "Set the language the bot speaks in this server (superadmin).",
    "cmd.language.param": "Language to use for every message in this server.",

    "cmd.custom.create.desc": "Create a custom (admin, in the config channel).",
    "cmd.custom.create.name": "Custom name",
    "cmd.custom.create.format": "BO1/BO3/BO5",
    "cmd.custom.create.start": "HH:MM (server time) or ISO — omit to start ASAP",
    # Discord caps a parameter description at 100 characters.
    "cmd.custom.create.maps": (
        "Comma-separated pool, or `competitive` — blank uses every enabled map"
    ),
    "cmd.custom.create.team_size": "Players per side: 1 (1v1) … 5 (5v5). Default 5.",
    "cmd.custom.create.draft": "How players are drafted: snake, or one by one. Default snake.",
    "cmd.custom.create.captains": "How captains are chosen when this custom starts. "
                                  "Default random.",
    "cmd.custom.register.desc": "Register for a custom by id.",
    "cmd.custom.leave.desc": "Leave a custom by id.",
    "cmd.custom.list.desc": "List active customs.",
    "cmd.custom.transfer.desc": "Transfer ownership of a custom.",
    "cmd.custom.delete.desc": "Delete a custom by id (owner/superadmin).",
    "cmd.custom.delete.force": "Superadmin override of the occupancy guard",
    "cmd.custom.prune.desc": "Delete ALL customs (superadmin).",

    "cmd.match.start.desc": "Start a full custom: captains → draft → veto.",
    "cmd.match.forcestart.desc": "Manual start: begin with the currently registered players.",
    "cmd.match.custom_id": "Custom to start",
    "cmd.match.captains": "Override the custom's captain method just for this start (optional)",
    "cmd.match.captain_a": "(manual only) Team A captain",
    "cmd.match.captain_b": "(manual only) Team B captain",
    "cmd.match.readycheck.desc": (
        "Post a ready check: every starter has to confirm before the match runs."
    ),
    "cmd.match.readycheck.custom_id": "Custom to run the check on",
    "cmd.match.result.desc": "Report a map result (captain or admin).",
    "cmd.match.partycode.desc": (
        "Set/update the party code (any registered player). Shown to everyone."
    ),
    "cmd.match.partycode.custom_id": "Custom whose match this is",
    "cmd.match.partycode.code": "Party/group code",
    "cmd.match.end.desc": "End the match: mark it done and delete its voice + text channels.",
    "cmd.match.end.custom_id": "Custom whose match to end",

    "cmd.maps.list.desc": "List the guild map pool.",
    "cmd.maps.seed.desc": "Seed the default Valorant pool.",
    "cmd.maps.competitive.desc": "Set the current competitive map pool (admin). Empty clears it.",
    "cmd.maps.competitive.maps": (
        "Comma-separated maps in the active rotation — blank to clear the pool"
    ),
    "cmd.maps.add.desc": "Add a map.",
    "cmd.maps.remove.desc": "Remove a map.",
    "cmd.maps.toggle.desc": "Enable/disable a map.",

    "cmd.admin.grant.desc": "Grant a bot role (superadmin only for admin/superadmin).",
    "cmd.admin.revoke.desc": "Revoke a bot role.",
    "cmd.admin.audit.desc": "View recent audit log entries.",
    "cmd.admin.ban.desc": "Ban a player from joining future games.",
    "cmd.admin.unban.desc": "Unban a player.",
    "cmd.admin.bans.desc": "List banned players.",
    "cmd.admin.notify_role.desc": "Set (or clear) the role pinged when a custom opens.",
    "cmd.admin.notify_role.param": "Role to ping (omit to clear).",

    "cmd.profile.register.desc": (
        "Register your profile with your Riot ID — pending admin approval."
    ),
    "cmd.profile.register.riot_id": "Your Riot ID like TenZ#NA1",
    "cmd.profile.register.main_role": "Optional preferred role",
    "cmd.profile.unregister.desc": "Remove your registered Riot ID.",
    "cmd.profile.refresh.desc": "Force-refresh your current and peak rank from Riot.",
    "cmd.profile.view.desc": "View a player's profile.",

    "cmd.stats.me.desc": "Your stats.",
    "cmd.stats.leaderboard.desc": "Wins leaderboard.",

    "cmd.queue.status.desc": "Show a custom's queue status.",

    "cmd.help.desc": "Show a walkthrough of every command you can use.",

    # ---------------------------------------------------------------- help ---
    "help.title": "\U0001f4d6 Customly Command Guide",
    "help.desc": "Everything you can do, grouped by area — grant/admin-only "
                 "entries only show up if you hold that role.",
    "help.section.customs": "\U0001f3ae Customs",
    "help.section.match": "⚔️ Match",
    "help.section.queue": "\U0001f4cb Queue",
    "help.section.maps": "\U0001f5fa️ Maps",
    "help.section.profile": "\U0001f464 Profile & Rank",
    "help.section.stats": "\U0001f4ca Stats",
    "help.section.panel": "\U0001f39b️ Panel & Language",
    "help.section.admin": "\U0001f6e1️ Admin",
    "help.footer": "Type a command to see its own parameters and choices.",
}
