"""
Restore a database from a backup dump (operator tool, run manually).

The reverse of backup.py: take a pg_dump custom-format `.dump` (from the local
backup volume or pulled from Spaces) and load it into a target database with
`pg_restore --clean --if-exists`.

This is intentionally a manual, deliberate operation — restoring overwrites the
target DB's objects. It is never run automatically.

Usage (inside the backup container, or any box with pg_restore + network):
  python restore.py --db farmos --file /backups/farmos__routine__...dump
  python restore.py --db farmos --from-s3 agriforestryos/backups/farmos__...dump
  python restore.py --list                 # show local + (if configured) remote dumps
"""
from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
import tempfile

import backup as bk

log = logging.getLogger("restore")


def _db_by_label(label: str) -> dict:
    for db in bk._databases_from_env():
        if db["label"] == label:
            return db
    raise SystemExit(f"unknown --db {label!r}; known: "
                     f"{[d['label'] for d in bk._databases_from_env()]}")


def _pull_from_s3(remote: bk.S3Store, key: str) -> str:
    data = remote._client.get_object(Bucket=remote._bucket, Key=key)["Body"].read()
    fd, path = tempfile.mkstemp(suffix=bk._EXT)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)
    return path


def restore(db: dict, dump_path: str) -> None:
    cmd = [
        "pg_restore", "-h", db["host"], "-p", str(db.get("port", 5432)),
        "-U", db["user"], "-d", db["name"],
        "--clean", "--if-exists", "--no-owner", "--no-privileges",
        dump_path,
    ]
    log.info("restoring %s into %s/%s", dump_path, db["host"], db["name"])
    proc = subprocess.run(  # noqa: S603 — fixed argv, no shell
        cmd, env={**os.environ, "PGPASSWORD": db["password"]},
    )
    # pg_restore exits non-zero on benign "does not exist" notices with --clean;
    # surface the code but don't treat a warning-only run as catastrophic.
    if proc.returncode != 0:
        log.warning("pg_restore exited %d — review output above (often harmless "
                    "with --clean --if-exists on a fresh DB)", proc.returncode)
    else:
        log.info("restore complete")


def _list() -> None:
    local = bk.LocalStore(os.environ.get("BACKUP_DIR", "/backups"))
    print("Local:")
    for name in sorted(local.list()):
        print(f"  {name}")
    remote = bk._remote_from_env()
    if remote is not None:
        print("Spaces:")
        for key in sorted(remote.list(os.environ.get("BACKUP_S3_PREFIX",
                                                      "agriforestryos/backups"))):
            print(f"  {key}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Restore a database from a dump.")
    parser.add_argument("--db", help="Target DB label (e.g. farmos, postgis).")
    parser.add_argument("--file", help="Local dump path.")
    parser.add_argument("--from-s3", dest="from_s3", help="Spaces object key to pull and restore.")
    parser.add_argument("--list", action="store_true", help="List available dumps and exit.")
    args = parser.parse_args()
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if args.list:
        _list()
        return
    if not args.db or not (args.file or args.from_s3):
        parser.error("need --db and one of --file / --from-s3 (or --list)")

    db = _db_by_label(args.db)
    if args.from_s3:
        remote = bk._remote_from_env()
        if remote is None:
            sys.exit("Spaces not configured; cannot --from-s3")
        path = _pull_from_s3(remote, args.from_s3)
    else:
        path = args.file
    restore(db, path)


if __name__ == "__main__":
    main()
