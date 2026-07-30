# Valorant Customs & Tournament Bot — Manual

A Discord bot that runs Valorant custom games end to end: registration, scheduling,
captain selection, snake draft, map veto, team voice channels, party codes,
bans, stats and an audit log. Everything is doable via slash commands
**or** the `/panel` button interface.

**Stack:** Python 3.12 · discord.py · SQLite (WAL) · Docker. No Riot API — a Riot ID
is just a display tag.

---

## 1. Quick start

```bash
cp .env.example .env          # fill in DISCORD_TOKEN (and GUILD_ID for instant commands)
docker compose up --build
```

Local, without Docker:

```bash
pip install -r requirements.txt
python -m bot
```

Once it's online, in your server run `/maps seed`, then `/register`. The server
owner (or anyone with Administrator) is treated as **SuperAdmin** automatically.

---

## 2. Installing on Discord

1. **Create the app + bot** at the Discord Developer Portal → *Bot* tab. Copy the
   **token** into `.env` as `DISCORD_TOKEN`.
2. **Enable privileged intents** (Bot tab → *Privileged Gateway Intents*):
   - **Server Members Intent** — to resolve and move members
   - **Voice State Intent** — for the team-voice move at game start
3. **Invite the bot** (OAuth2 → URL Generator):
   - Scopes: `bot`, `applications.commands`
   - Permissions: **Manage Channels**, **Move Members**, **Connect**,
     **Send Messages**, **View Channels**
4. **Role position:** drag the bot's role **above** the members it will move,
   or Discord refuses to move them.
5. **Channels:** create a category for customs and a `#custom-config` channel.
   Put their IDs in `.env` (enable Developer Mode → right-click → Copy ID).

---

## 3. Configuration (`.env`)

| Variable | Required | Purpose |
|---|---|---|
| `DISCORD_TOKEN` | yes | Bot token |
| `DB_PATH` | yes | SQLite file path (keep on the mounted volume, e.g. `/app/data/bot.db`) |
| `GUILD_ID` | no | Sync commands to one server instantly (use during testing) |
| `ADMIN_ROLE` | no | Discord role id — everyone holding it is a bot **admin** |
| `SUPERADMIN_ROLE` | no | Discord role id — everyone holding it is a bot **superadmin** |
| `TZ_OFFSET` | no | Server-local UTC offset for `HH:MM` start times (default 0). `6` = UTC+6 |
| `CUSTOMS_CATEGORY_ID` | no | Category where the custom's text channel and team VCs are created |
| `CUSTOM_CONFIG_CHANNEL` | no | Restricts `/custom create` to this channel |
| `DEFAULT_VOICE_CHANNEL` | no | Players are moved here when a match ends (blank = disconnect) |
| `DRAFT_PICK_SECONDS` | no | Per-turn draft timer (default 30) |
| `VETO_PICK_SECONDS` | no | Per-turn veto timer (default 30) |
| `READY_CHECK_SECONDS` | no | Reserved for ready-check (default 120) |

Leaving `GUILD_ID` blank syncs commands **globally**, which can take up to an hour
to appear. Set it while testing.

---

## 4. Roles & permissions

Three tiers, checked by the bot (separate from Discord roles):

| Tier | Who | Can do |
|---|---|---|
| **Player** | everyone who `/register`s | register/leave customs, view stats/queue, draft when captain |
| **Admin** | the `ADMIN_ROLE` Discord role, or granted via `/admin grant` | create/manage **their own** customs, start matches, maps, party code, bans |
| **SuperAdmin** | server owner / Administrator, the `SUPERADMIN_ROLE` Discord role, or granted | everything; manage **any** custom; grant roles; prune; audit |

A member's tier is the **highest** of three sources:

1. Discord server owner or the **Administrator** permission → SuperAdmin.
2. Holding the Discord role configured as `ADMIN_ROLE` / `SUPERADMIN_ROLE` in
   `.env` → Admin / SuperAdmin. This is the easy way to run the bot off roles you
   already have: set `ADMIN_ROLE=<role id>` and everyone with that role is an
   admin, with no per-person grant. Changes take effect immediately — the role is
   read live from Discord on every click.
3. A bot role granted in the DB: `/admin grant member:@x role:admin` ·
   `/admin revoke …`.

