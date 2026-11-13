# syntax=docker/dockerfile:1.7

# Multi-stage build for Grove Consult (consult.gatheringatthegrove.com).
#
# The app is a standalone pnpm project, so the build context is this
# directory, NOT the repo root:
#   docker build -f apps/consult/Dockerfile apps/consult
#
# Output: `node server.js` on port 3001 — odoocker production/consult.tf pins
# http_port = 3001 and health-checks GET /healthz (the one path the Access
# middleware serves without a Cf-Access-Jwt-Assertion).

ARG NODE_VERSION=22-alpine

# ── 1. install dependencies (frozen lockfile) ────────────────────────────
FROM node:${NODE_VERSION} AS deps
RUN apk add --no-cache libc6-compat
WORKDIR /app
RUN corepack enable

# Only the manifests, so this layer caches across source changes.
COPY package.json pnpm-lock.yaml .npmrc ./

RUN pnpm install --frozen-lockfile

# ── 2. build the standalone Next.js bundle ───────────────────────────────
FROM node:${NODE_VERSION} AS builder
WORKDIR /app
RUN corepack enable

COPY --from=deps /app/node_modules ./node_modules

COPY . .

ENV NEXT_TELEMETRY_DISABLED=1

RUN pnpm build

# ── 3. minimal runtime image ─────────────────────────────────────────────
FROM node:${NODE_VERSION} AS runner
WORKDIR /app

# Strip npm/npx/corepack — we only run `node server.js` (bundled-CLI CVEs).
RUN rm -rf /usr/local/lib/node_modules/npm \
    && rm -f /usr/local/bin/npm /usr/local/bin/npx \
    && (rm -f /usr/local/bin/corepack /usr/local/bin/yarn /usr/local/bin/yarnpkg || true)

# Current Alpine security patches, so upstream-fixed HIGH CVEs don't block
# the Trivy gate in .github/workflows/consult-image.yml.
RUN apk upgrade --no-cache

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3001
ENV HOSTNAME=0.0.0.0

RUN addgroup --system --gid 1001 nodejs \
 && adduser  --system --uid 1001 nextjs

COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=builder --chown=nextjs:nodejs /app/public ./public

USER nextjs
EXPOSE 3001

CMD ["node", "server.js"]
