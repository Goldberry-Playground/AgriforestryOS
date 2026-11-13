# backup-service

Logical Postgres backups for the AgriforestryOS stack, written **both** to a
local volume on the droplet and to **DigitalOcean Spaces** (S3-compatible),
with independent retention pruning in each place.

Two databases are backed up:

| label     | source                              | why                                   |
|-----------|-------------------------------------|---------------------------------------|
| `farmos`  | the `db` service (Postgres 17)      | system of record — **irreplaceable**  |
| `postgis` | the `postgis` service (PostGIS/PG16)| reproducible via ETL, but cheap to keep |

Dumps are `pg_dump -Fc` (custom format) → restorable with `pg_restore --clean`.
Filenames are `LABEL__REASON__TIMESTAMP.dump`, e.g.
`farmos__routine__2026-06-16T030000Z.dump`. The layout sorts chronologically,
so retention is just "keep the newest `BACKUP_KEEP` per label".

## Run

```bash
python backup.py --once                  # one pass (cron / manual)
python backup.py                         # daily loop (BACKUP_INTERVAL_SECONDS)
python backup.py --once --reason premigrate   # snapshot before a migration
python restore.py --list                 # show local + remote dumps
python restore.py --db farmos --file /backups/farmos__routine__...dump
python restore.py --db farmos --from-s3 agriforestryos/backups/farmos__...dump
```

In the stack it runs as the `backup` compose service (daily loop). The
**Run DB migrations** workflow shells in and runs `--once --reason premigrate`
*before* `drush updb`, so every migration is preceded by a fresh snapshot.

## Configuration (env)

Reuses the same DB credentials the stack already passes. Spaces is optional —
**without it the service runs local-only and logs a warning** (it never
silently skips the backup).

| var | default | purpose |
|---|---|---|
| `FARMOS_DB_HOST/PORT/USER/PASSWORD/NAME` | `db`/`5432`/… | farmOS DB |
| `POSTGIS_HOST/PORT/USER/PASSWORD/DB` | `postgis`/`5432`/… | spatial mirror (skipped if `POSTGIS_DB` unset) |
| `BACKUP_DIR` | `/backups` | local dump directory (mounted volume) |
| `BACKUP_KEEP` | `14` | dumps retained per label (`<=0` = never prune) |
| `BACKUP_INTERVAL_SECONDS` | `86400` | loop cadence |
| `SPACES_BUCKET` / `SPACES_KEY` / `SPACES_SECRET` | — | Spaces creds (omit → local-only) |
| `SPACES_ENDPOINT` | `https://nyc3.digitaloceanspaces.com` | Spaces region endpoint |
| `SPACES_REGION` | `nyc3` | |
| `BACKUP_S3_PREFIX` | `agriforestryos/backups` | key prefix in the bucket |

## Tests

```bash
uv run --extra dev pytest        # pure transforms + orchestration (I/O faked)
```

The pure layer (filename layout, retention planning, S3 keys) and the
orchestration (`run_once`: dump → local → remote → prune, one-DB-failure
isolation, local-only fallback) are unit-tested; `pg_dump`/`pg_restore`/boto3
are thin adapters exercised only in the live stack.