> To get a role id: enable **Developer Mode** in Discord (User Settings →
> Advanced), then right-click the role → **Copy Role ID**. Restart the bot after
> editing `.env`.

---

## 5. First-time server setup (checklist)

1. Invite the bot (section 2) and confirm it's online.
2. `/maps seed` — loads the default map pool (Ascent, Bind, Haven, Split, Lotus,
   Sunset, Icebox, Abyss, Pearl, Fracture).
3. `/admin grant` your organisers the **admin** role.
4. Players run `/register riot_id:Name#TAG`.
5. Test the flow: create a small custom, register players, start it.

---

## 6. The control panel (`/panel`)

`/panel` posts a **persistent Control Board** message in the channel. It stays put
(it survives bot restarts) and acts as a hub: tapping any button opens that button's
actions in a **new private (ephemeral) message** just for you — the board itself is
never replaced or dismissed. Pin it in a channel and your members use it like a menu.

The board shows **three entry buttons** rather than every action at once — pick the
view you want and its menu opens privately:

| Button | Who | Opens |
|---|---|---|
| 🎮 **Customs** | everyone | the pure customs view |
| 🛡 **Admin panel** | Admin+ | running customs |
| 👑 **Super Admin** | SuperAdmin | server-wide controls |

All three are visible to everyone, but the admin ones check your tier on click and
reply privately if you don't have access. The private menus auto-dismiss after ~30s
of inactivity.

**🎮 Customs (everyone)**
- **Profile** — modal to set Riot ID + optional role/rank/RR/peak
- **Join / leave a custom** — pick a custom → Register / Leave / Queue status
- **My stats** — your record

**🛡 Admin panel**
- **Create custom** — pick the map pool from a dropdown, then a modal for
  name / format / team size / start
- **Maps** — seed, add, and toggle any number of maps on/off in one go
- **Manage customs** — pick one → **Start / Force start / End** / transfer / delete
- **Bans** — pick a player → Ban (reason modal) / Unban / List
- **Audit** — recent audit entries

**👑 Super Admin**
- **Roles** — pick member + role → Grant / Revoke
- **Prune all customs** — delete every custom (with confirm/force)
- **Audit** — recent audit entries

> After updating the bot, re-run `/panel` and delete the old board — buttons on a
> board posted by an older version no longer resolve.

> Manual captain selection isn't available from the panel — use
> `/match start captains:manual captain_a:@x captain_b:@y` for that.

---

## 7. Command reference

### Player
| Command | Description |
|---|---|
| `/register riot_id [main_role] [cur_rank] [cur_rr] [peak_rank]` | Create/update your profile (tag only; rank fields optional) |
| `/profile [member]` | View a profile |
| `/panel` | Open the button hub |
| `/custom register custom_id` | Join a custom (subject to ban + time-overlap checks) |
| `/custom leave custom_id` | Leave a custom |
| `/custom list` | List active customs |
| `/queue status custom_id` | Show a custom's queue |
| `/stats me` · `/stats leaderboard` | Your stats / wins leaderboard |

### Admin (owner of the custom unless noted)
| Command | Description |
|---|---|
| `/custom create name format start [maps] [team_size]` | Create a custom (run in `#custom-config`); **maps optional — blank = all enabled** |
| `/custom transfer custom_id to:@user` | Hand ownership to another admin |
| `/custom delete custom_id [force]` | Delete a custom (occupancy guard; `force` = superadmin) |
| `/match start custom_id [captains] [captain_a] [captain_b]` | Start when the queue is full |
| `/match forcestart custom_id [captains] …` | Start now with current players (even, ≥2) |
| `/match result match_id map_name score_a score_b` | Record a map score (captain of that match, or admin) |
| `/match end custom_id` | End the match: mark done, delete the custom's voice **and** text channels |
| `/match partycode custom_id code` | Set the party code (any registered player); posted openly |
| `/maps list\|seed\|add\|remove\|toggle` | Manage the map pool |
| `/admin ban member [reason]` · `/admin unban member` · `/admin bans` | Block/allow players from future games |
| `/admin audit [limit]` | Recent audit entries |

### SuperAdmin
| Command | Description |
|---|---|
| `/custom prune [force]` | Delete **all** customs in the server |
| `/custom delete … force:true` | Override the occupancy guard |
| `/admin grant\|revoke member role` | Manage bot roles |

---

## 8. Core workflows

