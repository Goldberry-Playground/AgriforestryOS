/**
 * Cloudflare Access gate for the consult app (GOL-3581).
 *
 * consult.gatheringatthegrove.com sits behind a Cloudflare Access policy, but
 * App Platform also serves the app on its default `*.ondigitalocean.app`
 * ingress, which is public and has no origin allowlist. Anyone who learns that
 * hostname would skip Access entirely, so the app verifies the Access JWT
 * itself on every request:
 *
 *   - `Cf-Access-Jwt-Assertion` header, RS256, signed by a key from
 *     `https://<team>.cloudflareaccess.com/cdn-cgi/access/certs`
 *   - `iss` is `https://<team>.cloudflareaccess.com`
 *   - `aud` contains `CF_ACCESS_AUD`
 *   - not expired (and not before `nbf`, when present)
 *
 * Fail closed: if `CF_ACCESS_AUD` or `CF_ACCESS_TEAM_DOMAIN` is missing or
 * malformed, everything except the health check is denied.
 *
 * Written against WebCrypto only (no `jose`) so it runs unchanged in the Edge
 * middleware runtime and in Node tests.
 */

/** The only path served without a JWT — App Platform's health probe. */
export const HEALTH_PATH = "/healthz";

/** Header Cloudflare Access adds to every proxied request. */
export const ACCESS_JWT_HEADER = "cf-access-jwt-assertion";

/** Request header the middleware sets to the verified identity, for the BFF. */
export const CONSULT_USER_HEADER = "x-consult-user";

/** Allowed clock skew between Cloudflare and this container, in seconds. */
const CLOCK_SKEW_S = 30;

/** How long fetched signing keys are trusted before a refetch. */
const JWKS_TTL_MS = 60 * 60 * 1000;

/** Minimum gap between refetches triggered by an unknown `kid`. */
const JWKS_MISS_REFETCH_MS = 60 * 1000;

const AUD_PATTERN = /^[0-9a-f]{64}$/;
const TEAM_PATTERN = /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/;

export type AccessEnv = {
  CF_ACCESS_TEAM_DOMAIN?: string;
  CF_ACCESS_AUD?: string;
  CONSULT_AUTH_BYPASS?: string;
  NODE_ENV?: string;
};

export type AccessClaims = {
  aud: string | string[];
  iss: string;
  exp: number;
  nbf?: number;
  iat?: number;
  sub?: string;
  email?: string;
  common_name?: string;
  [claim: string]: unknown;
};

export type AccessDecision =
  | { allow: true; reason: "health" | "bypass" | "verified"; claims?: AccessClaims }
  | { allow: false; reason: string };

type Jwk = JsonWebKey & { kid?: string };

export type JwksFetcher = (url: string) => Promise<{ keys: Jwk[] }>;

/**
 * Accepts `goldberrygrove`, `goldberrygrove.cloudflareaccess.com` or the full
 * `https://` origin and returns the bare team name, or null if it isn't one.
 */
