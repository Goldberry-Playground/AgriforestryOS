"""
Database backup service for AgriforestryOS (Sprint 7, production readiness).

Logical backups of the two stateful Postgres databases — the farmOS operational
DB (the irreplaceable system of record) and the PostGIS spatial mirror — written
to a local directory AND pushed to S3-compatible object storage (DigitalOcean
Spaces). Retention is pruned independently in both places.

The PostGIS mirror is reproducible from farmOS via the ETL, but backing it up is
cheap and saves a full re-extract; the farmOS DB has no upstream and MUST be
recoverable.

Design mirrors the rest of the repo: pure, unit-tested transforms (filename
layout, retention planning, S3 keys) with the actual I/O (pg_dump subprocess,
filesystem, boto3) behind thin injected adapters that are faked in tests. If
Spaces credentials are absent the service degrades to local-only and says so —
it never silently skips the backup.

Two modes:
  python backup.py --once                 # one pass, then exit (cron / pre-migrate)
  python backup.py                         # loop every BACKUP_INTERVAL_SECONDS
  python backup.py --once --reason premigrate   # tag a snapshot before drush updb
"""
from __future__ import annotations

import argparse
import datetime as _dt
import logging
import os
import subprocess
import time
from pathlib import Path

log = logging.getLogger("backup")

# pg_dump custom format (-Fc): already compressed, and pg_restore can do
# selective / --clean restores from it. Hence the `.dump` extension (not .sql.gz).
_EXT = ".dump"


class BackupError(RuntimeError):
    """Raised when a dump or a required upload fails."""


# ---------------------------------------------------------------------------
# Pure transforms (no I/O) — unit-tested
# ---------------------------------------------------------------------------

def _safe_ts(ts: str) -> str:
    """Normalize an ISO-8601 UTC timestamp into a filesystem/S3-safe, sortable
    token: '2026-06-16T03:00:00+00:00' -> '2026-06-16T030000Z'.

    Colons are stripped (illegal on some filesystems) but the layout stays
    lexically sortable, so 'keep the newest N' is just a sort-and-slice.
    """
    base = ts.split("+", 1)[0].rstrip("Z")
    return base.replace(":", "") + "Z"


def dump_filename(db_label: str, ts: str, reason: str = "routine") -> str:
    """e.g. 'farmos__routine__2026-06-16T030000Z.dump'.

    `db_label` groups backups for retention; `reason` distinguishes scheduled
    runs from one-off snapshots (e.g. 'premigrate') in the name.
    """
    return f"{db_label}__{reason}__{_safe_ts(ts)}{_EXT}"


def db_label_of(filename: str) -> str:
    """The retention group of a dump filename (text before the first '__')."""
    return filename.split("__", 1)[0]


def prune_plan(names: list[str], keep: int) -> list[str]:
    """Return the dump names to delete: all but the newest `keep` per db_label.

    Grouping by db_label means farmOS and postgis retain `keep` each. `keep <= 0`
    is treated as 'never prune' — a deliberately safe default so a misconfigured
    env var can never wipe history.
    """
    if keep <= 0:
        return []
    groups: dict[str, list[str]] = {}
    for name in names:
        if name.endswith(_EXT):
            groups.setdefault(db_label_of(name), []).append(name)
    doomed: list[str] = []
    for group in groups.values():
        ordered = sorted(group)  # lexical order == chronological (see _safe_ts)
        doomed.extend(ordered[:-keep])
    return doomed


def s3_key(prefix: str, filename: str) -> str:
    prefix = prefix.strip("/")
    return f"{prefix}/{filename}" if prefix else filename


def _utcnow_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

class BackupService:
    """Dump each configured DB → local store → (optional) object store → prune.

    Adapters are duck-typed for easy faking:
      dumper.dump(db) -> bytes
      local.write(name, data) / local.list() -> [name] / local.delete(name)
      remote.put(key, data) / remote.list(prefix) -> [key] / remote.delete(key)
    """

    def __init__(self, dumper, local, remote, databases, *,
                 keep: int = 14, s3_prefix: str = "agriforestryos/backups",
                 clock=_utcnow_iso) -> None:
        self._dumper = dumper
        self._local = local
        self._remote = remote          # None => local-only mode
        self._databases = databases    # list of dicts: {label, host, port, user, password, name}
        self._keep = keep
        self._prefix = s3_prefix
        self._clock = clock

    def run_once(self, reason: str = "routine") -> dict:
        ts = self._clock()
        counts = {"dumped": 0, "uploaded": 0, "pruned_local": 0,
                  "pruned_remote": 0, "failed": 0}

        for db in self._databases:
            try:
                data = self._dumper.dump(db)
            except Exception:  # noqa: BLE001 — one DB failing must not abort the rest
                log.exception("pg_dump failed for %s — skipping", db["label"])
                counts["failed"] += 1
                continue
            name = dump_filename(db["label"], ts, reason)
            self._local.write(name, data)
            counts["dumped"] += 1
            log.info("backed up %s -> %s (%d bytes)", db["label"], name, len(data))
            if self._remote is not None:
                self._remote.put(s3_key(self._prefix, name), data)
                counts["uploaded"] += 1

        self._prune(counts)
        log.info("backup pass: %s", counts)
        return counts

    def _prune(self, counts: dict) -> None:
        for name in prune_plan(self._local.list(), self._keep):
            self._local.delete(name)
            counts["pruned_local"] += 1
        if self._remote is None:
            return
        keys = self._remote.list(self._prefix)
        by_name = {k.rsplit("/", 1)[-1]: k for k in keys}
        for name in prune_plan(list(by_name), self._keep):
            self._remote.delete(by_name[name])
            counts["pruned_remote"] += 1


