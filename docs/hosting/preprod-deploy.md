# Preprod deployment pipeline

How code reaches the preprod environment. The flow, end to end:

```
code → PR (gating CI) → merge 4.x → [auto] deploy app to preprod droplet
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

**Before running `terraform apply`:** Enable **MagicDNS** and **HTTPS certificates**
in the Tailscale admin console (Settings → DNS) — `tailscale serve` needs them to
issue the cert.

```bash
cd infra/terraform
export DIGITALOCEAN_TOKEN=dop_v1_...
export TF_VAR_tailscale_auth_key=tskey-auth-...   # reusable, tagged, ephemeral key
cp terraform.tfvars.example terraform.tfvars      # paste your SSH public key
terraform init && terraform apply
terraform output -raw reserved_ip                 # the deploy target (SSH/CI over public :22)
```
The box joins your **tailnet** on boot and runs `tailscale serve` to proxy the
tailnet HTTPS :443 to farmOS on loopback :80. farmOS has **no public web port** —
the cloud firewall allows only `22/tcp` (SSH break-glass + CI deploy) and
`41641/udp` (Tailscale). Reach farmOS at
`https://agriforestryos-preprod.<your-tailnet>.ts.net` (real TLS via `tailscale serve`)
from any device on the tailnet.

### 2. Configure GitHub (secrets + the enable gate)
Secrets sourced from **1Password** (single source of truth). Either paste them
into repo secrets, or use the `1Password/load-secrets-action` with one
service-account token. Required:

| GitHub secret | Value |
|---|---|
| `PREPROD_HOST` | `terraform output -raw reserved_ip` |
| `PREPROD_SSH_KEY` | the **private** key matching the Terraform `ssh_public_key` |
| `PREPROD_ENV_FILE` | full contents of the server `.env` (see `docker/.env.prod.example`) |

Then flip the gate on (workflows are dormant until this is set):
```bash
gh variable set DEPLOY_PREPROD_ENABLED --body true --repo Goldberry-Playground/AgriforestryOS
```

### 3. First-time farmOS install (manual, once)
A brand-new droplet has an empty farmOS DB. SSH in and install once:
```bash
ssh deploy@<reserved_ip>
cd /opt/agriforestryos/repo/docker
COMPOSE="docker compose --env-file /opt/agriforestryos/.env -f docker-compose.server.yml"
$COMPOSE up -d db postgis www
$COMPOSE exec www drush site:install farm --db-url=pgsql://$FARMOS_DB_USER:$FARMOS_DB_PASSWORD@db/$FARMOS_DB_NAME -y
$COMPOSE exec www drush en farm_syntropic -y
$COMPOSE exec www drush updb -y     # installs the syntropic field storage
$COMPOSE up -d                       # bring up sync-service + postgis-etl
```

## Ongoing

- **Deploy app:** merge a PR to `4.x` → the **Deploy to preprod** workflow ships the
  code and rebuilds the stack (cache rebuild only, no migrations). Or run it
  manually from the Actions tab.
- **Apply migrations:** when a change adds an update hook (e.g. a new field),
  run the **Run DB migrations (preprod) [manual]** workflow from the Actions tab.
  It prints `drush updatedb:status` first, then applies. Tick *config_import*
  if the change also alters exported config.

## Operator access
- **farmOS** — tailnet only. From a device on the tailnet:
  `https://agriforestryos-preprod.<your-tailnet>.ts.net` (real TLS via `tailscale serve`).
  There is no public web port.
- **Databases** — DB ports (5432/5433) are never exposed (not in the cloud
  firewall). Reach them over the tailnet, or via an SSH tunnel on the
  break-glass port:
  ```bash
  ssh -L 5433:localhost:5433 deploy@<reserved_ip>   # then QGIS/psql → localhost:5433
  ```

## Not deployed here
The MCP server and QGIS are **operator-local tools** — they run next to Claude
on your machine, not on the server. Only farmOS + the Python services deploy.
Because farmOS is tailnet-only, the operator machine must be **on the tailnet**;
point the MCP server's `FARMOS_BASE_URL` at `http://agriforestryos-preprod`.

## Pre-promotion review checklist

Before tagging a release for prod, on preprod:
- [ ] The Deploy to preprod run is green (post-deploy verify passed).
- [ ] `https://agriforestryos-preprod.<tailnet>.ts.net` loads with a valid cert.
- [ ] Spot-check the change you're shipping (the feature / fixed bug).
- [ ] If the release adds an update hook, you've run **Run DB migrations (preprod)**
      and it succeeded (snapshot-first).
- [ ] Then: tag `vX.Y.Z` (or dispatch Deploy to prod) → approve the gated run.

## Notes / future hardening (Sprint 7: production readiness)
- ✅ **DB backups + backup-before-migrate** — the `backup` service dumps both
  DBs daily to a local volume + DO Spaces, and the migrate workflow snapshots
  before `drush updb`. See `docs/hosting/backups.md`.
- ✅ **Pinned production farmOS image** — `docker/farmos.Dockerfile` pins the
  farmOS base by digest and bakes `farm_syntropic` in (no live bind-mount,
  Xdebug off). `docker-compose.server.yml` builds it; `up -d --build` ships
  committed module changes. Bump the digest deliberately to advance farmOS.
  (Local dev still uses `docker-compose.development.yml` with the bind-mount.)
- ✅ **Private-mesh access (Tailscale)** instead of public TLS — cloud-init
  joins the tailnet; the cloud firewall drops public 80/443 (only `22/tcp` +
  `41641/udp` remain). farmOS is reachable only over the tailnet, where
  WireGuard encrypts transit so basic auth is acceptable and no public certs
  are needed. Requires `TF_VAR_tailscale_auth_key` at apply.
- ✅ **Prod tier + required-reviewer approval gate** — `deploy-prod.yml` /
  `migrate-prod.yml` run against a separate prod droplet (Terraform workspace +
  a block-storage backups volume) and pause on the `prod` GitHub Environment's
  required reviewer before touching prod. Full runbook: `docs/hosting/prod-deploy.md`.
- State/secrets: `terraform.tfstate` and the server `.env` are never committed.
