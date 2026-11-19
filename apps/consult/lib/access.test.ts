import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import {
  HEALTH_PATH,
  accessCertsUrl,
  authorizeRequest,
  normalizeTeamDomain,
  resetJwksCache,
  verifyAccessJwt,
  type AccessEnv,
  type JwksFetcher,
} from "./access";

const TEAM = "goldberrygrove";
const AUD = "a".repeat(64);
const ISS = `https://${TEAM}.cloudflareaccess.com`;
const NOW_MS = Date.UTC(2026, 9, 22, 12, 0, 0);
const NOW = NOW_MS / 1000;

const ENV: AccessEnv = {
  CF_ACCESS_TEAM_DOMAIN: TEAM,
  CF_ACCESS_AUD: AUD,
  NODE_ENV: "production",
};

type KeyPair = { privateKey: CryptoKey; jwk: JsonWebKey & { kid: string } };
let signer: KeyPair;
let stranger: KeyPair;

async function makeKey(kid: string): Promise<KeyPair> {
  const pair = (await crypto.subtle.generateKey(
    {
      name: "RSASSA-PKCS1-v1_5",
      modulusLength: 2048,
      publicExponent: new Uint8Array([1, 0, 1]),
      hash: "SHA-256",
    },
    true,
    ["sign", "verify"],
  )) as CryptoKeyPair;
  const jwk = await crypto.subtle.exportKey("jwk", pair.publicKey);
  return { privateKey: pair.privateKey, jwk: { ...jwk, kid } };
}

const b64url = (bytes: Uint8Array) =>
  Buffer.from(bytes).toString("base64").replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const seg = (obj: unknown) => b64url(new TextEncoder().encode(JSON.stringify(obj)));

async function sign(
  claims: Record<string, unknown>,
  { key = signer, header = {} }: { key?: KeyPair; header?: Record<string, unknown> } = {},
): Promise<string> {
  const input = `${seg({ alg: "RS256", kid: key.jwk.kid, typ: "JWT", ...header })}.${seg(claims)}`;
  const sig = await crypto.subtle.sign(
    "RSASSA-PKCS1-v1_5",
    key.privateKey,
    new TextEncoder().encode(input),
  );
  return `${input}.${b64url(new Uint8Array(sig))}`;
}

const goodClaims = (over: Record<string, unknown> = {}) => ({
  aud: [AUD],
  iss: ISS,
  iat: NOW - 60,
  exp: NOW + 3600,
  email: "staff@goldberrygrove.farm",
  ...over,
});

let fetchJwks: ReturnType<typeof vi.fn<JwksFetcher>>;

beforeAll(async () => {
  signer = await makeKey("kid-current");
  stranger = await makeKey("kid-current"); // same kid, different key
});

beforeEach(() => {
  resetJwksCache();
  fetchJwks = vi.fn<JwksFetcher>(async () => ({ keys: [signer.jwk] }));
});

const verify = (token: string, nowMs = NOW_MS) =>
  verifyAccessJwt(token, { team: TEAM, aud: AUD, nowMs, fetchJwks });

describe("verifyAccessJwt", () => {
  it("accepts a valid Access token and fetches the team's certs", async () => {
    const res = await verify(await sign(goodClaims()));
    expect(res).toMatchObject({ ok: true, claims: { email: "staff@goldberrygrove.farm" } });
    expect(fetchJwks).toHaveBeenCalledWith(
      "https://goldberrygrove.cloudflareaccess.com/cdn-cgi/access/certs",
    );
  });

  it("accepts a string aud", async () => {
    expect((await verify(await sign(goodClaims({ aud: AUD })))).ok).toBe(true);
  });

  it.each([
    ["wrong audience", goodClaims({ aud: ["b".repeat(64)] })],
    ["wrong issuer", goodClaims({ iss: "https://evil.cloudflareaccess.com" })],
    ["expired", goodClaims({ exp: NOW - 31 })],
    ["expired", goodClaims({ exp: undefined })],
    ["not yet valid", goodClaims({ nbf: NOW + 120 })],
  ])("rejects: %s", async (reason, claims) => {
    expect(await verify(await sign(claims))).toEqual({ ok: false, reason });
  });

  it("tolerates small clock skew on exp", async () => {
    expect((await verify(await sign(goodClaims({ exp: NOW - 10 })))).ok).toBe(true);
  });

  it("rejects a token signed by a different key under a known kid", async () => {
    const token = await sign(goodClaims(), { key: stranger });
    expect(await verify(token)).toEqual({ ok: false, reason: "bad signature" });
  });

  it("rejects a tampered payload", async () => {
    const [h, , s] = (await sign(goodClaims())).split(".");
    const forged = `${h}.${seg(goodClaims({ email: "attacker@example.com" }))}.${s}`;
    expect(await verify(forged)).toEqual({ ok: false, reason: "bad signature" });
  });

  it.each([["none"], ["HS256"]])("refuses alg=%s", async (alg) => {
    const token = await sign(goodClaims(), { header: { alg } });
    expect(await verify(token)).toEqual({ ok: false, reason: "unexpected alg" });
    expect(fetchJwks).not.toHaveBeenCalled();
  });

  it.each([["garbage"], ["a.b"], ["!!.@@.##"]])("rejects malformed %s", async (token) => {
    expect(await verify(token)).toEqual({ ok: false, reason: "malformed token" });
  });

  it("fails closed when the certs endpoint is down", async () => {
    fetchJwks.mockRejectedValueOnce(new Error("ECONNREFUSED"));
    expect(await verify(await sign(goodClaims()))).toEqual({
      ok: false,
      reason: "jwks unavailable",
    });
  });

  it("caches keys and refetches on rotation, at most once a minute", async () => {
    await verify(await sign(goodClaims()));
    await verify(await sign(goodClaims()));
    expect(fetchJwks).toHaveBeenCalledTimes(1);

    const rotated = await makeKey("kid-next");
    fetchJwks.mockResolvedValue({ keys: [signer.jwk, rotated.jwk] });
    const token = await sign(goodClaims(), { key: rotated });

    // Inside the miss-refetch window: unknown kid, no extra fetch.
    expect(await verify(token, NOW_MS + 10_000)).toEqual({ ok: false, reason: "unknown kid" });
    expect(fetchJwks).toHaveBeenCalledTimes(1);

    // After it: refetch picks up the new key.
    expect((await verify(token, NOW_MS + 61_000)).ok).toBe(true);
    expect(fetchJwks).toHaveBeenCalledTimes(2);
  });
});

