FROM python:3.12-slim

# Poetry installs straight into the image's interpreter (no virtualenv) — the
# container *is* the environment. The version is pinned so a rebuild resolves
# the same way as the poetry.lock was made.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    POETRY_VERSION=2.4.2 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1

WORKDIR /app

# System deps for building wheels (aiosqlite/SQLAlchemy have no issue without
# this, but keep build-essential out to stay slim — add it back if a future
# dependency needs to compile).
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && pip install "poetry==$POETRY_VERSION"

# Dependencies before code, so a code-only change reuses this cached layer
# instead of re-resolving everything.
COPY pyproject.toml poetry.lock ./
RUN poetry install --only main --no-root

COPY bot ./bot

# data/ is where sqlite lives (db_path=data/bot.db); mounted as a volume in
# compose so the database survives container recreation.
RUN mkdir -p /app/data

CMD ["python", "-m", "bot"]
