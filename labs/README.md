# labs/

Static prototypes served at <https://lab.atthegrovenursery.com> from the
Cloudflare Pages project `grove-lab`. Each page is one self-contained HTML
file: no build step, no backend.

| Path | File | What it is |
|---|---|---|
| `/` | `index.html` | Planner Workshop sheet. One page to put on a screen or print, with a QR code and link for each station (planner, consult, feedback). |
| `/planner` | `planner/index.html` | Grove Planner Lab, the retail planting-planner prototype. |
| `/consult` | `consult/index.html` | Grove Consult Flow, the consultant intake-to-plan prototype. |
| `/feedback` | `_redirects` | 302 to the Odoo workshop survey. |

`_headers` sends `X-Robots-Tag: noindex` on every path. The pages also carry
`<meta name="robots" content="noindex">`.

The shipped products live elsewhere: the nursery planner is `/plan` in
grove-sites, and the consult dashboard is `apps/consult` in this repo. Nothing
here is imported by either.

## No data

The prototypes store nothing on a server. State is `localStorage` only, in the
visitor's own browser (`planner-lab-v2`, `consult-flow-v1`). Clearing site data
resets a prototype. The only data leaving the browser is what a visitor types
into the Odoo survey behind `/feedback`.

Third-party requests: Google Fonts on every page, and `qrcodejs` from cdnjs on
the workshop sheet.

## Deploy

`.github/workflows/labs-deploy.yml` deploys this folder on every push to `main`
that touches `labs/**`, and on `workflow_dispatch`. It runs
`wrangler pages deploy` against `grove-lab` and then smoke-checks the live
site (three pages answer 200, `/feedback` redirects, `noindex` is set).
`README.md` is left out of the upload.

To change a prototype, edit the HTML and merge. There is no local deploy step.

Repo configuration the workflow needs:

| Name | Kind | Source |
|---|---|---|
| `CF_PAGES_TOKEN` | secret | `op://Grove Prod/grove-lab pages/credential`, via AgenticOS `tools/sync-ci-secrets.sh`. Scopes: Pages Edit, plus Zone DNS Edit and Zone Read on `atthegrovenursery.com`. |
| `CF_ACCOUNT_ID` | variable | The Cloudflare account that owns `grove-lab`. Not a secret. |

Until both are set the workflow skips the deploy with a warning, so it does not
fail on `main`.

## Where the sources came from

These files were recovered on 2026-11-13 from the live deployment (GOL-3725),
which until then had been deployed from a session scratchpad and was in no
repo. They were taken from `grove-lab.pages.dev`, because the custom domain
adds a Cloudflare bot-detection script to every response. With that script
removed, the custom-domain copies are byte-identical to the ones committed
here.

The same pages exist as claude.ai artifacts: Grove Planner Lab
`UAzhVoqaGP53DV8kecHFZJ`, Grove Consult Flow `SQiMbKGxSzWXnX8W4YgeNQ`, and the
workshop sheet `5PE3sGsa4ReCsR8Ez4hceG`.

One URL detail changed. The scratchpad deploy served `/planner` and `/consult`
directly and redirected the trailing-slash form. With `planner/index.html` and
`consult/index.html`, Pages serves `/planner/` and `/consult/` and answers the
bare path with a 308 to it. Both forms keep working, including the QR codes.

## Teardown

When the workshop prototypes are no longer needed:

1. Delete the Cloudflare Pages project `grove-lab` (this removes
   `grove-lab.pages.dev` and the custom domain binding).
2. Delete the `lab` CNAME record in the `atthegrovenursery.com` zone.
3. Close the Odoo survey that `/feedback` points to.
4. Revoke the `grove-lab pages` API token, and remove `CF_PAGES_TOKEN` and
   `CF_ACCOUNT_ID` from this repo and the row from AgenticOS
   `infra/ci-secrets.yaml`.
5. Delete `labs/` and `.github/workflows/labs-deploy.yml`.