# ---------------------------------------------------------------------------
# Real I/O adapters
# ---------------------------------------------------------------------------

class PgDumper:
    """Runs `pg_dump -Fc` against a database over the docker network."""

    def dump(self, db: dict) -> bytes:
        cmd = [
            "pg_dump", "-h", db["host"], "-p", str(db.get("port", 5432)),
            "-U", db["user"], "-d", db["name"],
            "-Fc", "--no-owner", "--no-privileges",
        ]
        proc = subprocess.run(  # noqa: S603 — fixed argv, no shell
            cmd, capture_output=True,
            env={**os.environ, "PGPASSWORD": db["password"]},
        )
        if proc.returncode != 0:
            raise BackupError(
                f"pg_dump {db['label']} failed (exit {proc.returncode}): "
                f"{proc.stderr.decode(errors='replace')[:300]}"
            )
        return proc.stdout


class LocalStore:
    def __init__(self, directory: str | os.PathLike) -> None:
        self._dir = Path(directory)
        self._dir.mkdir(parents=True, exist_ok=True)

    def write(self, name: str, data: bytes) -> None:
        (self._dir / name).write_bytes(data)

    def list(self) -> list[str]:
        return [p.name for p in self._dir.glob(f"*{_EXT}")]

    def delete(self, name: str) -> None:
        (self._dir / name).unlink(missing_ok=True)

    def read(self, name: str) -> bytes:
        return (self._dir / name).read_bytes()


class S3Store:
    """DigitalOcean Spaces (S3-compatible) object store via boto3."""

    def __init__(self, bucket: str, endpoint: str, region: str,
                 key: str, secret: str) -> None:
        import boto3  # imported lazily so local-only mode needs no boto3

        self._bucket = bucket
        self._client = boto3.client(
            "s3", endpoint_url=endpoint, region_name=region,
            aws_access_key_id=key, aws_secret_access_key=secret,
        )

    def put(self, key: str, data: bytes) -> None:
        self._client.put_object(Bucket=self._bucket, Key=key, Body=data)

    def list(self, prefix: str) -> list[str]:
        keys: list[str] = []
        token: str | None = None
        while True:
            kwargs = {"Bucket": self._bucket, "Prefix": prefix}
            if token:
                kwargs["ContinuationToken"] = token
            resp = self._client.list_objects_v2(**kwargs)
            keys.extend(o["Key"] for o in resp.get("Contents", []))
            if not resp.get("IsTruncated"):
                return keys
            token = resp.get("NextContinuationToken")


# ---------------------------------------------------------------------------
# Wiring + entrypoint
# ---------------------------------------------------------------------------

def _databases_from_env() -> list[dict]:
    """Build the DB list from the same env the compose stack already passes."""
    dbs = [{
        "label": "farmos",
        "host": os.environ.get("FARMOS_DB_HOST", "db"),
        "port": int(os.environ.get("FARMOS_DB_PORT", "5432")),
        "user": os.environ["FARMOS_DB_USER"],
        "password": os.environ["FARMOS_DB_PASSWORD"],
        "name": os.environ["FARMOS_DB_NAME"],
    }]
    if os.environ.get("POSTGIS_DB"):
        dbs.append({
            "label": "postgis",
            "host": os.environ.get("POSTGIS_HOST", "postgis"),
            "port": int(os.environ.get("POSTGIS_PORT", "5432")),
            "user": os.environ["POSTGIS_USER"],
            "password": os.environ["POSTGIS_PASSWORD"],
            "name": os.environ["POSTGIS_DB"],
        })
    return dbs


def _remote_from_env() -> S3Store | None:
    bucket = os.environ.get("SPACES_BUCKET")
    key = os.environ.get("SPACES_KEY")
    secret = os.environ.get("SPACES_SECRET")
    if not all([bucket, key, secret]):
        log.warning("Spaces not configured (SPACES_BUCKET/KEY/SECRET) — "
                    "running LOCAL-ONLY. Off-droplet copies are disabled.")
        return None
    return S3Store(
        bucket=bucket,
        endpoint=os.environ.get("SPACES_ENDPOINT", "https://nyc3.digitaloceanspaces.com"),
        region=os.environ.get("SPACES_REGION", "nyc3"),
        key=key, secret=secret,
    )


def build_service_from_env() -> BackupService:
    return BackupService(
        dumper=PgDumper(),
        local=LocalStore(os.environ.get("BACKUP_DIR", "/backups")),
        remote=_remote_from_env(),
        databases=_databases_from_env(),
        keep=int(os.environ.get("BACKUP_KEEP", "14")),
        s3_prefix=os.environ.get("BACKUP_S3_PREFIX", "agriforestryos/backups"),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="AgriforestryOS database backups.")
    parser.add_argument("--once", action="store_true", help="Single pass then exit.")
    parser.add_argument("--reason", default="routine",
                        help="Tag for the dump filename (e.g. 'premigrate').")
    parser.add_argument("--interval", type=int,
                        default=int(os.environ.get("BACKUP_INTERVAL_SECONDS", "86400")))
    args = parser.parse_args()
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    service = build_service_from_env()
    if args.once:
        service.run_once(reason=args.reason)
        return
    log.info("starting backup loop (every %ds)", args.interval)
    while True:
        try:
            service.run_once()
        except Exception:  # noqa: BLE001
            log.exception("backup pass failed; retry next interval")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
