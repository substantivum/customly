# Valorant Customs & Tournament Bot — Manual

A Discord bot that runs Valorant custom games end to end: registration, scheduling,
captain selection, coin toss, player draft, map veto, side selection, team voice
channels, party codes, bans, stats and an audit log. Everything is doable via slash commands
**or** the `/panel` control boards — three live, self-updating boards (players,
admins, superadmins) you post in three different channels.

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
| `ADMIN_ROLE` | no | Discord role id — everyone holding it is a bot **admin**, and may talk in every custom's channel |
| `SUPERADMIN_ROLE` | no | Discord role id — everyone holding it is a bot **superadmin**, and may talk in every custom's channel |
| `TZ_OFFSET` | no | Server-local UTC offset for `HH:MM` start times (default 0). `6` = UTC+6 |
| `CUSTOMS_CATEGORY_ID` | no | Category where the custom's text channel and team VCs are created |
| `CUSTOM_CONFIG_CHANNEL` | no | Restricts `/custom create` to this channel |
| `ADMIN_PANEL_CHANNEL` | no | Channel the 🛡 Admin board is pinned to — it can't be posted elsewhere |
| `SUPERADMIN_PANEL_CHANNEL` | no | Channel the 👑 Super Admin board is pinned to |
| `DEFAULT_VOICE_CHANNEL` | no | Players are moved here when a match ends (blank = disconnect) |
| `DRAFT_PICK_SECONDS` | no | Per-turn draft timer (default 30) |
| `VETO_PICK_SECONDS` | no | Per-turn veto timer (default 30) |
| `READY_CHECK_SECONDS` | no | How long starters get to confirm in a ready check (default 120) |

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
4. Create the two staff channels (admins-only / superadmins-only), put their ids in
   `ADMIN_PANEL_CHANNEL` and `SUPERADMIN_PANEL_CHANNEL`, and restart the bot.
5. Post the boards: `/panel` in your public customs channel, then `/panel` in each
   staff channel (section 6).
6. Players run `/register riot_id:Name#TAG`.
7. Test the flow: create a small custom, register players, start it.

---

## 6. The control boards (`/panel`)

There are **three boards, meant for three different channels** — a public one for
players and two staff ones you keep in private channels:

| Channel | Command | Board | Who can use it |
|---|---|---|---|
| e.g. `#customs` | `/panel` | 🎮 **Customs** | everyone |
| e.g. `#admin-panel` | `/panel tier:admin` | 🛡 **Admin** | Admin+ |
| e.g. `#super-panel` | `/panel tier:superadmin` | 👑 **Super Admin** | SuperAdmin |

Put the two staff channel ids in `ADMIN_PANEL_CHANNEL` / `SUPERADMIN_PANEL_CHANNEL`
and the split is enforced: a staff board **refuses to be posted anywhere else**, and
nothing else may be posted in those channels. With the ids set you can also drop the
`tier:` argument — a bare `/panel` posts whichever board the channel is configured
for. Leave the ids blank and `/panel tier:` still works, it just isn't pinned down.

Restrict who can *see* each channel with normal Discord permissions; the bot
enforces the tier on every click regardless.

### The board is live

A board is one persistent message (it survives restarts) whose **embed mirrors the
server state** — open games, seats taken, waitlist, map pool, staff. It redraws
itself whenever a custom is created, joined, left, started, ended or deleted, so
what you see is current without anyone touching it. **🔄 Refresh** forces a redraw.

Only **one board per tier per server**: re-running `/panel` for a tier posts a fresh
board and deletes the old one, so upgrading no longer leaves a dead board behind.

### The buttons open a private panel

Board buttons never change the board. Each opens **your own private message** that
*morphs in place* as you navigate — the embed always shows exactly where you are and
what the current state is, and the buttons on it change with it (Register is greyed
out when you're already in; **Start** is greyed out on a match that's already
running). **◀️ Back** steps up, **🔄 Refresh** re-reads. Because it's private, several
people can use the same board at once. It auto-dismisses after ~3 minutes idle.

**🎮 Customs board (everyone)**
- **Browse & join** → every open game with your own sign-up marked ✅ → pick one →
  full roster, waitlist, start time, map pool, and **Register / Leave**

**🛡 Admin board**
- **Create custom** — map pool, draft mode and **captain method** shown live in the
  embed as you pick them (or one click for the **⭐ Competitive pool**), then a
  modal for name / format / team size / start
