# Preprod → Prod Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the release pipeline so AgriforestryOS runs on a private,
HTTPS-named `preprod` tier (auto-deploy + post-deploy verify) and is promoted to
`prod` through the existing human-approval gate.

**Architecture:** Two changes land as two PRs. PR-A is a behavior-neutral rename
(`dev → preprod`, `docker-compose.prod.yml → docker-compose.server.yml`) plus a
deploy-trigger bug fix. PR-B adds the Tailscale `serve` HTTPS ingress, light
container healthchecks, and a post-deploy verification step on both deploy
workflows. Everything stays private (tailnet-only); no public ports, no LB.

**Tech Stack:** GitHub Actions (YAML), Docker Compose, Terraform (DigitalOcean),
Tailscale, farmOS/Drupal, bash. No application code changes.

## Global Constraints

- **Private-mesh only.** No public `80`/`443` on any tier; no load balancer; DB
  ports never internet-exposed. (Copied from the design decision.)
- **Repo flow.** Branch off `4.x`; PR into `4.x`; squash-merge via
  `gh pr merge --squash --delete-branch`; sync local `4.x` after.
- **Auth workaround.** Commit with `--no-gpg-sign`. Push with
  `timeout 90 git -c credential.helper='!gh auth git-credential' push https://github.com/Goldberry-Playground/AgriforestryOS.git HEAD:<branch>`.
- **CHANGELOG.** Each PR adds ONE new bullet under `## [Unreleased] > ### Added`.
  NEVER edit existing (historical) CHANGELOG bullets or the spec file — those
  are records of past work.
- **Commit trailer.** End every commit message with:
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`
- **Never** push or open a PR against `farmOS/farmOS`.
- Both PRs branch from the current `feature/preprod-pipeline` branch's base
  (`4.x`); the design spec is already committed on `feature/preprod-pipeline`.
  Land the spec with PR-A (it's already staged in that branch's history).

---

## PR-A — Rename `dev → preprod` + `server.yml` (behavior-neutral)

Branch: `feature/preprod-pipeline` (already created off `4.x`, already holds the
spec commit). All Task 1–6 commits go on this branch; PR-A ships it.

### Task 1: Rename the compose file → `docker-compose.server.yml`

**Files:**
- Rename: `docker/docker-compose.prod.yml` → `docker/docker-compose.server.yml`
- Modify (reference only): `docs/hosting/backups.md`, `docs/hosting/prod-deploy.md`,
  `.github/workflows/deploy-prod.yml`, `.github/workflows/migrate-prod.yml`
- Do NOT touch: `CHANGELOG.md` historical bullets, the spec file.

**Interfaces:**
- Produces: the deployed server stack is now referenced everywhere as
  `docker/docker-compose.server.yml` (used by BOTH preprod and prod).

- [ ] **Step 1: Rename the file with git**

```bash
cd "/Users/joshuadunbar/Documents/Dev Projects/agriforestryOS"
git mv docker/docker-compose.prod.yml docker/docker-compose.server.yml
```

- [ ] **Step 2: Update the file's own header comment**

In `docker/docker-compose.server.yml`, change the opening comment from
"AgriforestryOS server stack (dev environment on the Terraform-provisioned
droplet)." to:

```
# AgriforestryOS server stack — the ONE deploy unit shared by the preprod and
# prod tiers (selected by the per-tier .env, not the compose file). farmOS +
# Postgres + PostGIS + the Python sync/ETL/backup services. The MCP server and
# QGIS are operator-local tools and are intentionally NOT here.
```

- [ ] **Step 3: Update references in the prod workflows + docs (NOT the dev/preprod workflows — Task 2 owns those)**

Replace `docker-compose.prod.yml` → `docker-compose.server.yml` in:
`.github/workflows/deploy-prod.yml`, `.github/workflows/migrate-prod.yml`,
`docs/hosting/backups.md`, `docs/hosting/prod-deploy.md`.

- [ ] **Step 4: Validate the renamed compose file**

Run: `docker compose -f docker/docker-compose.server.yml config -q`
Expected: no output (valid). Warnings about unset env vars are fine.

- [ ] **Step 5: Confirm no stale references remain (except history)**

Run: `grep -rln "docker-compose.prod.yml" --include="*.yml" --include="*.yaml" --include="*.md" . | grep -v docker/www`
Expected: only `CHANGELOG.md` and `docs/superpowers/specs/...` (historical/spec —
left intentionally) plus `deploy-dev.yml`/`migrate-dev.yml` (Task 2 renames those
next). No other files.

- [ ] **Step 6: Commit**

```bash
git add docker/ docs/hosting/backups.md docs/hosting/prod-deploy.md .github/workflows/deploy-prod.yml .github/workflows/migrate-prod.yml
git commit --no-gpg-sign -m "refactor(deploy): rename docker-compose.prod.yml → server.yml

