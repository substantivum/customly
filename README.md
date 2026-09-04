# Customly

A Discord bot for running custom matches in **Valorant, CS2 and Dota 2**: registration, ready checks, coin toss, team drafting, map veto, a match lobby with map pictures, per-game ranks, and staff control panels — all localised in English and Russian.

## Requirements

- Docker and Docker Compose (recommended), **or** Python 3.12+ with [Poetry](https://python-poetry.org/) if running locally
- A Discord bot application and token — [Discord Developer Portal](https://discord.com/developers/applications)
- Enable the **Server Members Intent** for the bot in the portal (Bot → Privileged Gateway Intents). The bot also needs `Manage Roles`/`Move Members` permissions in your server to run customs.

## Configuration

All configuration is via environment variables, loaded from a `.env` file.

1. Copy the example file and fill in your values:

   ```bash
   cp .env.example .env
   ```

2. At minimum, set `DISCORD_TOKEN`. Everything else in `.env.example` is optional and documented inline — role IDs, channel restrictions, timers, timezone offset — with three API keys for ranks:

   | Key | Game | Needed? |
   |-----|------|---------|
   | `HENRIK_API_KEY` | Valorant | Optional — works without it at a lower rate limit |
   | `FACEIT_API_KEY` | CS2 | **Required for CS2 rank** — Faceit rejects unauthenticated calls. Get one at [developers.faceit.com](https://developers.faceit.com/apps) (a personal account is enough) |
   | `OPENDOTA_API_KEY` | Dota 2 | Optional — the free tier works, a key only raises the rate limit |

## Deploy with Docker Compose

```bash
docker compose up -d --build
```

This builds the image, starts the bot in the background, and persists the SQLite database to `./data` on the host (mounted into `/app/data` in the container) — the database survives rebuilds and restarts.

Useful commands:

```bash
docker compose logs -f       # tail bot logs
docker compose restart       # restart after changing .env
docker compose down          # stop and remove the container (data/ is untouched)
docker compose up -d --build # rebuild after pulling code changes
```

## Deploy without Docker

Dependencies are managed with [Poetry](https://python-poetry.org/) (`pipx install poetry`).

```bash
poetry install --only main    # creates a virtualenv and installs the runtime deps
cp .env.example .env          # then edit .env
poetry run python -m bot
```

The bot reads `DB_PATH` relative to its own working directory, so run it from the project root (this is what makes it portable to panel hosts like Pterodactyl, where the working directory isn't `/app`).

## The three games

Every game shares the same flow — registration → ready check → coin toss → draft → lobby — with a few per-game differences:

| | Valorant | CS2 | Dota 2 |
|---|---|---|---|
| Formats | BO1 / BO3 / BO5 | BO1 only | BO1 only |
| Map veto | Yes, with an attack/defence side pick | Yes (side decided by knife round in-game) | None — straight from the draft to the lobby |
| Connect info | Party code | Server IP | Lobby name + password |

Each game has its own colour and marker (🟥 Valorant, 🟨 CS2, 🟧 Dota 2). Any embed about a specific game's custom or match wears that game's colour; the boards and staff screens keep the neutral brand colour.

## Ranks and identities

Ranks work the same way in every game: a player submits an identity, an admin approves it (there is no OAuth that proves a Discord user owns a game account, so a human is the trust step), then the bot fetches the rank and keeps it fresh.

| Game | Command | Identity | Rank source |
|------|---------|----------|-------------|
| Valorant | `/register <Riot ID>` | `Name#TAG` | HenrikDev — current rank, RR, peak |
| CS2 | `/register_cs2 <Faceit nickname>` | Faceit nickname (exact, case-sensitive) | Faceit — skill level + elo |
| Dota 2 | `/register_dota <friend id>` | In-game Friend ID (a number) | OpenDota — rank medal (match data must be public) |

Pending submissions appear in the **Rank approvals** queue on the Admin and Super Admin panels, and the panels show how many are waiting. Once approved, the rank shows on `/profile` and feeds captain selection: the `highest_rr` / `highest_peak` captain methods use the right metric for the game being played (RR in Valorant, elo in CS2, medal in Dota 2). Players without an approved rank simply aren't eligible for rank-based captaincy.

Other profile commands: `/profile` (one card for all three games), `/setmain` (your main game — it colours the card), `/link` (a clickable Steam handle), `/unlink`, `/refresh_rank`.

## Map pictures in the lobby

When the veto finishes, the lobby message shows a picture card for each map in play order, with the sides. Drop one image per map under `bot/assets/maps/<game>/<slug>.png` — see [bot/assets/maps/README.md](bot/assets/maps/README.md) for the naming rule. Maps without a picture fall back to a plain list; nothing breaks.

## Panels

`/panel` posts a live board that redraws itself whenever a custom changes:

| Command | Board | Who |
|---------|-------|-----|
| `/panel` | Player board — open games, browse & join | everyone |
| `/panel tier:admin` | Admin board — create/manage customs, per-game map pools, bans, rank approvals, audit | Admin+ |
| `/panel tier:superadmin` | Super board — bot roles, language, prune, rank approvals | SuperAdmin |

Set `ADMIN_PANEL_CHANNEL` / `SUPERADMIN_PANEL_CHANNEL` in `.env` and the staff boards refuse to be posted anywhere else. The Maps screen lets admins seed defaults, add, remove and toggle maps, and set the competitive pool — separately for each game. `/help` lists every slash command you can use, grouped by area; `/language` (SuperAdmin) switches the whole server between English and Russian.

## Development

Run the test suite with:

```bash
poetry install                # runtime + dev deps (pytest)
poetry run pytest
```

## Notes

- `GUILD_ID` — set this during development to sync slash commands instantly to one server. Leave it blank in production; global sync can take up to an hour to propagate but works across every server the bot is in.
- The SQLite database lives at `data/bot.db` by default. Back up the `data/` directory to preserve registrations, match history, and rankings.
- **Upgrading is safe.** On boot the bot creates any missing tables and adds any new columns to existing ones, so a rebuild against an older database just works — nothing is dropped or rewritten.
