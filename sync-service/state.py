"""
Sync cursor persistence.

Stores the high-water mark (latest Odoo move-line date processed) so each
poll only fetches new moves. A simple JSON file — the sync is low-frequency
(15 min) and single-writer, so this needs no database.
"""
from __future__ import annotations

import json
from pathlib import Path


class SyncState:
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def load_cursor(self) -> str | None:
        """Return the last-processed move date (ISO8601), or None on first run."""
        if not self._path.exists():
            return None
        try:
            return json.loads(self._path.read_text()).get("cursor")
        except (json.JSONDecodeError, OSError):
            return None

    def save_cursor(self, cursor: str) -> None:
        """Persist the high-water mark atomically (write-temp-then-replace)."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(json.dumps({"cursor": cursor}))
        tmp.replace(self._path)
