# Odoo ↔ farmOS sync service.
# Uses the official uv image for fast, reproducible dependency installs.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# Install dependencies first (layer-cached on lockfile/manifest changes only).
COPY pyproject.toml ./
COPY README.md ./
RUN uv sync --no-dev || uv pip install --system "httpx>=0.27,<1"

# Application code.
COPY mapping.py odoo_client.py farmos_writer.py state.py sync.py harvest_sync.py ./

# Cursor state lives on a mounted volume so it survives restarts.
VOLUME ["/data"]
ENV SYNC_STATE_FILE=/data/sync_state.json

# Default: continuous 15-minute poll loop. Override CMD with --once for cron.
ENTRYPOINT ["uv", "run", "--no-dev", "python", "sync.py"]