describe("authorizeRequest", () => {
  const req = (over: Partial<{ method: string; pathname: string; jwt: string | null }> = {}) => ({
    method: "GET",
    pathname: "/",
    jwt: null,
    ...over,
  });

  it("lets the health probe through with no token and no config", async () => {
    expect(await authorizeRequest(req({ pathname: HEALTH_PATH }), {})).toMatchObject({
      allow: true,
      reason: "health",
    });
    expect(
      await authorizeRequest(req({ pathname: HEALTH_PATH, method: "HEAD" }), {}),
    ).toMatchObject({ allow: true });
  });

  it("only exempts GET/HEAD on the exact health path", async () => {
    for (const r of [
      req({ pathname: HEALTH_PATH, method: "POST" }),
      req({ pathname: `${HEALTH_PATH}/x` }),
      req({ pathname: "/healthz.json" }),
    ]) {
      expect((await authorizeRequest(r, ENV, { fetchJwks })).allow).toBe(false);
    }
  });

  it.each([
    ["AUD unset", { CF_ACCESS_TEAM_DOMAIN: TEAM }],
    ["AUD blank", { CF_ACCESS_TEAM_DOMAIN: TEAM, CF_ACCESS_AUD: " " }],
    ["AUD not 64-hex", { CF_ACCESS_TEAM_DOMAIN: TEAM, CF_ACCESS_AUD: "not-an-aud" }],
    ["team unset", { CF_ACCESS_AUD: AUD }],
    ["team junk", { CF_ACCESS_TEAM_DOMAIN: "evil.com/x", CF_ACCESS_AUD: AUD }],
  ])("fails closed when %s, even with a valid token", async (_label, env) => {
    const token = await sign(goodClaims());
    expect(await authorizeRequest(req({ jwt: token }), env, { fetchJwks, nowMs: NOW_MS })).toEqual(
      { allow: false, reason: "access not configured" },
    );
    expect(fetchJwks).not.toHaveBeenCalled();
  });

  it("denies a request with no token", async () => {
    expect(await authorizeRequest(req(), ENV, { fetchJwks })).toEqual({
      allow: false,
      reason: "missing token",
    });
  });

  it("allows a verified token and returns its claims", async () => {
    const token = await sign(goodClaims());
    const res = await authorizeRequest(req({ pathname: "/api/leads", jwt: token }), ENV, {
      fetchJwks,
      nowMs: NOW_MS,
    });
    expect(res).toMatchObject({ allow: true, reason: "verified", claims: { iss: ISS } });
  });

  it("honours CONSULT_AUTH_BYPASS only outside production", async () => {
    expect(
      await authorizeRequest(req(), { CONSULT_AUTH_BYPASS: "1", NODE_ENV: "development" }),
    ).toMatchObject({ allow: true, reason: "bypass" });
    expect(
      await authorizeRequest(req(), { CONSULT_AUTH_BYPASS: "1", NODE_ENV: "production" }),
    ).toEqual({ allow: false, reason: "access not configured" });
    expect(
      await authorizeRequest(req(), { CONSULT_AUTH_BYPASS: "true", NODE_ENV: "development" }),
    ).toMatchObject({ allow: false });
  });
});

describe("normalizeTeamDomain", () => {
  it.each([
    ["goldberrygrove", "goldberrygrove"],
    ["GoldberryGrove", "goldberrygrove"],
    ["goldberrygrove.cloudflareaccess.com", "goldberrygrove"],
    ["https://goldberrygrove.cloudflareaccess.com/", "goldberrygrove"],
    ["", null],
    [undefined, null],
    ["evil.com", null],
    ["a/b", null],
  ])("%s → %s", (raw, want) => {
    expect(normalizeTeamDomain(raw)).toBe(want);
  });

  it("builds the certs URL from the team", () => {
    expect(accessCertsUrl("goldberrygrove")).toBe(
      "https://goldberrygrove.cloudflareaccess.com/cdn-cgi/access/certs",
    );
  });
});