It defines the one server stack used by both the preprod and prod tiers, so
'prod' was misleading. No behavior change.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

### Task 2: Rename + rewrite the preprod workflows

**Files:**
- Rename: `.github/workflows/deploy-dev.yml` → `.github/workflows/deploy-preprod.yml`
- Rename: `.github/workflows/migrate-dev.yml` → `.github/workflows/migrate-preprod.yml`

**Interfaces:**
- Produces: GitHub vars/secrets the operator must set — `DEPLOY_PREPROD_ENABLED`
  (var), `PREPROD_HOST`, `PREPROD_SSH_KEY`, `PREPROD_ENV_FILE` (secrets).

- [ ] **Step 1: git mv both workflow files**

```bash
git mv .github/workflows/deploy-dev.yml .github/workflows/deploy-preprod.yml
git mv .github/workflows/migrate-dev.yml .github/workflows/migrate-preprod.yml
```

- [ ] **Step 2: Rewrite `deploy-preprod.yml`**

Apply these exact substitutions throughout the file:
- `name: Deploy to dev` → `name: Deploy to preprod`
- every `docker-compose.prod.yml` → `docker-compose.server.yml`
- `vars.DEPLOY_ENABLED` → `vars.DEPLOY_PREPROD_ENABLED`
- `secrets.DEPLOY_SSH_KEY` → `secrets.PREPROD_SSH_KEY`
- `secrets.DEV_ENV_FILE` → `secrets.PREPROD_ENV_FILE`
- `secrets.DEPLOY_HOST` → `secrets.PREPROD_HOST`
- `concurrency.group: deploy-dev` → `deploy-preprod`
- in the trigger `paths:`, add a line `- 'backup-service/**'` (the Sprint 7
  backup service was added to the stack but not the deploy trigger — bug fix)
- update header comment text `dev droplet` → `preprod droplet`, and the
  `gh variable set DEPLOY_ENABLED` hint → `gh variable set DEPLOY_PREPROD_ENABLED`

- [ ] **Step 3: Rewrite `migrate-preprod.yml`**

Apply the same substitutions:
- `name: Run DB migrations (dev) [manual]` → `name: Run DB migrations (preprod) [manual]`
- `docker-compose.prod.yml` → `docker-compose.server.yml`
- `vars.DEPLOY_ENABLED` → `vars.DEPLOY_PREPROD_ENABLED`
- `secrets.DEPLOY_SSH_KEY` → `secrets.PREPROD_SSH_KEY`
- `secrets.DEPLOY_HOST` → `secrets.PREPROD_HOST`
- `concurrency.group: deploy-dev` → `deploy-preprod`
- header comment `dev` → `preprod`

- [ ] **Step 4: Lint the workflows**

Run: `actionlint .github/workflows/deploy-preprod.yml .github/workflows/migrate-preprod.yml`
Expected: no output (clean). If `actionlint` is not installed locally, skip —
CI's "Workflow lint (actionlint)" job will gate it.

- [ ] **Step 5: Confirm no stale tokens remain in these two files**

Run: `grep -nE "DEPLOY_ENABLED|DEV_ENV_FILE|DEPLOY_HOST|DEPLOY_SSH_KEY|docker-compose.prod.yml|deploy-dev|Deploy to dev" .github/workflows/deploy-preprod.yml .github/workflows/migrate-preprod.yml`
Expected: no matches.

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/
git commit --no-gpg-sign -m "refactor(deploy): rename dev workflows → preprod (+ backup-service trigger fix)

