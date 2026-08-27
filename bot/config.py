"""Environment-backed settings."""
from __future__ import annotations

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    discord_token: str
    # Relative to the bot's working directory on purpose: under Docker that's
    # /app (so this is the mounted /app/data volume), and on a panel host
    # (bot-hosting, Pterodactyl) it's /home/container — where an absolute
    # /app/... path doesn't exist and the filesystem is read-only.
    db_path: str = "data/bot.db"
    customs_category_id: int | None = None      # optional default
    custom_config_channel: int | None = None    # #custom-config id
    default_voice_channel: int | None = None     # where players go when a match ends
    guild_id: int | None = None                 # if set, sync commands to this guild fast

    # Discord roles that map onto bot roles. Holding the role is equivalent to
    # having been granted the bot role via /admin grant — no DB row needed.
    admin_role: int | None = None               # ADMIN_ROLE — grants bot "admin"
    superadmin_role: int | None = None          # SUPERADMIN_ROLE — grants bot "superadmin"

    # Where each staff board may be posted. Set these to the ids of your
    # (privately-permissioned) staff channels and `/panel tier:admin` refuses to
    # post anywhere else — the board can't be leaked into a public channel by a
    # mis-click. Leave blank and the tier may be posted anywhere.
    admin_panel_channel: int | None = None      # ADMIN_PANEL_CHANNEL
    superadmin_panel_channel: int | None = None  # SUPERADMIN_PANEL_CHANNEL

    # HenrikDev Valorant API (https://docs.henrikdev.xyz) — used to verify
    # Riot IDs and fetch current/peak rank in /register. Unset still works
    # (unauthenticated, lower rate limit); set it for the higher tier.
    henrik_api_key: str | None = None

    # Server-local time. Discord exposes no per-user timezone, so a bare `HH:MM`
    # start time is read in this zone: 6 = UTC+6 (Bishkek), -5 = UTC-5.
    tz_offset: int = 0

    # Behavior knobs
    draft_pick_seconds: int = 30
    veto_pick_seconds: int = 30
    ready_check_seconds: int = 120

    @field_validator(
        "customs_category_id", "custom_config_channel", "default_voice_channel",
        "guild_id", "admin_role", "superadmin_role",
        "admin_panel_channel", "superadmin_panel_channel",
        mode="before",
    )
    @classmethod
    def _blank_is_none(cls, v):
        """`.env.example` ships these keys blank; an empty string is 'unset',
        not a validation error."""
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @property
    def db_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.db_path}"


settings = Settings()  # type: ignore[call-arg]
