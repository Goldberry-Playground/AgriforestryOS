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
