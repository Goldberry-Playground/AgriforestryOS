# Grove Consult

The staff dashboard for Grove consulting work, served at
`consult.gatheringatthegrove.com` behind Cloudflare Access. Next.js, standalone
pnpm project (no workspace). Moved here from grove-sites (GOL-3722).

## Run it

```sh
cd apps/consult
corepack enable
pnpm install
cp .env.local.example .env.local   # CONSULT_AUTH_BYPASS=1 skips Access in dev
pnpm dev                           # http://localhost:3006
```

`pnpm lint`, `pnpm type-check` and `pnpm test` are what `consult-ci.yml` runs.

## What is in it

- **Pipeline** (`/pipeline`): every consult lead by stage, with its practices
  by area, acres, zone, service step, next action and days in stage. Stage
  filters and **New client**.
- **Client workspace** (`/client/<id>`), three tabs:
  - **Intake**: client and land (the ZIP looks up the zone and a travel
    estimate), service step, how hands-on, goals, what they have, goal module
    chips, and the areas table. Each area's practice shows its site needs and
    default infrastructure read-only.
  - **Site**: a schematic map sized by acreage with wet areas hatched, the site
    facts, and the walk checklist.
  - **Design**: plan versions, one editor per section with draft, edited and
    approved states, an optional "why I changed it" note, a "show draft" diff,
    and the approval lock. There is no generator; a new plan starts from the
    skeleton Odoo builds.

The layout follows the Grove Consult Flow prototype (`labs/consult/index.html`).

## Where the data comes from

The browser only ever calls this app's own routes under `/api/consult/*`
(`app/api/consult/[...path]/route.ts`). Those run on the server, check the
request is a same-origin JSON call, and talk to Odoo with `ODOO_API_KEY`. The
key never reaches the browser. Server pages read through the same client.

`lib/consult-client/` is the typed client:

| File | What it does |
| --- | --- |
| `types.ts` | The app's own shapes and the `ConsultBackend` interface |
| `odoo.ts` | Maps those to the grove_headless C.7 routes (`/grove/api/v1/consult/*`) |
| `fixture.ts` | The same interface from memory, with made-up clients |
| `backend.ts` | Picks one: the fixture when `CONSULT_FIXTURE=1` and not a production build, else Odoo |
| `browser.ts` | The browser-side caller for `/api/consult/*` |
| `view.ts` | Labels, validation, the map layout and the draft diff (no I/O) |

### Fixture mode

`CONSULT_FIXTURE=1 pnpm dev` runs the whole app without Odoo. A "Fixture data"
badge shows in the top bar. Data lives in memory and resets when the server
restarts. A production build ignores the flag, the same as the auth bypass.

### Contract gaps

The C.7 routes on `main` in grove-odoo-modules do not carry everything spec §D
shows. The client already reads the fields below when they are present and
degrades when they are not, so nothing here needs a second app change:

| Gap | Until Odoo has it |
| --- | --- |
| Pipeline rows lack areas, `stage_since`, zone | Areas come from one extra read per lead; days in stage shows "–"; zone comes from the public ZIP lookup |
| `POST /consult/lead` cannot set the ZIP, or rename an existing lead | The save goes through and says which field Odoo did not keep |
| No service-step list (`GET /consult/steps`) | The service step picker is disabled with a note |
| Practices omit `site_needs` | Only the infrastructure line shows under the practice |
| No walk checklist field on the lead | The checklist shows a note and does not save |
| No plan read route (`GET /consult/lead/<id>/plans`) or plan approve route | The Design tab says plans cannot be read back yet |
| Section edits record the API user, not the person | The app sends the Access email as `actor`; Odoo ignores it for now |

## Tests

```sh
pnpm test        # vitest: client, BFF route, intake form, areas table
pnpm test:e2e    # Playwright: new client, three areas, modules, save, pipeline
```

`pnpm test:e2e` starts its own `next dev` on port 3016 in fixture mode. It
shares `.next` with `pnpm dev`, so stop a running dev server first. It needs a
Chromium (`pnpm exec playwright install chromium`) and is not part of
`consult-ci.yml` yet.

## Access gate

Every request except `GET /healthz` must carry a valid
`Cf-Access-Jwt-Assertion` (see `lib/access.ts`). With `CF_ACCESS_AUD` unset the
app refuses everything, and the dev bypass is ignored in a production build.

## Image

```sh
docker build -f apps/consult/Dockerfile apps/consult
```

`consult-image.yml` builds this on every change, smoke-tests `/healthz`, and on
`main` pushes `ghcr.io/goldberry-playground/grove-consult:<sha>`. The host
(App Platform app, DNS, Access policy) lives in odoocker and AgenticOS.
