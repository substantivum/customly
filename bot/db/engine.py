"""Async SQLAlchemy engine + session factory. SQLite tuned with WAL."""
from __future__ import annotations

import asyncio
import os
import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from bot.config import settings

REPO_ROOT = Path(__file__).resolve().parents[2]
# alembic/versions/2fe3e291e473_baseline.py — the schema as it stood the moment
# Alembic was adopted, i.e. exactly what the old create_all-based bootstrap
# already produces on every deployment that predates this file.
BASELINE_REVISION = "2fe3e291e473"

# Ensure the data dir exists (sqlite file lives on the mounted volume).
# abspath() so a bare `bot.db` still yields a directory to check.
_db_dir = os.path.dirname(os.path.abspath(settings.db_path))
try:
    os.makedirs(_db_dir, exist_ok=True)
except OSError as e:
    # This runs at import, so a bare OSError here kills the bot with a traceback
    # that says nothing about the actual mistake — which is nearly always a
    # DB_PATH copied from the Docker layout onto a host that doesn't have it.
    raise RuntimeError(
        f"Can't create the database directory {_db_dir!r}: {e.strerror}.\n"
        f"DB_PATH is currently {settings.db_path!r}.\n"
        f"Use a path relative to the bot's own folder — DB_PATH=data/bot.db — "
        f"which works both in Docker and on a panel host. An absolute "
        f"/app/... path exists only inside the Docker image."
    ) from e

engine = create_async_engine(settings.db_url, echo=False, future=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


@event.listens_for(engine.sync_engine, "connect")
def _set_sqlite_pragmas(dbapi_conn, _record):  # noqa: ANN001
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA busy_timeout=5000")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.close()


def _existing_tables() -> set[str]:
    if not os.path.exists(settings.db_path):
        return set()
    conn = sqlite3.connect(settings.db_path)
    try:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        return {r[0] for r in rows}
    finally:
        conn.close()


def _run_migrations() -> None:
    """Bring the schema up to date via Alembic (alembic/versions/).

    Runs on the plain sync sqlite3 driver, same as alembic/env.py — schema DDL
    doesn't need asyncio, and pysqlite is stdlib. Blocking, so the caller runs
    it off the event loop; a boot-time schema check is quick enough that a
    dedicated migration step before start isn't needed.
    """
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))

    tables = _existing_tables()
    if tables and "alembic_version" not in tables:
        # A deployment that predates Alembic: the old create_all-based
        # bootstrap already built this exact schema (baseline is a faithful
        # snapshot of it), so mark it there directly instead of replaying
        # baseline's create_table calls against tables that already exist.
        command.stamp(cfg, BASELINE_REVISION)

    command.upgrade(cfg, "head")


async def init_db() -> None:
    """Bring the schema up to date, then apply pragmas to this connection."""
    await asyncio.to_thread(_run_migrations)
    async with engine.begin() as conn:
        await conn.execute(text("PRAGMA journal_mode=WAL"))
