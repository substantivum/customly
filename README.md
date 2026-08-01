# Valorant Customs & Tournament Bot

Discord bot for Valorant custom games — registration, scheduling, snake draft,
map veto, and automatic team voice channels. **Python · discord.py · SQLite · Docker.**
No Riot API / RSO: a Riot ID is just a display tag.

## Quick start

```bash
cp .env.example .env          # add DISCORD_TOKEN (+ GUILD_ID for instant sync)
docker compose up --build
```

Local (no Docker):

```bash
pip install -r requirements.txt
DISCORD_TOKEN=... GUILD_ID=... DB_PATH=./data/bot.db python -m bot
```

Tests (pure logic, no token needed):

```bash
DISCORD_TOKEN=x DB_PATH=/tmp/t.db pytest -q
```

### Discord setup
1. Create a bot at the Developer Portal; enable the **Server Members** and
   **Voice State** privileged intents.
2. Invite with `applications.commands` + `bot` scopes and permissions:
   Manage Channels, Move Members, Send Messages, Connect.
3. Create a category for customs and put its id in `CUSTOMS_CATEGORY_ID`;
   create a `#custom-config` channel and put its id in `CUSTOM_CONFIG_CHANNEL`.
4. Optional but recommended: put your organiser role's id in `ADMIN_ROLE` (and a
   `SUPERADMIN_ROLE` if you want one) — everyone holding that Discord role is
   treated as a bot admin, no per-person grant needed.
5. Create an admins-only and a superadmins-only channel and put their ids in
   `ADMIN_PANEL_CHANNEL` / `SUPERADMIN_PANEL_CHANNEL`; the staff boards then
   refuse to be posted anywhere else.
6. First boot: a guild admin runs `/maps seed`, then `/admin grant` to assign
   bot roles to anyone not covered by those Discord roles (guild
   owner/administrator is treated as superadmin automatically).
7. Post the boards: `/panel` in your public customs channel, and `/panel` in each
   of the two staff channels.

## Commands

| Command | Who | Notes |
|---|---|---|
| `/register riot_id` | player | tag only; rank/RR/peak optional |
| `/profile [member]` | player | |
| `/custom create name format start maps [team_size] [draft] [captains]` | admin (owner) | spawns `#<creator>-<name>`; team_size 1–5 (1v1…5v5); `maps:competitive` = current competitive pool; `draft` = snake or one-by-one; `captains` = random / highest_rr / highest_peak |
| `/custom register \| leave \| list` | player | overlap-checked registration |
| `/custom transfer <id> to:@user` | owner / superadmin | reassigns ownership; redraws the embed + DMs the new owner |
| `/custom delete <id> [force]` | owner / superadmin | occupancy guard; `force` = superadmin |
| `/custom prune [force]` | superadmin | deletes all customs |
| `/queue status <id>` | player | |
| `/match readycheck <id>` | owner / superadmin | posts a ready check now; auto-fires anyway when the last seat fills |
| `/match start <id> [captains] [captain_a] [captain_b]` | owner / superadmin | needs a full queue; cuts short a running ready check. `captains` overrides the custom's method for this start only |
| `/match forcestart <id> [captains] [captain_a] [captain_b]` | owner / superadmin | manual start with current players (even, ≥2) |
| `/match partycode <id> code` | any registered player | posts the party code openly |
| `/admin ban member [reason]` / `/admin unban member` / `/admin bans` | admin | block from future games |
| `/panel [tier]` | tier-gated | posts a live control board — 🎮 Customs / 🛡 Admin / 👑 Super Admin — one per channel |
| `/match result <id> map a b` | captain / admin | records a map score |
| `/maps list \| seed \| add \| remove \| toggle` | admin | |
| `/maps competitive [maps]` | admin | sets the current competitive pool (blank clears it) |
| `/admin grant \| revoke \| audit` | superadmin / admin | |
| `/stats me \| leaderboard` | player | |

## How the core flow works

1. **Create** — admin runs `/custom create` in `#custom-config`. Bot derives the
   time block (`BO1=1h / BO3=3h / BO5=5h`), creates the custom + its queue, and
   spawns a dedicated `#<creator>-<name>` text channel with a registration embed
   (Register / Leave buttons).
