# Database backups & restore

The farmOS operational database is the system of record for the whole orchard
inventory — it has no upstream and must be recoverable. The PostGIS mirror is
reproducible from farmOS via the ETL, but it's cheap to back up too.

## What runs

The `backup` service (`backup-service/`, in `docker-compose.server.yml`) takes
`pg_dump -Fc` snapshots of both databases on a daily loop and writes them to
**two** places:

1. A **local volume** on the droplet (`backups:`) — fast restores. In prod this
   volume should sit on attached DO block storage so it survives droplet
   replacement (wired in `infra/terraform/`).
2. **DigitalOcean Spaces** (S3-compatible) — the off-droplet copy that survives
   total droplet/region loss.

Retention keeps the newest `BACKUP_KEEP` (default 14) dumps **per database** in
each place; older ones are pruned. `BACKUP_KEEP=0` disables pruning entirely.

Spaces is optional: with `SPACES_*` unset the service runs **local-only** and
logs a warning — it never silently skips a backup.

## Backup before every migration

The **Run DB migrations (dev) [manual]** workflow takes a fresh snapshot
(`--reason premigrate`) *before* `drush updb`. A migration is exactly where a
bad update hook can corrupt data, so the snapshot is the rollback point. If the
snapshot fails, the workflow stops before touching `updb`.

## Restore (manual, deliberate)

Restoring overwrites the target DB's objects, so it's never automatic.

```bash
ssh deploy@<host>
cd /opt/agriforestryos/repo/docker
COMPOSE="docker compose --env-file /opt/agriforestryos/.env -f docker-compose.server.yml"

# See what's available (local + Spaces):
$COMPOSE run --rm --no-deps backup --once --reason manual   # optional: take one now
$COMPOSE run --rm --no-deps --entrypoint "uv run --no-dev python restore.py" backup --list

# Restore farmOS from a local dump:
$COMPOSE run --rm --no-deps --entrypoint "uv run --no-dev python restore.py" backup \
  --db farmos --file /backups/farmos__routine__2026-06-16T030000Z.dump

# Or pull the dump straight from Spaces:
$COMPOSE run --rm --no-deps --entrypoint "uv run --no-dev python restore.py" backup \
  --db farmos --from-s3 agriforestryos/backups/farmos__routine__2026-06-16T030000Z.dump
```

After a farmOS restore, run `drush cr` on `www` to clear caches, and re-run the
PostGIS ETL (or restore the `postgis` DB too) so the spatial mirror matches.

## Configuration

See `backup-service/README.md` for the full env-var table. The values are set
in the server `.env` (from 1Password → GitHub secrets), same as the rest of the
stack. The Spaces key/secret are the only new secrets.
