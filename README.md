# ValBot

A Discord bot for running Valorant custom matches: registration, team drafting, map veto, ready checks, and staff control panels.

## Requirements

- Docker and Docker Compose (recommended), **or** Python 3.12+ if running locally
- A Discord bot application and token — [Discord Developer Portal](https://discord.com/developers/applications)
- Enable the **Server Members Intent** for the bot in the portal (Bot → Privileged Gateway Intents). The bot also needs `Manage Roles`/`Move Members` permissions in your server to run customs.

## Configuration

All configuration is via environment variables, loaded from a `.env` file.

1. Copy the example file and fill in your values:

   ```bash
   cp .env.example .env
   ```

2. At minimum, set `DISCORD_TOKEN`. Everything else in `.env.example` is optional and documented inline (role IDs, channel restrictions, timers, timezone offset, HenrikDev API key).

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

```bash
python -m venv .venv
source .venv/bin/activate    # .venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env         # then edit .env
python -m bot
```

The bot reads `DB_PATH` relative to its own working directory, so run it from the project root (this is what makes it portable to panel hosts like Pterodactyl, where the working directory isn't `/app`).

## Development

Run the test suite with:

```bash
pip install pytest
pytest
```

## Notes

- `GUILD_ID` — set this during development to sync slash commands instantly to one server. Leave it blank in production; global sync can take up to an hour to propagate but works across every server the bot is in.
- The SQLite database lives at `data/bot.db` by default. Back up the `data/` directory to preserve registrations, match history, and rankings.