deploy-dev→deploy-preprod, migrate-dev→migrate-preprod; secrets/vars renamed
to PREPROD_*/DEPLOY_PREPROD_ENABLED; compose ref → server.yml. Adds the missing
backup-service/** path to the deploy trigger.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

### Task 3: Terraform default environment → preprod

**Files:**
- Modify: `infra/terraform/variables.tf` (the `environment` variable default)
- Modify: `infra/terraform/main.tf` (header comment only), `infra/terraform/README.md` (title + `agriforestryos-dev` refs)

**Interfaces:**
- Produces: a plain `terraform apply` now builds the `preprod` tier; `local.name`
  becomes `agriforestryos-preprod` and the Tailscale hostname follows
  automatically. Prod is still `terraform workspace ... -var environment=prod`.

- [ ] **Step 1: Change the default**

In `infra/terraform/variables.tf`, change the `environment` variable:

```hcl
variable "environment" {
  description = "Environment name (used in resource names + tags). Default tier is preprod; prod uses a separate workspace with -var environment=prod."
  type        = string
  default     = "preprod"
}
```

- [ ] **Step 2: Fix the cosmetic `dev` references**

- `infra/terraform/main.tf`: first-line comment `AgriforestryOS dev environment:`
  → `AgriforestryOS deploy tier (preprod by default; prod via workspace):`
- `infra/terraform/README.md`: title `# AgriforestryOS — Dev infrastructure (Terraform)`
  → `# AgriforestryOS — Deploy-tier infrastructure (Terraform)`; replace any
  `agriforestryos-dev` → `agriforestryos-preprod` and "dev environment"/"dev host"
  → "preprod environment"/"preprod host". Leave the prod-workspace instructions intact.

- [ ] **Step 3: Validate Terraform**

Run: `cd infra/terraform && terraform fmt && terraform validate`
Expected: `Success! The configuration is valid.`

- [ ] **Step 4: Commit**

```bash
cd "/Users/joshuadunbar/Documents/Dev Projects/agriforestryOS"
git add infra/terraform/
git commit --no-gpg-sign -m "refactor(infra): default tier is now preprod (was dev)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

### Task 4: Rename + sweep the hosting docs

**Files:**
- Rename: `docs/hosting/dev-deploy.md` → `docs/hosting/preprod-deploy.md`
- Modify: `docs/hosting/prod-deploy.md`, `infra/terraform/README.md` (secret-name refs)

**Interfaces:**
- Consumes: the var/secret names from Task 2; the `server.yml` name from Task 1.

- [ ] **Step 1: git mv the runbook**

```bash
git mv docs/hosting/dev-deploy.md docs/hosting/preprod-deploy.md
```

- [ ] **Step 2: Sweep `preprod-deploy.md`**

Replace throughout: `dev droplet`/`dev environment`/`dev box` → `preprod ...`;
`Dev deployment pipeline` (title) → `Preprod deployment pipeline`;
`DEPLOY_HOST`→`PREPROD_HOST`, `DEPLOY_SSH_KEY`→`PREPROD_SSH_KEY`,
`DEV_ENV_FILE`→`PREPROD_ENV_FILE`, `DEPLOY_ENABLED`→`DEPLOY_PREPROD_ENABLED`;
`agriforestryos-dev`→`agriforestryos-preprod`;
`docker-compose.prod.yml`→`docker-compose.server.yml`;
"Deploy to dev" workflow name → "Deploy to preprod"; "Run DB migrations (dev)" →
"Run DB migrations (preprod)".

- [ ] **Step 3: Fix cross-references in `prod-deploy.md` and `README.md`**

- `docs/hosting/prod-deploy.md`: any `dev-deploy.md` link → `preprod-deploy.md`;
  any `DEPLOY_HOST`/`DEPLOY_SSH_KEY`/`DEV_ENV_FILE` mentioned as the *dev* pattern
  → `PREPROD_*`; `docker-compose.prod.yml` → `docker-compose.server.yml`.
- `infra/terraform/README.md`: `DEPLOY_HOST`/`DEPLOY_SSH_KEY` wiring table →
  `PREPROD_HOST`/`PREPROD_SSH_KEY`.

- [ ] **Step 4: Confirm the sweep is complete**

Run: `grep -rln "dev-deploy\|DEPLOY_ENABLED\b\|DEV_ENV_FILE\|agriforestryos-dev" --include="*.md" --include="*.tf" --include="*.yml" . | grep -v docker/www | grep -v CHANGELOG | grep -v superpowers`
Expected: no matches.

- [ ] **Step 5: Commit**

```bash
git add docs/ infra/terraform/README.md
git commit --no-gpg-sign -m "docs: rename dev-deploy runbook → preprod-deploy; sweep dev→preprod refs

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

### Task 5: CHANGELOG + ship PR-A

- [ ] **Step 1: Add ONE new bullet at the top of `## [Unreleased] > ### Added`**

(Do not touch existing bullets.)

```
- AgriforestryOS fork: release-pipeline rename — the auto-deploy remote tier is now **`preprod`** (was "dev"), and `docker-compose.prod.yml` is renamed **`docker-compose.server.yml`** (it defines the one server stack shared by both tiers). Workflows `deploy-preprod.yml`/`migrate-preprod.yml` use `PREPROD_*` secrets + `DEPLOY_PREPROD_ENABLED`; Terraform's default tier is `preprod` (prod stays a separate workspace). Also fixes a Sprint 7 bug: the deploy trigger now watches `backup-service/**`. Behavior-neutral; prod (tag-promoted, approval-gated) is unchanged.
```

- [ ] **Step 2: Commit, push, open PR**

```bash
git add CHANGELOG.md
git commit --no-gpg-sign -m "docs(changelog): preprod/server.yml rename (PR-A)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
timeout 90 git -c credential.helper='!gh auth git-credential' push https://github.com/Goldberry-Playground/AgriforestryOS.git HEAD:feature/preprod-pipeline
timeout 90 gh pr create --repo Goldberry-Playground/AgriforestryOS --base 4.x --head feature/preprod-pipeline \
  --title "refactor(sprint7): rename dev→preprod + docker-compose.server.yml" \
  --body "Behavior-neutral rename of the auto-deploy tier dev→preprod and docker-compose.prod.yml→server.yml (shared by both tiers), plus the design spec and the backup-service/** deploy-trigger bug fix. Prod unchanged. See docs/superpowers/specs/2026-06-17-preprod-prod-pipeline-design.md."
```

- [ ] **Step 3: Watch CI green, then merge + sync**

```bash
timeout 300 gh pr checks <PR#> --repo Goldberry-Playground/AgriforestryOS --watch
timeout 90 gh pr merge <PR#> --repo Goldberry-Playground/AgriforestryOS --squash --delete-branch
git checkout 4.x && timeout 60 git -c credential.helper='!gh auth git-credential' pull --no-edit https://github.com/Goldberry-Playground/AgriforestryOS.git 4.x
```

---

## PR-B — Tailscale HTTPS ingress + preprod verify (behavioral)

Branch: `feature/pipeline-tailscale-https` off the freshly-synced `4.x`.

### Task 6: Loopback-only farmOS port + healthchecks

**Files:**
- Modify: `docker/docker-compose.server.yml` (`www` + `db` services)

**Interfaces:**
- Produces: farmOS published only on `127.0.0.1:80`; `www` and `db` report
  Docker health status (consumed by the verify step in Task 8).

- [ ] **Step 1: Bind farmOS to loopback + add a www healthcheck**

In `docker/docker-compose.server.yml`, change the `www` service `ports` and add a
`healthcheck` (so only `tailscale serve` exposes farmOS to the tailnet):

```yaml
    ports:
      # Loopback only — the tailnet reaches farmOS via `tailscale serve` (HTTPS),
      # never directly. Public access is impossible (cloud firewall + no 0.0.0.0 bind).
      - '127.0.0.1:80:80'
    healthcheck:
      test: ["CMD-SHELL", "curl -fsS http://localhost/user/login >/dev/null || exit 1"]
      interval: 30s
      timeout: 5s
      retries: 5
      start_period: 120s
```

- [ ] **Step 2: Add a db healthcheck**

In the `db` service, add (uses the same env the service already sets):

```yaml
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $${FARMOS_DB_USER} -d $${FARMOS_DB_NAME}"]
      interval: 10s
      timeout: 5s
      retries: 10
```

(Note the doubled `$$` so compose passes `$FARMOS_DB_USER` to the container shell
rather than interpolating at parse time.)

- [ ] **Step 3: Validate**

Run: `docker compose -f docker/docker-compose.server.yml config -q`
Expected: no output (valid).

- [ ] **Step 4: Commit**

```bash
git add docker/docker-compose.server.yml
git commit --no-gpg-sign -m "feat(deploy): farmOS on loopback + www/db healthchecks

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

### Task 7: `tailscale serve` HTTPS in cloud-init

**Files:**
- Modify: `infra/terraform/cloud-init.yaml`

**Interfaces:**
- Consumes: farmOS on `127.0.0.1:80` (Task 6).
- Produces: tailnet HTTPS at `https://<hostname>.<tailnet>.ts.net` → farmOS.

- [ ] **Step 1: Add the serve command after `tailscale up`**

In `infra/terraform/cloud-init.yaml`, immediately after the existing
`tailscale up ...` line, add:

```yaml
  # Expose farmOS (loopback:80) on the tailnet over HTTPS with a real
  # Tailscale-issued cert. Requires MagicDNS + HTTPS enabled in the tailnet
  # admin (operator one-time step). https://<hostname>.<tailnet>.ts.net
  - tailscale serve --bg 80
```

- [ ] **Step 2: Verify Terraform still validates (templatefile parses)**

Run: `cd infra/terraform && terraform validate`
Expected: `Success! The configuration is valid.`

- [ ] **Step 3: Commit**

```bash
cd "/Users/joshuadunbar/Documents/Dev Projects/agriforestryOS"
git add infra/terraform/cloud-init.yaml
git commit --no-gpg-sign -m "feat(infra): tailscale serve — farmOS HTTPS on the tailnet

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

### Task 8: Post-deploy verify step in both deploy workflows

**Files:**
- Modify: `.github/workflows/deploy-preprod.yml`, `.github/workflows/deploy-prod.yml`

**Interfaces:**
- Consumes: the healthchecks from Task 6.
- Produces: a deploy that FAILS if farmOS isn't healthy after `up -d --build`.

- [ ] **Step 1: Append a verify block to the remote deploy script in BOTH workflows**

After the `drush cr` line inside the `<<'REMOTE'` heredoc (in each of
`deploy-preprod.yml` and `deploy-prod.yml`), add:

```bash
            echo "== Post-deploy verify =="
            COMPOSE="docker compose --env-file /opt/agriforestryos/.env -f docker-compose.server.yml"
            # Wait up to ~2min for www to report healthy, then confirm HTTP 200.
            for i in $(seq 1 24); do
              status=$($COMPOSE ps --format '{{.Service}} {{.Health}}' | awk '$1=="www"{print $2}')
              [ "$status" = "healthy" ] && break
              sleep 5
            done
            [ "$status" = "healthy" ] || { echo "farmOS www not healthy: $status"; $COMPOSE ps; exit 1; }
            $COMPOSE exec -T www curl -fsS http://localhost/user/login >/dev/null \
              && echo "verify OK: farmOS responds 200" || { echo "farmOS HTTP check failed"; exit 1; }
```

(`deploy-prod.yml` already defines `COMPOSE` earlier; if so, reuse it instead of
re-declaring — keep one definition per script.)

- [ ] **Step 2: Lint**

Run: `actionlint .github/workflows/deploy-preprod.yml .github/workflows/deploy-prod.yml`
Expected: clean (or rely on CI if actionlint absent).

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/deploy-preprod.yml .github/workflows/deploy-prod.yml
git commit --no-gpg-sign -m "feat(deploy): fail the deploy if farmOS isn't healthy after up

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

### Task 9: Docs (review checklist + MagicDNS HTTPS) + CHANGELOG + ship PR-B

**Files:**
- Modify: `docs/hosting/preprod-deploy.md`, `docs/hosting/prod-deploy.md`, `CHANGELOG.md`

- [ ] **Step 1: Add the MagicDNS-HTTPS prerequisite + access URL to `preprod-deploy.md`**

In the provisioning steps, add a first sub-step under Tailscale setup:
"Enable **MagicDNS** and **HTTPS certificates** in the Tailscale admin console
(Settings → DNS) before `terraform apply` — `tailscale serve` needs them to issue
the cert." And update the access line to:
"farmOS: `https://agriforestryos-preprod.<your-tailnet>.ts.net` (real TLS via
`tailscale serve`)."

- [ ] **Step 2: Add the human-review checklist to `preprod-deploy.md`**

Add a `## Pre-promotion review checklist` section:

```
Before tagging a release for prod, on preprod:
- [ ] The Deploy to preprod run is green (post-deploy verify passed).
- [ ] `https://agriforestryos-preprod.<tailnet>.ts.net` loads with a valid cert.
- [ ] Spot-check the change you're shipping (the feature / fixed bug).
- [ ] If the release adds an update hook, you've run **Run DB migrations (preprod)**
      and it succeeded (snapshot-first).
- [ ] Then: tag `vX.Y.Z` (or dispatch Deploy to prod) → approve the gated run.
```

- [ ] **Step 3: Note the HTTPS access in `prod-deploy.md`**

Update the prod access mention to
`https://agriforestryos-prod.<your-tailnet>.ts.net` and reference the same
MagicDNS/HTTPS prerequisite.

- [ ] **Step 4: Add ONE new CHANGELOG bullet** (top of `### Added`, leave history)

```
- AgriforestryOS fork: Tailscale HTTPS ingress + post-deploy verify — farmOS is published only on `127.0.0.1:80` and exposed on the tailnet over HTTPS via `tailscale serve` (real cert at `https://agriforestryos-<tier>.<tailnet>.ts.net`; needs MagicDNS+HTTPS enabled). `www`/`db` get container healthchecks, and both deploy workflows now **fail if farmOS isn't healthy** after `up -d --build`. Adds a pre-promotion review checklist to the preprod runbook.
```

- [ ] **Step 5: Commit, push, open PR**

```bash
git add docs/ CHANGELOG.md
git commit --no-gpg-sign -m "docs(changelog): tailscale HTTPS ingress + preprod verify (PR-B)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
timeout 90 git -c credential.helper='!gh auth git-credential' push https://github.com/Goldberry-Playground/AgriforestryOS.git HEAD:feature/pipeline-tailscale-https
timeout 90 gh pr create --repo Goldberry-Playground/AgriforestryOS --base 4.x --head feature/pipeline-tailscale-https \
  --title "feat(sprint7): tailscale HTTPS ingress + preprod post-deploy verify" \
  --body "farmOS on loopback + tailscale serve HTTPS (real cert on the tailnet), www/db healthchecks, and a deploy that fails if farmOS isn't healthy. Plus the pre-promotion review checklist. Private-mesh only."
```

- [ ] **Step 6: Watch CI green, then merge + sync**

```bash
timeout 300 gh pr checks <PR#> --repo Goldberry-Playground/AgriforestryOS --watch
timeout 90 gh pr merge <PR#> --repo Goldberry-Playground/AgriforestryOS --squash --delete-branch
git checkout 4.x && timeout 60 git -c credential.helper='!gh auth git-credential' pull --no-edit https://github.com/Goldberry-Playground/AgriforestryOS.git 4.x
```

---

## Operator handoff (after both PRs merge)

These are billable / account / settings actions the agent cannot run. Full
detail lives in `docs/hosting/preprod-deploy.md`; summary:

1. Tailscale admin: enable MagicDNS + HTTPS; mint a reusable/tagged/ephemeral key.
2. `export TF_VAR_tailscale_auth_key=...` then `terraform apply` (preprod default).
3. Set `PREPROD_HOST`/`PREPROD_SSH_KEY`/`PREPROD_ENV_FILE` secrets;
   `gh variable set DEPLOY_PREPROD_ENABLED --body true`.
4. One-time farmOS install on the box; verify the HTTPS URL.

## Self-Review

**Spec coverage:**
- Private-only / no LB → Tasks 6–7 keep loopback + serve; no public ports added. ✓
- Tailscale serve HTTPS name → Task 6 (loopback) + Task 7 (serve) + Task 9 (docs). ✓
- Two tiers, rename dev→preprod → Tasks 2–4. ✓
- Verified-preprod review → Task 6 (healthchecks) + Task 8 (verify) + Task 9 (checklist). ✓
- `v*` tag promotion → unchanged (prod workflows already do this; Task 1/8 only
  touch their compose ref + verify). ✓
- `server.yml` rename → Task 1. ✓
- backup-service trigger bug → Task 2. ✓
- Provisioning runbook → Task 9 docs + Operator handoff. ✓

**Placeholder scan:** `<PR#>`, `<tailnet>`, `<hostname>`, `<tier>` are runtime
values (PR number assigned on creation; tailnet/tier are DNS templates) — not
plan placeholders. All code/edits are shown verbatim. ✓

**Type/name consistency:** `docker-compose.server.yml`, `PREPROD_HOST`,
`PREPROD_SSH_KEY`, `PREPROD_ENV_FILE`, `DEPLOY_PREPROD_ENABLED`,
`agriforestryos-preprod`, `tailscale serve --bg 80` used consistently across all
tasks. The verify step's `COMPOSE` uses `docker-compose.server.yml` (matches the
Task 1 rename). ✓
