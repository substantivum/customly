FROM python:3.12-slim

WORKDIR /app

# System deps for building wheels (aiosqlite/SQLAlchemy have no issue without
# this, but keep build-essential out to stay slim — add it back if a future
# dependency needs to compile).
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot ./bot
COPY alembic ./alembic
COPY alembic.ini .

# data/ is where sqlite lives (db_path=data/bot.db); mounted as a volume in
# compose so the database survives container recreation.
RUN mkdir -p /app/data

CMD ["python", "-m", "bot"]
