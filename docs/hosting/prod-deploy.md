# Production deployment pipeline

Prod is the same stack as dev, with three differences that make it safe for real
data: a **separate, isolated environment**, a **human approval gate** on every
deploy/migration, and **durable backups storage**.

```
tag v* (or manual dispatch)
        │
        ▼
  Deploy to prod ──► ⏸ REQUIRED REVIEWER approves ──► ship code to prod droplet
                                                          │
                                      migrations are SEPARATE + MANUAL + APPROVED
                                      (Run DB migrations (prod) → snapshot → updb)
```

Three principles carry over from dev, plus the gate:
- **App deploy is code-only; migrations are manual** (and here, snapshot-first).
- **Terraform owns the box; GitHub Actions owns the app.**
- **A second human approves** before anything touches prod (the `prod`
  Environment's required-reviewer rule).

## One-time setup

### 1. Provision the prod tier (separate Terraform state)
Use a Terraform **workspace** so prod state never collides with dev:
```bash
cd infra/terraform
export DIGITALOCEAN_TOKEN=dop_v1_...
export TF_VAR_tailscale_auth_key=tskey-auth-...      # reusable, tagged, ephemeral

terraform workspace new prod                          # once; then `select prod`
terraform apply \
  -var environment=prod \
  -var ssh_public_key="ssh-ed25519 AAAA... you@host" \
  -var backups_volume_size_gb=10                      # durable backups volume
terraform output -raw reserved_ip                     # prod deploy target
```
`backups_volume_size_gb` attaches a block-storage volume mounted at
`/opt/agriforestryos/backups`, so the local backup copies survive droplet
replacement (the off-droplet copies go to Spaces regardless — see
`docs/hosting/backups.md`).

### 2. Create the `prod` GitHub Environment + the approval gate
This is a **repo settings change — run it yourself** (it names *you* as the
approver). It creates the Environment the prod workflows pause on:
```bash
# Replace <your-user-id> (from: gh api user --jq .id).
gh api -X PUT repos/Goldberry-Playground/AgriforestryOS/environments/prod \
  -F "reviewers[][type]=User" -F "reviewers[][id]=<your-user-id>"
```
Now `deploy-prod.yml` / `migrate-prod.yml` will **wait for your approval** in the
Actions UI before running.

### 3. Environment-scoped secrets + enable gate
Add these as **`prod` environment** secrets (Settings → Environments → prod), so
they're only readable by approved prod runs:

| Secret | Value |
|---|---|
| `DEPLOY_PROD_HOST` | `terraform output -raw reserved_ip` (prod workspace) |
| `DEPLOY_PROD_SSH_KEY` | private key matching the prod `ssh_public_key` |
| `PROD_ENV_FILE` | full prod server `.env` (see `docker/.env.prod.example`) — **distinct creds from dev** |

Then arm the prod workflows:
```bash
gh variable set DEPLOY_PROD_ENABLED --body true --repo Goldberry-Playground/AgriforestryOS
```

### 4. First-time farmOS install (manual, once)
Same as dev (see `dev-deploy.md` §3) but against the prod host — install farmOS,
enable `farm_syntropic`, run `drush updb`. Reachable over the tailnet only.

## Ongoing

- **Deploy to prod:** push a `v*` tag (or run **Deploy to prod** → enter a ref).
  The run **pauses for reviewer approval**, then ships code (no migrations).
- **Migrate prod:** run **Run DB migrations (prod) [manual]**. It pauses for
  approval, takes a `premigrate` snapshot, prints `updatedb:status`, then
  `drush updb`. Tick *config_import* if exported config changed.

## What makes prod different from dev (summary)

| | dev | prod |
|---|---|---|
| Trigger | auto on merge to `4.x` | `v*` tag / manual dispatch |
| Approval | none | **required reviewer** (`prod` Environment) |
| Backups dir | droplet disk | **block-storage volume** (survives rebuild) |
| Secrets | repo-level | **environment-scoped** to `prod` |
| Enable gate | `DEPLOY_ENABLED` | `DEPLOY_PROD_ENABLED` |

Access (tailnet-only farmOS), the manual-migration principle, and the
backup-before-migrate snapshot are identical to dev.