- **Manage customs** — the customs you own (a superadmin sees all) → one custom →
  **🔔 Ready check / Start / Force start / End / Delete** and transfer ownership.
  How captains are picked is shown here but set at creation, not at start time.
- **Maps** — the whole pool with 🟢/🔴/⭐ state visible; toggle any number in one go
  and set the **⭐ competitive pool** (ticking a map there enables it for play)
- **Bans** — the ban list, plus pick a player → Ban (reason modal) / Unban
- **Audit** — the 15 most recent entries

**👑 Super Admin board**
- **Bot roles** — who currently holds admin/superadmin → pick member + role →
  Grant / Revoke
- **Manage any custom** — the admin manage flow, unrestricted by ownership
- **Prune all customs** — spells out the blast radius, then Confirm / Force
- **Audit** — the 15 most recent entries

> **Profiles, personal scores and leaderboards are deliberately not on the boards.**
> That feature isn't finished, so the panel stays a lobby tool. The slash commands
> `/register`, `/profile` and `/stats` still work.

> Manual captain selection isn't available from the panel — use
> `/match start captains:manual captain_a:@x captain_b:@y` for that.

---

## 7. Command reference

### Player
| Command | Description |
|---|---|
| `/register riot_id [main_role] [cur_rank] [cur_rr] [peak_rank]` | Create/update your profile (tag only; rank fields optional) |
| `/profile [member]` | View a profile |
| `/panel [tier]` | Post a live control board in this channel (see §6) |
| `/custom register custom_id` | Join a custom (subject to ban + time-overlap checks) |
| `/custom leave custom_id` | Leave a custom |
| `/custom list` | List active customs |
| `/queue status custom_id` | Show a custom's queue |
| `/stats me` · `/stats leaderboard` | Your stats / wins leaderboard |