2. **Register** — players register (button or `/custom register`). A player may
   hold many customs **as long as their `[start, start+duration)` blocks don't
   overlap**; a clash is rejected and names the conflicting custom. A custom has
   `team_size × 2` seats: sign-ups past that join the **waitlist** as subs and are
   promoted in join order the moment a starter leaves. Only starters play.
3. **Ready check** — the moment the last seat fills, the bot posts a ready check in
   the custom's channel **tagging every starter**. All of them must hit ✅ within
   `READY_CHECK_SECONDS` (default 120); it resolves early once everyone has
   answered. If some don't, they **lose their seat**, waitlisted subs are promoted
   and a fresh round runs — up to 3 rounds, after which the custom drops back to
   registration. An owner/admin can post one any time with `/match readycheck`.
4. **Start** — a passed ready check starts the match on its own. An owner can also
   run `/match start` (every seat filled) or `/match forcestart` (current
   registrants — must be even and ≥2), either of which **cuts a running ready check
   short**. Both cap the match at `team_size × 2` and announce anyone extra as a
   sub. Captains are chosen by the method **set on the custom at creation**
   (`random` / `highest_rr` / `highest_peak`); `/match start captains:` overrides it
   for one start and is the only place `manual` (`captain_a`/`captain_b`) lives.
   **Team size is set per custom (1v1 … 5v5).**
5. **Coin toss** — a random captain calls heads or tails; the toss winner then
   takes **first or second pick**, which opens the draft on their side.
6. **Draft** — a player Select, turn-gated, in the custom's chosen mode:
   **snake** (A, BB, AA, …) or **one by one** (A, B, A, B, …). Both are set at
   creation. A per-turn timer auto-picks if a captain stalls.
7. **Veto** — uses the **custom's** map pool. BO1 alternates bans to one;
   BO3/BO5 follow ban/ban/pick…/decider. Buttons per remaining map, turn-gated.
8. **Sides** — veto done, the team that did **not** make the last ban picks
   **attack or defence** on the decider; it lands in the lobby embed.
9. **Voice** — when veto starts the bot creates `<custom>-a-<captain>` /
   `<custom>-b-<captain>` (e.g. `friday-5v5-a-salta`)
   under the Customs category and **moves already-connected players** in. The
   channels are **open to everyone**, so friends and observers just join. Players
   are moved **once, at game start** only — afterwards they can leave and rejoin
   freely. Discord can't pull someone who isn't in voice; those players simply
   join the channel themselves.
10. **Lobby** — sides chosen, the bot posts the match lobby in the custom's channel
   with **Set party code** and **End custom** buttons. Any registered player can
   use them; setting the code updates the lobby embed in place.
11. **End** — ending marks the match completed and deletes the custom's team VCs
   **and** its text channel.
12. **Delete/prune guard** — teardown is blocked while **both** team VCs are
   occupied (game in progress). Superadmin can `force`, which disconnects
   members first.

## Implemented vs stubbed

**Fully wired:** identity/registration, customs (create + dedicated channel),
overlap scheduling, queue fill, ownership + transfer (embed redraw + owner DM),
delete/prune with the occupancy guard, captain selection, coin toss for pick
order, snake **or** one-by-one draft, BO1/3/5 veto, attack/defence side pick,
team-VC creation + one-time auto-move, party code (open to all), player bans,
maps incl. the competitive pool, roles/permissions, audit log, the three live
control boards, the ready check (auto on full, drop-and-refill on failure), Docker.

**Stubbed (schema + hooks exist, logic minimal):** tournaments (single/double
elim, round robin, swiss) and brackets; stats accrual on results, Elo updates,
MVP voting, predictions, achievements, seasons/leaderboard depth; the
substitute view. These are intentionally left as extension points.

Because personal scores aren't finished, **profiles, stats and leaderboards are
kept off the control boards** — the boards are a lobby tool and show only what a
game needs. `/register`, `/profile` and `/stats` still work for anyone who wants
them, and re-adding the buttons is a small change once the feature lands.

## Notes
- SQLite runs in WAL mode; **run a single bot instance** (single writer). For
  horizontal scale, migrate to Postgres — the SQLAlchemy layer keeps the swap cheap.
- Schema is created via `create_all` on boot. For production, switch to Alembic
  migrations.