### 8.1 Create a custom
`/custom create` (in `#custom-config`) or panel → **Create custom**.
- **format:** BO1 / BO3 / BO5
- **team_size:** 1–5 → 1v1 … 5v5 (queue size = team_size × 2)
- **start:** `HH:MM` in server time (`TZ_OFFSET` in `.env`) or full ISO. A time
  that already passed today is taken as tomorrow.
- **maps:** comma-separated, must be in the enabled pool. **Optional** — leave it
  blank to use **all enabled maps** in the server pool (run `/maps seed` first).

The bot creates a dedicated `#<your-name>-<custom-name>` text channel with a registration embed
(Register / Leave buttons). The channel is **read-only**: everyone can see it and use
the Register/Leave buttons, but **only the bot and (later) the two captains can type**
in it. The whole match flow — captain announcement, snake draft, the map ban/pick
veto, and the final lobby — all happens **in this channel**, not in `#custom-config`.
Start time renders as a Discord timestamp, localized for every viewer.

### 8.2 Register & the scheduling rule
Players register via the buttons or `/custom register`. A player may hold **many**
customs at once **as long as their time blocks don't overlap**. The block length is
the format duration: **BO1 = 1h, BO3 = 3h, BO5 = 5h**, starting at the custom's start
time. A clash is rejected and names the conflicting custom. Banned players are
blocked from registering anywhere in the server.

### 8.3 Start a match
- **`/match start`** requires a full queue (team_size × 2).
- **`/match forcestart`** starts with whoever's registered (must be even, ≥2).
- **Captain method:** `random`, `highest_rr`, `highest_peak`, or `manual`
  (pass `captain_a`/`captain_b`).

A custom that's already `captains`/`veto`/`live` can't be re-started — delete it to
reset. From the panel, **start / force start / end / transfer / delete** all live under
**Manage customs → pick a custom**.

### 8.4 Snake draft
The two captains draft the remaining players in snake order (A, BB, AA, …) from a
dropdown. Each turn has a timer (`DRAFT_PICK_SECONDS`); if a captain stalls, the bot
**auto-drafts a random remaining player**. In a 1v1 there's nobody to draft, so this
step is skipped automatically.

### 8.5 Map veto
Uses the **custom's** map pool. BO1 alternates bans down to one; BO3/BO5 open with
ban/ban/pick… then alternate bans through any surplus maps to the decider, so a pool
of any size resolves to the right number of maps. Minimum pool: **2** for BO1,
**5** for BO3, **7** for BO5 — creation is rejected below that.
Buttons appear per remaining map; only the captain on the
clock may act. Each turn has a timer (`VETO_PICK_SECONDS`); on timeout the bot
**bans/picks a random remaining map**.

### 8.6 Going live — the match lobby
When veto finishes, the bot marks the match **live** and posts the **lobby** in the
custom's own channel: both teams (👑 marks the captain), the chosen maps, the party
code, and links to the team voice channels. Two buttons sit under it:

- **🔑 Set party code** — opens a small modal; the lobby embed updates in place.
- **🏁 End custom** — ends the match (see 8.9).

Both work for **anyone registered for that custom**, plus admins. Discord can't hide
a button from specific viewers, so everyone sees them, but a click from someone who
isn't in the custom is refused with a private message. The buttons are persistent —
they keep working after a bot restart.

### 8.7 Voice channels
At game start the bot creates `team_a_<id>` and `team_b_<id>` under the customs
category. **The channels are open** — anyone can connect, so friends and observers
just join, and there's nothing to grant. The bot does a **one-time move** of
already-connected players into their team VC; after that, players may leave and
rejoin freely and are never auto-moved again. Anyone not connected at start simply
joins the channel themselves.

### 8.8 Party code
Lobby → **🔑 Set party code** (preferred), or `/match partycode custom_id code`.
Settable by **any player registered for the custom** (and admins), and visible to
everyone. The match must have started first — the code lives on the match.

### 8.9 End a match
Lobby → **🏁 End custom**, `/match end custom_id`, or panel → **Manage customs →
End**. Any registered player can end it once it has started. Ending marks the match
completed and the custom done, then **deletes the team voice channels and the
custom's text channel** (anyone still in voice is moved to `DEFAULT_VOICE_CHANNEL`,
or disconnected if that isn't set). The DB records are kept for stats/audit.

