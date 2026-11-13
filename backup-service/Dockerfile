# Database backup/restore service.
# Needs the Postgres 17 client (pg_dump/pg_restore) plus a small Python runtime.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# Postgres 17 client tools from the official PGDG apt repo. A v17 client dumps
# both our databases fine (the PostGIS mirror is PG16 — newer client, older
# server is supported).
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl gnupg \
 && install -d /usr/share/postgresql-common/pgdg \
 && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
      -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
 && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" \
      > /etc/apt/sources.list.d/pgdg.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends postgresql-client-17 \
 && rm -rf /var/lib/apt/lists/*

# Dependencies first (layer-cached on manifest changes only).
COPY pyproject.toml README.md ./
RUN uv sync --no-dev || uv pip install --system "boto3>=1.34,<2"

COPY backup.py restore.py ./

# Local dumps live on a mounted volume so they survive restarts.
VOLUME ["/backups"]
ENV BACKUP_DIR=/backups

# Default: daily backup loop. Override with `--once [--reason premigrate]`.
ENTRYPOINT ["uv", "run", "--no-dev", "python", "backup.py"]