export function normalizeTeamDomain(raw: string | undefined): string | null {
  if (!raw) return null;
  const team = raw
    .trim()
    .toLowerCase()
    .replace(/^https?:\/\//, "")
    .replace(/\/+$/, "")
    .replace(/\.cloudflareaccess\.com$/, "");
  return TEAM_PATTERN.test(team) ? team : null;
}

export function accessIssuer(team: string): string {
  return `https://${team}.cloudflareaccess.com`;
}

export function accessCertsUrl(team: string): string {
  return `${accessIssuer(team)}/cdn-cgi/access/certs`;
}

/** Local-dev escape hatch; never honoured in a production build. */
export function bypassEnabled(env: AccessEnv): boolean {
  return env.CONSULT_AUTH_BYPASS === "1" && env.NODE_ENV !== "production";
}

// ── base64url / JWT parsing ──────────────────────────────────────────────

function base64UrlToBytes(input: string): Uint8Array<ArrayBuffer> {
  if (!/^[A-Za-z0-9_-]*$/.test(input)) throw new Error("bad base64url");
  const b64 = input.replace(/-/g, "+").replace(/_/g, "/");
  const padded = b64 + "=".repeat((4 - (b64.length % 4)) % 4);
  const bin = atob(padded);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

function decodeJsonSegment<T>(segment: string): T {
  return JSON.parse(new TextDecoder().decode(base64UrlToBytes(segment))) as T;
}

// ── JWKS cache ───────────────────────────────────────────────────────────

type CacheEntry = { keys: Map<string, CryptoKey>; fetchedAt: number };
const jwksCache = new Map<string, CacheEntry>();

/** Test hook: forget every cached signing key. */
export function resetJwksCache(): void {
  jwksCache.clear();
}

const defaultFetcher: JwksFetcher = async (url) => {
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`JWKS fetch ${res.status}`);
  return (await res.json()) as { keys: Jwk[] };
};

async function importKeys(jwks: { keys: Jwk[] }): Promise<Map<string, CryptoKey>> {
  const keys = new Map<string, CryptoKey>();
  for (const jwk of jwks.keys ?? []) {
    if (jwk.kty !== "RSA" || !jwk.kid) continue;
    const { kid, ...material } = jwk;
    keys.set(
      kid,
      await crypto.subtle.importKey(
        "jwk",
        { kty: material.kty, n: material.n, e: material.e },
        { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" },
        false,
        ["verify"],
      ),
    );
  }
  return keys;
}

async function signingKey(
  team: string,
  kid: string,
  fetchJwks: JwksFetcher,
  nowMs: number,
): Promise<CryptoKey | null> {
  const url = accessCertsUrl(team);
  const cached = jwksCache.get(url);
  const fresh = cached && nowMs - cached.fetchedAt < JWKS_TTL_MS;
  if (fresh && cached.keys.has(kid)) return cached.keys.get(kid)!;
  // Unknown kid on a fresh cache = Cloudflare may have rotated. Refetch, but
  // not more than once a minute so a flood of junk kids can't hammer the
  // certs endpoint.
  if (fresh && nowMs - cached.fetchedAt < JWKS_MISS_REFETCH_MS) return null;
  const entry: CacheEntry = { keys: await importKeys(await fetchJwks(url)), fetchedAt: nowMs };
  jwksCache.set(url, entry);
  return entry.keys.get(kid) ?? null;
}

// ── verification ─────────────────────────────────────────────────────────

export type VerifyOptions = {
  team: string;
  aud: string;
  nowMs?: number;
  fetchJwks?: JwksFetcher;
};

export type VerifyResult =
  | { ok: true; claims: AccessClaims }
  | { ok: false; reason: string };

export async function verifyAccessJwt(
  token: string,
  { team, aud, nowMs = Date.now(), fetchJwks = defaultFetcher }: VerifyOptions,
): Promise<VerifyResult> {
  const parts = token.split(".");
  if (parts.length !== 3) return { ok: false, reason: "malformed token" };
  const [h, p, s] = parts;

  let header: { alg?: string; kid?: string };
  let claims: AccessClaims;
  let signature: Uint8Array<ArrayBuffer>;
  try {
    header = decodeJsonSegment(h);
    claims = decodeJsonSegment(p);
    signature = base64UrlToBytes(s);
  } catch {
    return { ok: false, reason: "malformed token" };
  }

  // Pin the algorithm: never let the token choose (no `none`, no HS256).
  if (header.alg !== "RS256") return { ok: false, reason: "unexpected alg" };
  if (!header.kid) return { ok: false, reason: "missing kid" };

  let key: CryptoKey | null;
  try {
    key = await signingKey(team, header.kid, fetchJwks, nowMs);
  } catch {
    return { ok: false, reason: "jwks unavailable" };
  }
  if (!key) return { ok: false, reason: "unknown kid" };

  const valid = await crypto.subtle.verify(
    "RSASSA-PKCS1-v1_5",
    key,
    signature,
    new TextEncoder().encode(`${h}.${p}`),
  );
  if (!valid) return { ok: false, reason: "bad signature" };

  if (claims.iss !== accessIssuer(team)) return { ok: false, reason: "wrong issuer" };
  const auds = Array.isArray(claims.aud) ? claims.aud : [claims.aud];
  if (!auds.includes(aud)) return { ok: false, reason: "wrong audience" };

  const now = Math.floor(nowMs / 1000);
  if (typeof claims.exp !== "number" || claims.exp + CLOCK_SKEW_S <= now) {
    return { ok: false, reason: "expired" };
  }
  if (typeof claims.nbf === "number" && claims.nbf - CLOCK_SKEW_S > now) {
    return { ok: false, reason: "not yet valid" };
  }
  return { ok: true, claims };
}

/**
 * The whole gate: health probe, dev bypass, fail-closed config check, then
 * JWT verification. Pure apart from the JWKS fetch, so it's unit-testable
 * without Next.
 */
export async function authorizeRequest(
  req: { method: string; pathname: string; jwt: string | null },
  env: AccessEnv,
  opts: { nowMs?: number; fetchJwks?: JwksFetcher } = {},
): Promise<AccessDecision> {
  if (req.pathname === HEALTH_PATH && (req.method === "GET" || req.method === "HEAD")) {
    return { allow: true, reason: "health" };
  }
  if (bypassEnabled(env)) return { allow: true, reason: "bypass" };

  const team = normalizeTeamDomain(env.CF_ACCESS_TEAM_DOMAIN);
  const aud = env.CF_ACCESS_AUD?.trim().toLowerCase();
  if (!team || !aud || !AUD_PATTERN.test(aud)) {
    return { allow: false, reason: "access not configured" };
  }
  if (!req.jwt) return { allow: false, reason: "missing token" };

  const result = await verifyAccessJwt(req.jwt, { team, aud, ...opts });
  return result.ok
    ? { allow: true, reason: "verified", claims: result.claims }
    : { allow: false, reason: result.reason };
}