### 8.10 Results
`/match result match_id map_name score_a score_b` records each map's score and
winner. Restricted to a captain of that match or an admin.

---

## 9. Match lifecycle

```
registration → full → captains → veto → live
       │
    (delete / prune at any time, subject to the occupancy guard)
```

- **registration** — open for sign-ups
- **full** — queue filled
- **captains / veto** — match running (draft then veto)
- **live** — teams set, maps chosen, lobby posted
- **done** — match ended (`/match end`)

---

## 10. Admin operations

- **Bans:** `/admin ban`, `/admin unban`, `/admin bans` (or panel → Bans). A ban
  blocks the player from registering for any future custom in the server.
- **Maps:** `/maps seed|add|remove|toggle`. Disabled maps can't be put in a pool.
- **Ownership:** `/custom transfer` reassigns a custom; the new owner must be an
  admin. Registrations and channels are untouched.
- **Delete / prune:** `/custom delete` (own) / `/custom prune` (all, superadmin).
  Cascades the registrations, queue, the custom's text channel and team VCs.
- **Occupancy guard:** delete/prune is blocked while **both** team voice channels
  have people in them (game in progress). SuperAdmin can override with `force:true`,
  which disconnects members first.
- **Audit:** every state-changing action is logged; `/admin audit` shows recent
  entries.

---

## 11. Timezones

- Display: all times render as Discord timestamps (`<t:…>`), automatically shown in
  each viewer's local timezone.
- Input: `start:20:00` means 20:00 in server time (`TZ_OFFSET`). Full ISO with
  an offset (e.g. `2026-06-24T20:00+06:00`) is also accepted. Internally everything is
  stored as a UTC instant, so it's correct regardless of the host's timezone.

---

## 12. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Slash commands don't appear | Global sync can take ~1h. Set `GUILD_ID` for instant sync in your server. |
| Buttons do nothing after a restart | Registration buttons persist; in-flight draft/veto views don't. Delete and recreate the custom. |
| Veto seems stuck / won't advance | Old versions had no veto→live step. On the current build it auto-advances; a custom stuck from before must be `/custom delete`d and recreated. |
| `/match start` says "already in progress" | The custom is in captains/veto/live. Run `/custom delete` to reset, then start again. |
| Party code says "hasn't started a match yet" | It needs `/match start` first — the code lives on the match. |
| Players aren't moved into team VCs | The bot needs **Move Members** + a role above them, and **Server Members**/**Voice State** intents enabled. Players not in voice at start can't be pulled — they join the channel themselves. |
| `team_size` column error on an old DB | Schema changed. Delete `bot.db` (dev) or `ALTER TABLE customs ADD COLUMN team_size INTEGER DEFAULT 5;`. Same idea for `bans` / `match_spectators` tables — easiest is to let a fresh DB build. |
| Docker "mount source path … file exists" (WSL) | Run `wsl --shutdown`, restart Docker Desktop, then `docker compose down && up`. Or switch `./data` to a named volume. Keep the project under `/home/...`, not `/mnt/c/...`. |
| Permission errors creating channels/VCs | The bot needs **Manage Channels**. |

---

## 13. Data & operations

- SQLite runs in **WAL** mode. Run a **single** bot instance (single writer). For
  heavy multi-server use, migrate to Postgres — the SQLAlchemy layer makes the swap
  cheap.
- The DB file lives at `DB_PATH` (mount `./data` or a named volume so it persists
  across container rebuilds).
- Backup = copy the `bot.db` file while the bot is idle, or, with a named volume:
  `docker run --rm -v botdata:/data -v "$PWD":/backup alpine cp /data/bot.db /backup/`.
- Schema is created on first boot. For production, adopt Alembic migrations rather
  than relying on auto-create.

---

## 14. Command index (A–Z)

`/admin audit` · `/admin ban` · `/admin bans` · `/admin grant` · `/admin revoke` ·
`/admin unban` · `/custom create` · `/custom delete` · `/custom leave` ·
`/custom list` · `/custom prune` · `/custom register` · `/custom transfer` ·
`/maps add` · `/maps list` · `/maps remove` · `/maps seed` · `/maps toggle` ·
`/match forcestart` · `/match partycode` · `/match result` ·
`/match start` · `/panel` · `/profile` · `/queue status` · `/register` ·
`/stats leaderboard` · `/stats me`
