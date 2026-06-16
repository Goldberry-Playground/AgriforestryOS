# Dev deployment pipeline

How code reaches the dev environment. The flow, end to end:

```
code → PR (gating CI) → merge 4.x → [auto] deploy app to dev droplet
                                          │
                              migrations are SEPARATE + MANUAL
                              (run the "Run DB migrations" workflow by hand)
```

Two principles, both deliberate:
- **App deploy is automatic; DB migrations are manual.** `drush updb` runs the
  farmOS update hooks — exactly where a bad change can corrupt data. A human
  triggers it after reviewing what's pending. Auto-deploy never runs it.
- **Terraform owns the box; GitHub Actions owns the app.** See
  `infra/terraform/` for the infrastructure.

## One-time setup

### 1. Provision the droplet
```bash
cd infra/terraform
export DIGITALOCEAN_TOKEN=dop_v1_...
cp terraform.tfvars.example terraform.tfvars   # paste your SSH public key
terraform init && terraform apply
terraform output -raw reserved_ip              # the deploy target
```

### 2. Configure GitHub (secrets + the enable gate)
Secrets sourced from **1Password** (single source of truth). Either paste them
into repo secrets, or use the `1Password/load-secrets-action` with one
service-account token. Required:

| GitHub secret | Value |
|---|---|
| `DEPLOY_HOST` | `terraform output -raw reserved_ip` |
| `DEPLOY_SSH_KEY` | the **private** key matching the Terraform `ssh_public_key` |
| `DEV_ENV_FILE` | full contents of the server `.env` (see `docker/.env.prod.example`) |

Then flip the gate on (workflows are dormant until this is set):
```bash
gh variable set DEPLOY_ENABLED --body true --repo Goldberry-Playground/AgriforestryOS
```

### 3. First-time farmOS install (manual, once)
A brand-new droplet has an empty farmOS DB. SSH in and install once:
```bash
ssh deploy@<reserved_ip>
cd /opt/agriforestryos/repo/docker
COMPOSE="docker compose --env-file /opt/agriforestryos/.env -f docker-compose.prod.yml"
$COMPOSE up -d db postgis www
$COMPOSE exec www drush site:install farm --db-url=pgsql://$FARMOS_DB_USER:$FARMOS_DB_PASSWORD@db/$FARMOS_DB_NAME -y
$COMPOSE exec www drush en farm_syntropic -y
$COMPOSE exec www drush updb -y     # installs the syntropic field storage
$COMPOSE up -d                       # bring up sync-service + postgis-etl
```

## Ongoing

- **Deploy app:** merge a PR to `4.x` → the **Deploy to dev** workflow ships the
  code and rebuilds the stack (cache rebuild only, no migrations). Or run it
  manually from the Actions tab.
- **Apply migrations:** when a change adds an update hook (e.g. a new field),
  run the **Run DB migrations (dev) [manual]** workflow from the Actions tab.
  It prints `drush updatedb:status` first, then applies. Tick *config_import*
  if the change also alters exported config.

## Operator access to the databases
The DB ports (5432/5433) are firewalled off the public internet. Reach them via
an SSH tunnel:
```bash
ssh -L 5433:localhost:5433 deploy@<reserved_ip>   # then QGIS/psql → localhost:5433
```

## Not deployed here
The MCP server and QGIS are **operator-local tools** — they run next to Claude
on your machine, not on the server. Only farmOS + the two Python services
deploy.

## Notes / future hardening
- The dev `www` uses the `farmos/farmos:4.x-dev` image with the module
  bind-mounted. A production environment should build a pinned farmOS image
  (composer) instead, add TLS (Caddy/Traefik), DB backups-before-migrate, and a
  required-reviewer approval gate on a `prod` GitHub Environment.
- State/secrets: `terraform.tfstate` and the server `.env` are never committed.
