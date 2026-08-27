"""Async SQLAlchemy engine + session factory. SQLite tuned with WAL."""
from __future__ import annotations

import os

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from bot.config import settings
from bot.db.models import Base

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


def _literal_default(col) -> str | None:  # noqa: ANN001
    """SQL literal for a column's Python-side default, or None if it has none.

    Only scalars are usable in `ALTER TABLE ... ADD COLUMN`; callables (e.g.
    `_utcnow`) are skipped — the column is simply added nullable/empty.
    """
    d = getattr(col, "default", None)
    if d is None or getattr(d, "is_callable", False):
        return None
    arg = getattr(d, "arg", None)
    if isinstance(arg, bool):
        return "1" if arg else "0"
    if isinstance(arg, (int, float)):
        return str(arg)
    if isinstance(arg, str):
        escaped = arg.replace("'", "''")
        return f"'{escaped}'"
    return None


async def _add_missing_columns(conn) -> None:  # noqa: ANN001
    """Poor-man's migration: add columns the models gained since the DB was made.

    `create_all` only creates missing *tables*, so a bot upgraded in place would
    otherwise crash on every new column. SQLite's ADD COLUMN is cheap and
    non-destructive; existing rows get the column default (or NULL).
    """
    for table in Base.metadata.sorted_tables:
        rows = await conn.execute(text(f"PRAGMA table_info('{table.name}')"))
        existing = {r[1] for r in rows}
        if not existing:      # table didn't exist -> create_all just made it
            continue
        for col in table.columns:
            if col.name in existing:
                continue
            ddl = f"ALTER TABLE {table.name} ADD COLUMN {col.name} " \
                  f"{col.type.compile(engine.dialect)}"
            default = _literal_default(col)
            if default is not None:
                ddl += f" DEFAULT {default}"
            await conn.execute(text(ddl))


async def init_db() -> None:
    """Create tables on first boot, then patch in any new columns.
    (Use Alembic in production.)"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _add_missing_columns(conn)
        # ensure pragmas applied on this connection too
        await conn.execute(text("PRAGMA journal_mode=WAL"))
