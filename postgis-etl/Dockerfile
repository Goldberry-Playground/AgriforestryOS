# farmOS → PostGIS ETL service.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

COPY pyproject.toml README.md ./
RUN uv sync --no-dev || uv pip install --system "httpx>=0.27,<1" "psycopg[binary]>=3.1,<4"

COPY etl.py db.py extract.py farmos.py schema.sql ./

# Default: continuous 15-minute poll loop. Override CMD with --once for cron.
ENTRYPOINT ["uv", "run", "--no-dev", "python", "etl.py"]
