# AgriforestryOS becomes the Grove Consult platform (restructure design)

**Status:** rulings by Josh, 2026-11-01. Targets Release Train #5 (freeze Fri 2026-11-13, QA Mon 11-16, promote Wed 11-18). Train #4 is not touched.
**Amends:** grove-odoo-modules `docs/superpowers/specs/2026-10-22-consult-dashboard-design.md` (gom#378) §D and §E. Wherever that spec says "grove-sites" for the consult app, its client, or its image build, read "AgriforestryOS". Its §A, §B and §C are unchanged.
**Supersedes:** the GOL-2016 decision to keep this repo out of the agent pipeline (AgriforestryOS#36). That decision said to reverse it "when development resumes", and it resumes now.

## Decisions (Josh, 2026-11-01), do not re-open

1. **The consulting software lives in AgriforestryOS.** It does not get its own repo and it does not stay in grove-sites. AgriforestryOS becomes one land-design platform repo holding the farmOS module, the MCP server, sync, ETL, the QGIS scripts, the consult app and the lab prototypes.
2. **Fresh history.** A new `main` branch starts from the current tree as a single root commit. The old `4.x` branch is tagged `archive/farmos-fork` and then deleted. farmOS becomes a dependency (the stock image plus our module), not a fork.
3. **Lab prototypes go into `labs/`** and are deployed by GitHub Actions instead of a local script.
4. **Timing: Train #5.**
5. **What stays where it is:**
   - The nursery planner (`/plan`, `packages/planner`) stays in grove-sites.
   - The consult Odoo models stay in grove-odoo-modules (§C of gom#378).
   - The consult host infrastructure stays in odoocker (`infra/terraform/environments/production/consult.tf`) and AgenticOS (`cloudflare-access-consult.tf`).

## Why

- **AgriforestryOS is a fork in name only.** Commit `e27a44fdb` removed 1,513 upstream farmOS files. What remains is all ours: `modules/farm_syntropic`, `mcp-server`, `sync-service`, `postgis-etl`, `backup-service` and `infra/terraform`. The repo still carries 9,398 upstream commits, uses upstream's `4.x` branch name, and has inherited files (`FUNDING.yml`, `netlify-build-docs.yml`) that do nothing here.
- **The consult work is split over three repos with no reason for it.** gom#378 put the dashboard shell in grove-sites because of the toolchain. But `apps/consult` on grove-sites main (GOL-3581, grove-sites#1179) uses no workspace package; it depends only on `next`, `react` and `server-only`. Moving it costs least now, before GOL-3576 builds on it.
- **The retail planner and the consult dashboard share data, not code.** Both read the Odoo planner facts feed from grove-odoo-modules: the retail vocabulary is a projection of the consultant vocabulary (gom#378 §B). No TypeScript package has to cross a repo boundary, so nothing needs publishing.
- **The lab prototypes are in no repo.** The planner and consult prototypes on `lab.atthegrovenursery.com` (Cloudflare Pages project `grove-lab`) were deployed from a session scratchpad. The only other copies are claude.ai artifacts.

## Non-goals

- Any change to the nursery `/plan`, `packages/planner` or the planner winter beta (GOL-3547 to 3551).
- Any change to the consult models, routes or seed data (gom#378 §B and §C).
- Provisioning a farmOS instance. No farmOS droplet exists on DigitalOcean today, and preprod is a tailnet host. See open item 1.
- Reorganising the folders in the same train. That is section F, which is optional and comes later.

## Target layout

```
AgriforestryOS/  (default branch: main)
├── modules/farm_syntropic/   farmOS module (unchanged path until §F)
├── docker/                   farmOS image + compose files
├── mcp-server/  sync-service/  postgis-etl/  backup-service/
├── scripts/new_client_project.py   (GOL-3577, AgriforestryOS#37)
├── apps/consult/             Next.js staff dashboard (from grove-sites)
├── labs/                     static prototypes → CF Pages grove-lab
├── infra/terraform/          farmOS droplet tier
└── docs/
```

## A. Cut the fresh `main` (Josh; needs repo admin)

**Prerequisite: no open PRs.** A PR branched from `4.x` cannot merge into an unrelated root history, so every open PR has to land on `4.x` or be closed before the cut:

| PR | Action |
|---|---|
| AgriforestryOS#38 (GOL-3573, consult phase 1 A) | Review and merge to `4.x`. It is Train #5 content. |
| AgriforestryOS#37 (GOL-3577, client QGIS script) | Review and merge to `4.x`. |
| AgriforestryOS#35 (GOL-3360, needs-closure audit port) | Merge to `4.x`. Section B needs it anyway. |
| AgriforestryOS#36 (GOL-2016, out of the pipeline) | Close as superseded by this spec. |
| CVE lockfile bumps (11-01 security session) | Merge to `4.x`. |

**Steps:**
1. Tag the current `4.x` tip as `archive/farmos-fork` and push the tag.
2. Create a root commit on a new `main` branch with the `4.x` tip's tree:
   `git commit-tree <4.x>^{tree} -m "AgriforestryOS: fresh history from 4.x@<sha> (archive/farmos-fork)"`
3. In the same root commit (or a second commit, made before branch protection is applied):
   - Remove `.github/FUNDING.yml` and `.github/workflows/netlify-build-docs.yml`.
   - Change `branches: [4.x]` to `[main]` in every workflow, including `deploy-preprod.yml`.
   - Set `"branch": "main"` in `.github/required-checks.json`.
   - Retitle the CHANGELOG `[Unreleased]` entries from "AgriforestryOS fork:" to "AgriforestryOS:".
4. Switch the default branch to `main`, and move the rulesets (main protection and merge queue) to target `main`.
5. Update the matching entry in AgenticOS `.github/merge-policy.json` to `main`.
6. Change the GitHub description to: "Grove land-design platform: farmOS syntropic module, consult dashboard, QGIS/PostGIS, Claude MCP".
7. Delete the `4.x` branch after one green `main` CI run. The tag keeps the history.

**Keep:** `LICENSE.txt` (GPL-2.0) and `COPYRIGHT.txt`, because `farm_syntropic` is a farmOS module. The licence does not change.

**Done when:** `main` is the default branch, all four required checks pass on `main` through the merge queue, and the `archive/farmos-fork` tag resolves to the old `4.x` tip.

## B. Bring the repo into the agent pipeline (Terra)

These are the reversal steps recorded in AgriforestryOS#36, in order:
1. Register a github-sync bridge for AgriforestryOS on the board.
2. Port the six agent-ops workflows in their current shape from grove-sites: `auto-approve.yml`, `ci-autofix.yml`, `ci-failure-router.yml`, `config-freeze.yml`, `fix-touches-test.yml`, `protected-paths-guard.yml`.
   - Pin `ci-failure-router` to a SHA, not `@main`. This follows the 11-01 security scan.
3. Remove `agent_ops: "out-of-scope"` from AgenticOS `.github/merge-policy.json`.
4. Add `ownership.yml` with slugs `engineering-ada`, `engineering-iris` and `devops-terra`, using the current slugs and not `alice`.

**Done when:** a test PR gets an `agent-review/*` check and a board review issue.

## C. Move `apps/consult` from grove-sites (Iris; Terra for the deploy wiring)

**Into AgriforestryOS:**
- **The app.** Copy `apps/consult` as it is on grove-sites main into `apps/consult/`, as a standalone pnpm project with its own `package.json` and `pnpm-lock.yaml`. The `apps/` folder leaves room for more apps; there is no workspace yet.
- **The client.** gom#378 §D's `packages/consult-client` becomes `apps/consult/lib/consult-client/`, a folder inside the app and not a published package.
- **Styling.** If the app wants grove tokens, it copies the CSS variables it needs. It does not depend on `@grove/grove-tokens` (it is a staff tool, and the copy is small).
- **CI** in `.github/workflows/consult-ci.yml`, triggered on PRs, `merge_group` and pushes to main, with path filter `apps/consult/**`:
  - Run `pnpm install --frozen-lockfile`, lint, type-check, and the `lib/access.test.ts` suite.
  - Add the job to `required-checks.json` with a `merge_group` trigger, so `required-checks-audit` stays green.
- **The image** in `.github/workflows/consult-image.yml`, on pushes to main touching `apps/consult/**`:
  - Build `apps/consult/Dockerfile` and push to **the same image name**, `ghcr.io/goldberry-playground/grove-consult:<sha>`. Keeping the name means `consult.tf` does not change.
  - Port the healthz smoke step from grove-sites `docker.yml`. Consult answers `/` with a 403, so poll `/healthz`.

**Deploy wiring in odoocker (Terra):**
- Today `digitalocean_app.consult` rides `var.tenant_image_tag` with the storefronts. Once the image comes from another repo, those SHAs no longer match.
- Add `var.consult_image_tag` (an AgriforestryOS SHA), defaulting to the pinned value in the production tfvars.
- `promote-storefronts.yml` gains an optional `consult_tag` input. The app is still deployed by owner (a), so no fourth deploy owner is added.
- Update the "What lives where" table in `docs/RUNBOOK-consult-host.md` and the header comment in `consult.tf`.
- `consult_enabled` stays `false` until Train #6, as already planned.

**Out of grove-sites (Iris), in the same train, after the AgriforestryOS image exists:**
- Delete `apps/consult`, the `consult` leg of the `.github/workflows/docker.yml` matrix, and its `pnpm-lock.yaml` entries.
- Add a line to the README's apps table saying consult moved to AgriforestryOS.

**Train manifest:** the Train #5 manifest gains an AgriforestryOS line for the consult SHA.

**Done when:**
- The `grove-consult:<sha>` image is built from AgriforestryOS main and passes its healthz smoke.
- grove-sites main has no `apps/consult`.
- An odoocker plan with `consult_enabled=false` shows no change.

## D. `labs/` (Terra)

**Recover the sources.** The deployed pages are self-contained HTML, so download them from the live site:
- `lab.atthegrovenursery.com/planner` → `labs/planner/index.html`
- `/consult` → `labs/consult/index.html`
- `/` (the workshop sheet) → `labs/index.html`

Check each against its artifact (Grove Planner Lab `UAzhVoqaGP53DV8kecHFZJ`, Grove Consult Flow `SQiMbKGxSzWXnX8W4YgeNQ`, workshop sheet `5PE3sGsa4ReCsR8Ez4hceG`). Where an artifact is newer, use the artifact.

**Keep the current behaviour:**
- `labs/_redirects` keeps `/feedback` → the Odoo survey (302).
- `labs/_headers` keeps `X-Robots-Tag: noindex`.

**Deploy:**
- Add `.github/workflows/labs-deploy.yml`, triggered on pushes to main touching `labs/**` and on `workflow_dispatch`.
- It runs `wrangler pages deploy labs --project-name grove-lab`, with `cloudflare/wrangler-action` pinned to a SHA.
- It uses repo secret `CF_PAGES_TOKEN`, synced from `op://Grove Prod/grove-lab pages/credential` by the same 1Password-to-GitHub sync the other repos use.

**Add `labs/README.md`** covering what each prototype is, that they hold no data (state is localStorage only), and the teardown steps (delete the Pages project and the `lab` CNAME, close the survey).

**Done when:** a commit to `labs/` redeploys `lab.atthegrovenursery.com` with no step from Josh, and the scratchpad deploy script is no longer needed.

## E. Docs and board (Terra for docs, Josh for board moves)

**AgriforestryOS docs:**
- Rewrite `README.md` to describe the platform rather than a fork:
  - The stack division of labour from gom#378: farmOS is the ground record, Odoo is the customer and the money, PostGIS/QGIS is the map, MCP is the interface.
  - The layout above, and where the nursery planner lives (grove-sites).
  - Keep the farmOS credit in the licence section.
- Add a short `CLAUDE.md` with the layout, the train cadence, and "default branch is main; `4.x` is archived".

**Other repos:**
- **gom#378:** add the amendment note from this spec's header to §D and §E, or comment it on the PR if it merges first.
- **Vault:** add `Software/Grove Consult + Planner.md` with one paragraph on which repo holds what.

**Board:**
- GOL-3576 (Iris, apps/consult shell): repoint to AgriforestryOS, `apps/consult`. Same blocker (GOL-3575), same train (#6).
- GOL-3577 (Terra): the script stays in AgriforestryOS (#37). The odoocker part gains the `consult_image_tag` work from section C.
- New issues, listed in section G.

## F. Folder reshuffle (optional, after Train #5)

This is a mechanical move into `farmos/` (the module, `docker/` and the farmOS image) and `services/` (the four Python services), done in one PR with every workflow path filter, Dockerfile `COPY` and compose path updated.

Do it only if the flat layout gets in the way. It has no effect on behaviour, and it does not belong in the same train as section A, so that a revert never has to undo both.

## G. Rollout and board split

| Work | Repo | Owner | Blocked by | Train |
|---|---|---|---|---|
| Land or close AgriforestryOS#35–38 and the CVE PR | AgriforestryOS | Josh (review), Ada (#38 fixes) | — | #5 |
| A. Fresh `main` cut, tag, rulesets, merge-policy | AgriforestryOS, AgenticOS | Josh | the row above | #5, by Fri 11-06 |
| B. Agent pipeline on | AgriforestryOS, board, AgenticOS | Terra | A | #5 |
| C1. `apps/consult` + CI + image | AgriforestryOS | Iris | A | #5 |
| C2. `consult_image_tag` + promote input + runbook | odoocker | Terra | C1 image exists | #5 |
| C3. Remove `apps/consult` from grove-sites | grove-sites | Iris | C1 | #5 |
| D. `labs/` + Pages deploy | AgriforestryOS | Terra | A | #5 |
| E. README / CLAUDE.md / gom#378 note / vault | several | Terra | A | #5 |
| F. Folder reshuffle | AgriforestryOS | — | after #5 promote | later |

GOL-3576 (phase 2 D) still targets Train #6 as before; it now builds in AgriforestryOS on top of C1.

## Open items

1. **Where does the one AgriforestryOS farmOS instance run?**
   - gom#378 rules on a single instance for all clients, and GOL-3573 changes that instance's vocabulary.
   - But no farmOS droplet exists on DigitalOcean, `DEPLOY_PREPROD_ENABLED` is unset, and preprod is a tailnet host.
   - Phase 2 (the consult dashboard reading farmOS) needs a reachable instance by Train #6. That needs its own decision and ticket: provision the prod tier from `infra/terraform`, and restrict SSH, because 0.0.0.0/0 on tcp/22 was flagged on 11-01.
2. **The `grove-lab` Pages token expires 2026-11-29.** That is before the December rotation batch. Re-mint it without an expiry (same scopes: Pages Edit, Zone DNS Edit and Zone Read on `atthegrovenursery.com`), or move `labs/` deploys to Josh's terminal. This spec assumes CI.
3. **`4.x` deletion.** The spec deletes the branch after the tag. If you'd rather keep it read-only for a train, add a ruleset that blocks pushes to it.
