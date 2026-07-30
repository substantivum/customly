"""Environment-backed settings."""
from __future__ import annotations

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    discord_token: str
    db_path: str = "/app/data/bot.db"
    customs_category_id: int | None = None      # optional default
    custom_config_channel: int | None = None    # #custom-config id
    default_voice_channel: int | None = None     # where players go when a match ends
    guild_id: int | None = None                 # if set, sync commands to this guild fast

    # Discord roles that map onto bot roles. Holding the role is equivalent to
    # having been granted the bot role via /admin grant — no DB row needed.
    admin_role: int | None = None               # ADMIN_ROLE — grants bot "admin"
    superadmin_role: int | None = None          # SUPERADMIN_ROLE — grants bot "superadmin"

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
