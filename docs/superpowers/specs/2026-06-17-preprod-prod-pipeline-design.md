# Preprod → Prod deployment pipeline — design

**Date:** 2026-06-17
**Status:** approved (brainstorm), pending implementation plan
**Scope:** finish wiring the release pipeline so AgriforestryOS can run on a real
preprod environment and be promoted to prod, all on a private Tailscale mesh.

## Goal

Realize the target pipeline:

```
code local → docker local → preprod → human review → prod
```

…against what Sprint 7 already built, by closing the gaps found in the audit.
The immediate driver is "release to preprod now and reach it at a friendly,
secure DNS name."

## Decisions (from brainstorming)

- **Access model: private only (Tailscale).** farmOS is never on the public
  internet. No public load balancer. (LB explicitly cut — it terminates no
  public TLS and adds no HA on a single private node.)
- **Friendly name: `tailscale serve` + MagicDNS HTTPS.** farmOS reachable at
  `https://agriforestryos-<tier>.<tailnet>.ts.net` with a real Tailscale-issued
  TLS cert (browser lock; needed for farmOS map/geolocation secure-context
  features). WireGuard still encrypts all transit, so basic auth remains
  acceptable and no OAuth2 migration is required.
- **Two remote tiers: `preprod` + `prod`.** The tier Sprint 7 called "dev" is
  renamed to `preprod` (the staging/review box). Each is its own droplet/DB.
- **Human review = verified preprod, then approve.** A post-deploy health check
  proves preprod came up; a manual checklist guides the look; the prod run still
  pauses on the `prod` GitHub Environment's required reviewer.
- **Promotion trigger: `v*` git tag** (manual dispatch also available).
- **`docker-compose.prod.yml → docker-compose.server.yml`** — it defines the one
  server stack used by *both* tiers, so "prod" was misleading.

## Pipeline architecture

| Stage | Trigger | Mechanism | Access |
|---|---|---|---|
| code local | author | PR to `4.x`; CI (smoke, pytest×3, lint, image build) | — |
| docker local | manual | `docker-compose.development.yml` (bind-mount, Xdebug) | localhost |
| **preprod** | merge to `4.x` (auto) | `deploy-preprod.yml`: SSH → pull → `compose up --build` → `drush cr` → **verify** | `https://agriforestryos-preprod.<tailnet>.ts.net` |
| **human review** | you | review preprod (checklist) + tag `v*` | — |
| review gate | the tag/dispatch | `prod` GitHub Environment **pauses for required reviewer** | — |
| **prod** | approved run | `deploy-prod.yml`: checkout tag → `compose up --build` → verify; `migrate-prod.yml`: snapshot → `updb` (also gated) | `https://agriforestryos-prod.<tailnet>.ts.net` |

Both remote tiers are private (tailnet-only). Separate droplets, separate DBs:
preprod data is throwaway/seed; prod is the system of record. Migrations are
manual + snapshot-first on each tier.

## Work breakdown (two PRs)

### PR-A — rename `dev → preprod` (mechanical refactor)

Pure rename + one bug fix; no behavior change.

- Workflows: `deploy-dev.yml → deploy-preprod.yml`, `migrate-dev.yml → migrate-preprod.yml`.
- Secrets/vars: `DEPLOY_HOST → PREPROD_HOST`, `DEPLOY_SSH_KEY → PREPROD_SSH_KEY`,
  `DEV_ENV_FILE → PREPROD_ENV_FILE`, `DEPLOY_ENABLED → DEPLOY_PREPROD_ENABLED`.
- Terraform: `var.environment` default `dev → preprod`; Tailscale hostname
  becomes `agriforestryos-preprod` (derived from `local.name`, so automatic).
- Compose: `docker-compose.prod.yml → docker-compose.server.yml`; update every
  reference (deploy/migrate workflows for both tiers, docs, dev-deploy runbook).
- Docs: `docs/hosting/dev-deploy.md → preprod-deploy.md`; update prod-deploy.md
  references to the renamed compose file + secrets.
- **Bug fix:** add `backup-service/**` to the `deploy-preprod.yml` trigger
  `paths` (Sprint 7 added the backup service to the stack but not the trigger,
  so a backup-service change would not redeploy).

### PR-B — Tailscale HTTPS ingress + preprod verify (behavioral)

- **Ingress:** `server.yml` `www` port `80:80 → 127.0.0.1:80:80` (farmOS only on
  loopback). cloud-init, after `tailscale up`, runs `tailscale serve --bg 80`
  so the tailnet HTTPS endpoint (`:443`) proxies to farmOS on loopback. Exact
  `serve` syntax verified against the installed Tailscale version at
  implementation time.
- **Healthchecks:** light container healthchecks so `compose ps` "healthy" is
  meaningful — `www` (HTTP GET of the farmOS homepage/login) and `db`
  (`pg_isready`). Other services already `restart: unless-stopped`.
- **Verify step:** both deploy workflows, after `up -d --build`, assert all
  services report healthy (`docker compose ps`) and farmOS returns HTTP 200
  (curl through the container/loopback). Deploy fails loudly if not.
- **Review checklist:** a short manual checklist in `preprod-deploy.md` for the
  human review before tagging a release.

## Provisioning runbook (operator-run; all prerequisites already in place)

Documented in `preprod-deploy.md`; the operator runs these (billable / account
actions the agent cannot perform):

1. **Tailscale admin:** enable MagicDNS + HTTPS certificates; mint a reusable,
   tagged (`tag:agriforestryos`), ephemeral, pre-authorized auth key.
2. **Provision preprod:** `terraform apply` (default `environment=preprod`) with
   `TF_VAR_tailscale_auth_key` and `ssh_public_key`. `backups_volume_size_gb`
   may stay `0` for preprod (backups on droplet disk are fine for staging).
3. **GitHub:** add `PREPROD_HOST` / `PREPROD_SSH_KEY` / `PREPROD_ENV_FILE`
   secrets (1Password → GH); `gh variable set DEPLOY_PREPROD_ENABLED --body true`.
4. **First install:** one-time `drush site:install farm` + `drush en farm_syntropic`
   + `drush updb` on the box; verify `https://agriforestryos-preprod.<tailnet>.ts.net`.
5. **Prod later (same module):** `terraform workspace new prod` +
   `-var environment=prod -var backups_volume_size_gb=10`; create the `prod`
   Environment + required reviewer (one `gh api` call); add `prod`-scoped
   secrets + `DEPLOY_PROD_ENABLED`; promote with a `v*` tag.

## Out of scope (explicitly deferred)

- Public access / public TLS / load balancer / OAuth2 — excluded by the
  private-mesh decision.
- The QGIS/GeoPackage → farmOS importer (seed the ~2,227 planned trees) — the
  next *feature*, tracked separately.
- Full observability/alerting beyond the light healthchecks above — the deferred
  production-readiness item.
- Vanity domain (`farm.goldberrygrove.farm`) via split-DNS — can layer on the
  Tailscale TLS name later; not needed now.

## Success criteria

- Merging to `4.x` auto-deploys preprod and the deploy fails if preprod is
  unhealthy.
- farmOS is reachable only over the tailnet, at the HTTPS MagicDNS name, with a
  valid cert.
- A `v*` tag opens a prod deploy that **cannot** proceed without a human
  approving the `prod` Environment run.
- No public 80/443 on either tier; DBs never internet-exposed.
- Naming across the repo (`preprod`, `server.yml`) matches the mental model.
