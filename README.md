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
5. First boot: a guild admin runs `/maps seed`, then `/admin grant` to assign
   bot roles to anyone not covered by those Discord roles (guild
   owner/administrator is treated as superadmin automatically).

## Commands

| Command | Who | Notes |
|---|---|---|
| `/register riot_id` | player | tag only; rank/RR/peak optional |
| `/profile [member]` | player | |
| `/custom create name format start maps [team_size]` | admin (owner) | spawns `#<creator>-<name>`; team_size 1–5 (1v1…5v5) |
| `/custom register \| leave \| list` | player | overlap-checked registration |
| `/custom transfer <id> to:@user` | owner / superadmin | reassigns ownership |
| `/custom delete <id> [force]` | owner / superadmin | occupancy guard; `force` = superadmin |
| `/custom prune [force]` | superadmin | deletes all customs |
| `/queue status <id>` | player | |
| `/match start <id> [captains] [captain_a] [captain_b]` | owner / superadmin | needs a full queue |
| `/match forcestart <id> [captains] [captain_a] [captain_b]` | owner / superadmin | manual start with current players (even, ≥4) |
| `/match partycode <id> code` | any registered player | posts the party code openly |
| `/admin ban member [reason]` / `/admin unban member` / `/admin bans` | admin | block from future games |
| `/panel` | everyone | button hub: Customs / Admin panel / Super Admin |
| `/match result <id> map a b` | captain / admin | records a map score |
| `/maps list \| seed \| add \| remove \| toggle` | admin | |
| `/admin grant \| revoke \| audit` | superadmin / admin | |
| `/stats me \| leaderboard` | player | |

## How the core flow works

1. **Create** — admin runs `/custom create` in `#custom-config`. Bot derives the
   time block (`BO1=1h / BO3=3h / BO5=5h`), creates the custom + its queue, and
   spawns a dedicated `#<creator>-<name>` text channel with a registration embed
   (Register / Leave buttons).
2. **Register** — players register (button or `/custom register`). A player may
   hold many customs **as long as their `[start, start+duration)` blocks don't
   overlap**; a clash is rejected and names the conflicting custom.
3. **Start** — owner runs `/match start` (full queue) or `/match forcestart`
   (manual start with the current registrants — must be even and ≥4). Captains
   are chosen by `random` / `manual` (pass `captain_a`/`captain_b`) /
   `highest_rr` / `highest_peak`, then a **snake draft** (A, BB, AA, …) runs via
   a player Select. **Team size is set per custom (2v2 … 5v5).**
4. **Veto** — uses the **custom's** map pool. BO1 alternates bans to one;
   BO3/BO5 follow ban/ban/pick…/decider. Buttons per remaining map, turn-gated.
5. **Voice** — when veto starts the bot creates `team_a_<id>` / `team_b_<id>`
   under the Customs category and **moves already-connected players** in. The
   channels are **open to everyone**, so friends and observers just join. Players
   are moved **once, at game start** only — afterwards they can leave and rejoin
   freely. Discord can't pull someone who isn't in voice; those players simply
   join the channel themselves.
6. **Lobby** — veto done, the bot posts the match lobby in the custom's channel
   with **Set party code** and **End custom** buttons. Any registered player can
   use them; setting the code updates the lobby embed in place.
7. **End** — ending marks the match completed and deletes the custom's team VCs
   **and** its text channel.
8. **Delete/prune guard** — teardown is blocked while **both** team VCs are
   occupied (game in progress). Superadmin can `force`, which disconnects
   members first.

## Implemented vs stubbed

**Fully wired:** identity/registration, customs (create + dedicated channel),
overlap scheduling, queue fill, ownership + transfer, delete/prune with the
occupancy guard, captain selection, snake draft, BO1/3/5 veto, team-VC creation
+ one-time auto-move, party code (open to all), player bans, maps, roles/permissions, audit log, Docker.

**Stubbed (schema + hooks exist, logic minimal):** tournaments (single/double
elim, round robin, swiss) and brackets; stats accrual on results, Elo updates,
MVP voting, predictions, achievements, seasons/leaderboard depth; draft/veto
auto-pick-on-timeout timers (APScheduler is started; jobs are TODO); substitute
and ready-check views. These are intentionally left as extension points.

## Notes
- SQLite runs in WAL mode; **run a single bot instance** (single writer). For
  horizontal scale, migrate to Postgres — the SQLAlchemy layer keeps the swap cheap.
- Schema is created via `create_all` on boot. For production, switch to Alembic
  migrations.