### Admin (owner of the custom unless noted)
| Command | Description |
|---|---|
| `/custom create name format start [maps] [team_size] [draft] [captains]` | Create a custom (run in `#custom-config`); **maps optional — blank = all enabled**, or `competitive` for the competitive pool; **draft** = snake (default) or one by one; **captains** = random (default) / highest RR / highest peak |
| `/match readycheck custom_id` | Post a ready check now — every starter is tagged and must confirm (§8.4) |
| `/custom transfer custom_id to:@user` | Hand ownership to another admin — the registration embed is redrawn and the new owner is notified (DM + a note in the custom's channel) |
| `/custom delete custom_id [force]` | Delete a custom (occupancy guard; `force` = superadmin) |
| `/match start custom_id [captains] [captain_a] [captain_b]` | Start when the queue is full; cuts short a running ready check. **captains** overrides the custom's own method for this start only, and is the only place `manual` works |
| `/match forcestart custom_id [captains] …` | Start now with current players (even, ≥2) |
| `/match result match_id map_name score_a score_b` | Record a map score (captain of that match, or admin) |
| `/match end custom_id` | End the match: mark done, delete the custom's voice **and** text channels |
| `/match partycode custom_id code` | Set the party code (any registered player); posted openly |
| `/maps list\|seed\|add\|remove\|toggle` | Manage the map pool |
| `/maps competitive [maps]` | Set the current competitive pool (comma-separated; blank clears it). Maps in it are enabled automatically |
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
  Type `competitive` (or hit **⭐ Competitive pool** in the panel) to take the
  server's current competitive pool — see §8.14.
- **draft:** how the captains pick — **snake** (A, BB, AA, … — default) or
  **one by one** (A, B, A, B, …). Shown on the registration embed.
- **captains:** how the two captains are chosen when this custom starts —
  **🎲 random** (default), **📈 highest RR** or **🏔 highest peak rank** (the last
  two read the players' `/register` profiles). It belongs to the game, so it's
  fixed here rather than asked at start time; `/match start captains:…` can still
  override it for one start, and is the only way to name captains by hand.

The bot creates a dedicated `#<your-name>-<custom-name>` text channel with a registration embed
(Register / Leave buttons). The channel is **read-only** for the room: everyone can
see it and use the Register/Leave buttons, but only the bot, **anyone with the
`ADMIN_ROLE` / `SUPERADMIN_ROLE` Discord role**, the custom's **owner** (including a
new owner after a transfer) and — once the match starts — the **two captains** can
type in it. The whole match flow — captain announcement, snake draft, the map ban/pick
veto, and the final lobby — all happens **in this channel**, not in `#custom-config`.
Start time renders as a Discord timestamp, localized for every viewer.

### 8.2 Register, the waitlist & the scheduling rule
Players register via the buttons or `/custom register`. A player may hold **many**
customs at once **as long as their time blocks don't overlap**. The block length is
the format duration: **BO1 = 1h, BO3 = 3h, BO5 = 5h**, starting at the custom's start
time. A clash is rejected and names the conflicting custom. Banned players are
blocked from registering anywhere in the server.

**Seats and subs.** A custom has `team_size × 2` seats — a 3v3 has 6. The first six
to sign up are the **starters**; the custom flips to state `full` but stays open, and
anyone after that joins the **🪑 waitlist** as a sub. They're told their position,
and the registration embed lists them separately.

Subs are promoted **in join order, automatically**: when a starter leaves, the first
sub takes the seat and is pinged in the custom's channel (and by DM). The split is
derived from sign-up order rather than stored, so it can never drift out of step
with who's actually registered.

Only the starters play. Both `/match start` **and** `/match forcestart` take the
first `team_size × 2` and announce the rest as subs, so a 3v3 always starts as a
3v3 no matter how many signed up.

### 8.3 Start a match

There are **two ways in**, and they work together:

**A. The ready check (players start it themselves) — see §8.4.**
The moment the last seat fills, the bot posts a ready check in the custom's
channel tagging every starter. Everyone confirms → the match starts on its own.
No organiser needed.

**B. Manual start (owner / admin / superadmin).**
- **`/match start`** requires a full queue (team_size × 2).
- **`/match forcestart`** starts with whoever's registered (must be even, ≥2).
- Either one **cuts a running ready check short** and begins immediately — use it
  when you know everyone's there and don't want to wait out the clock.

**Captains are chosen by the method set on the custom when it was created**
(§8.1) — the start button doesn't ask. `/match start captains:…` overrides it for
one start only, and is the only place `manual` (with `captain_a`/`captain_b`)
lives, because naming two players is impossible before anyone has signed up.

A custom that's already `captains`/`veto`/`live` can't be re-started — delete it to
reset. On the 🛡 Admin board, **ready check / start / force start / end / transfer /
delete** all live under **Manage customs → pick a custom**, and each button is
greyed out when the custom's state doesn't allow it.

### 8.4 The ready check
A Valorant custom needs both teams full. Someone who gets drafted and never turns
up wrecks the game for nine other people — so before the flow begins, everyone
confirms they're actually there.

**It starts by itself** when the last seat fills, and an owner/admin can post one
any time from **Manage customs → 🔔 Ready check** (or `/match readycheck`). The
message tags every starter and gives them `READY_CHECK_SECONDS` (default 120) to
answer:

- **✅ Ready** — you're in.
- **❌ Can't play** — you're out, and your seat frees up for a sub.

The embed updates live with a ✅ / ❌ / ⬜ line per player. Only starters can click.
**Every starter must be ✅** — a majority isn't enough.

The check **resolves as soon as everyone has answered**, rather than sitting out
the full clock: `❌` is an answer, not silence.

**If it passes** → captains → coin toss → draft → veto → sides, as normal.

**If it doesn't**, the lobby repairs itself:

1. Everyone who didn't confirm (refused *or* silent) **loses their seat**.
2. Waitlisted subs are **promoted in join order** to fill the gaps.
3. If that refills the lobby, a **fresh round** runs automatically.

With **no subs left to promote** — or after **3 rounds** — the check gives up: the
custom drops back to `registration` with whoever's left, and the channel says so.
An admin can then re-run the check or force start.

> A ready check lives in memory. If the bot restarts mid-check the clock is lost,
> so on boot any custom stranded in `ready` is put back to `full` / `registration`
> and can simply be checked again.

### 8.5 Coin toss
Before anyone drafts, the bot posts a coin toss in the custom's channel:

1. A **random captain** is put on the clock and calls **Heads** or **Tails**.
2. The coin lands; whoever called it right **wins the toss**.
3. The toss winner picks **First pick** or **Second pick** — that decides which
   side opens the draft (the whole draft order mirrors accordingly).

Only the captain on the clock can click. Each step has the draft timer
(`DRAFT_PICK_SECONDS`); on timeout the bot decides that step at random and marks
the result _(auto)_. In a 1v1 there's nobody to draft, so the toss is skipped.

### 8.6 Draft — snake or one by one
The two captains draft the remaining players from a dropdown, starting with the
side that won first pick. The order comes from the custom's **draft mode**, set
at creation:

- **🐍 Snake** — A, BB, AA, BB … (the default; evens out the first-pick edge)
- **🔁 One by one** — A, B, A, B … (strict alternation, so first pick is worth more)

Each turn has a timer (`DRAFT_PICK_SECONDS`); if a captain stalls, the bot
**auto-drafts a random remaining player**. In a 1v1 there's nobody to draft, so this
step is skipped automatically.

### 8.7 Map veto
Uses the **custom's** map pool. BO1 alternates bans down to one; BO3/BO5 open with
ban/ban/pick… then alternate bans through any surplus maps to the decider, so a pool
of any size resolves to the right number of maps. Minimum pool: **2** for BO1,
**5** for BO3, **7** for BO5 — creation is rejected below that.
Buttons appear per remaining map; only the captain on the
clock may act. Each turn has a timer (`VETO_PICK_SECONDS`); on timeout the bot
**bans/picks a random remaining map**.

### 8.8 Attack or defence
Veto done, the bot asks for sides on the **decider** (the last map standing): the
team that did **not** make the last ban picks **🔫 Attack** or **🛡 Defence**, and
the other team takes the opposite. Only that team's captain can click; on timeout
(`VETO_PICK_SECONDS`) the bot picks at random and marks it _(auto)_. The choice is
announced in the channel and shown in the lobby embed. (If a veto had no bans at
all — a minimum-size BO3 pool — the last team to act loses the choice instead.)

### 8.9 Going live — the match lobby
When sides are settled, the bot marks the match **live** and posts the **lobby** in
the custom's own channel: both teams (👑 marks the captain), the chosen maps, the
sides, the party code, and links to the team voice channels. Two buttons sit under it:

- **🔑 Set party code** — opens a small modal; the lobby embed updates in place.
- **🏁 End custom** — ends the match (see 8.11).

Both work for **anyone registered for that custom**, plus admins. Discord can't hide
a button from specific viewers, so everyone sees them, but a click from someone who
isn't in the custom is refused with a private message. The buttons are persistent —
they keep working after a bot restart.

### 8.10 Voice channels
At game start the bot creates one voice channel per team under the customs
category, named after the custom, the side and that team's captain —
`friday-5v5-a-salta` / `friday-5v5-b-nex` — so several concurrent customs are easy
to tell apart. **The channels are open** — anyone can connect, so friends and observers
just join, and there's nothing to grant. The bot does a **one-time move** of
already-connected players into their team VC; after that, players may leave and
rejoin freely and are never auto-moved again. Anyone not connected at start simply
joins the channel themselves.

### 8.11 Party code
Lobby → **🔑 Set party code** (preferred), or `/match partycode custom_id code`.
Settable by **any player registered for the custom** (and admins), and visible to
everyone. The match must have started first — the code lives on the match.

### 8.12 End a match
Lobby → **🏁 End custom**, `/match end custom_id`, or panel → **Manage customs →
End**. Any registered player can end it once it has started. Ending marks the match
completed and the custom done, then **deletes the team voice channels and the
custom's text channel** (anyone still in voice is moved to `DEFAULT_VOICE_CHANNEL`,
or disconnected if that isn't set). The DB records are kept for stats/audit.

### 8.13 Results
`/match result match_id map_name score_a score_b` records each map's score and
winner. Restricted to a captain of that match or an admin.

### 8.14 The competitive map pool
Riot's active rotation is a subset of every map that exists, and it changes every
few acts. Rather than re-ticking it on every custom, mark it once:

- **🛡 Admin board → Maps → ⭐ Competitive pool** — tick the maps in the
  current rotation. The selection *replaces* the pool (untick everything to clear
  it), and anything in it is enabled for play automatically.
- Or `/maps competitive maps:Ascent,Bind,Haven,…` — blank clears the pool.

Once set, custom creation can take it in one step: the **⭐ Competitive pool**
button in the panel, or `maps:competitive` on `/custom create`. `/maps list` and
the Maps panel mark pool members with ⭐.

### 8.15 Transferring a custom
`/custom transfer custom_id to:@user`, or panel → **Manage customs → Transfer
ownership to…**. The owner or a superadmin can do it. On transfer the bot:

- rewrites the **registration embed** so its Owner field shows the new owner,
- posts a note in the custom's channel, and
- **DMs the new owner** (if their DMs are closed, the channel note still tells them).

The new owner gets the full owner toolkit — start, force start, end, transfer,
delete — under **Manage customs**.

---

## 9. Match lifecycle

```
registration → full → ready → captains → veto → live → done
       ▲               │
       └───────────────┘   ready check failed: absent players dropped,
                           subs promoted, retried (up to 3 rounds)

    (delete / prune at any time, subject to the occupancy guard)
```

- **registration** — open for sign-ups, seats still free
- **full** — every seat taken; sign-ups continue onto the waitlist as subs
- **ready** — 🔔 ready check on the clock; a manual start skips straight past it
- **captains / veto** — match running (coin toss → draft → veto → sides)
- **live** — teams set, maps and sides chosen, lobby posted
- **done** — match ended (`/match end`)

---

## 10. Admin operations

- **Bans:** `/admin ban`, `/admin unban`, `/admin bans` (or panel → Bans). A ban
  blocks the player from registering for any future custom in the server.
- **Maps:** `/maps seed|add|remove|toggle`. Disabled maps can't be put in a pool.
  `/maps competitive` (or the panel) sets the ⭐ competitive pool — see §8.14.
- **Ownership:** `/custom transfer` reassigns a custom; the new owner must be an
  admin. Registrations and channels are untouched — the registration embed is
  redrawn and the new owner is notified (§8.15).
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
| Buttons do nothing after a restart | Registration and control-board buttons persist; in-flight coin toss / draft / veto / side views don't. Delete and recreate the custom. |
| `/panel tier:admin` is refused | The board is pinned to `ADMIN_PANEL_CHANNEL` (see §6) — run it in that channel, or clear the setting. |
| A board's embed looks stale | It redraws on every state change and on **🔄 Refresh**. If it never updates, the bot probably lost **View Channel**/**Read Message History** on that channel, or the board message was deleted — just run `/panel` again. |
| Veto seems stuck / won't advance | Old versions had no veto→live step. On the current build it auto-advances; a custom stuck from before must be `/custom delete`d and recreated. |
| `/match start` says "already in progress" | The custom is in captains/veto/live. Run `/custom delete` to reset, then start again. |
| "A ready check is running on Custom #N" | Wait it out, or press **Start** / **Force start** — either one cuts the check short and begins immediately. |
| The ready check keeps failing | Every starter must click ✅; silence counts as absent. Absent players are dropped and subs promoted, up to 3 rounds. Force start if you'd rather play short-handed. |
| A custom is stuck in `ready` | Only possible if the bot died mid-check; the next boot resets it to `full`/`registration` automatically. |
| Nobody was tagged by the ready check | The bot needs **Send Messages** in the custom's own channel, and the custom must still have one. |
| More people registered than seats | Expected: extras join the 🪑 waitlist as subs and only the first `team_size × 2` play. Subs move up automatically when a starter leaves. |
| The match stalls after the draft | The bot now says what failed in the channel and logs a traceback. The usual cause is team-VC creation — a **full customs category** (Discord caps a category at 50 channels) or missing **Manage Channels**. The veto continues anyway; clean out old custom channels. |
| Party code says "hasn't started a match yet" | It needs `/match start` first — the code lives on the match. |
| Players aren't moved into team VCs | The bot needs **Move Members** + a role above them, and **Server Members**/**Voice State** intents enabled. Players not in voice at start can't be pulled — they join the channel themselves. |
| Missing-column error on an old DB | On boot the bot adds any columns the models gained (`draft_mode`, `vc_a`/`vc_b`, `maps.competitive`, the match's side pick, …). If a DB predates that and still errors, delete `bot.db` (dev) or add the column by hand, e.g. `ALTER TABLE customs ADD COLUMN team_size INTEGER DEFAULT 5;`. |
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
- Schema is created on first boot, and each boot also **adds any columns the models
  have gained** since the DB was made (SQLite `ADD COLUMN`, non-destructive — old
  rows take the column default). Column *removals* and type changes are not handled:
  for production, adopt Alembic migrations rather than relying on auto-create.

---

## 14. Command index (A–Z)

`/admin audit` · `/admin ban` · `/admin bans` · `/admin grant` · `/admin revoke` ·
`/admin unban` · `/custom create` · `/custom delete` · `/custom leave` ·
`/custom list` · `/custom prune` · `/custom register` · `/custom transfer` ·
`/maps add` · `/maps competitive` · `/maps list` · `/maps remove` · `/maps seed` ·
`/maps toggle` · `/match end` · `/match forcestart` · `/match partycode` ·
`/match readycheck` · `/match result` · `/match start` · `/panel` · `/profile` ·
`/queue status` · `/register` · `/stats leaderboard` · `/stats me`
