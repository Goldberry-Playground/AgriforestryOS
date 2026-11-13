import { NextResponse, type NextRequest } from "next/server";
import {
  ACCESS_JWT_HEADER,
  CONSULT_USER_HEADER,
  authorizeRequest,
} from "@/lib/access";

/**
 * Every request is checked against Cloudflare Access (see lib/access.ts) —
 * pages, BFF routes and static assets alike, because the App Platform ingress
 * hostname bypasses Access. Only `GET /healthz` is exempt.
 */
export async function middleware(req: NextRequest) {
  const decision = await authorizeRequest(
    {
      method: req.method,
      pathname: req.nextUrl.pathname,
      jwt: req.headers.get(ACCESS_JWT_HEADER),
    },
    // Named reads (not the whole process.env) so Next records each one for
    // the middleware runtime. NODE_ENV is inlined at build time, so the dev
    // bypass is dead code in the production image.
    {
      CF_ACCESS_TEAM_DOMAIN: process.env.CF_ACCESS_TEAM_DOMAIN,
      CF_ACCESS_AUD: process.env.CF_ACCESS_AUD,
      CONSULT_AUTH_BYPASS: process.env.CONSULT_AUTH_BYPASS,
      NODE_ENV: process.env.NODE_ENV,
    },
  );

  if (!decision.allow) {
    console.warn(
      `[consult] access denied: ${decision.reason} ${req.method} ${req.nextUrl.pathname}`,
    );
    return new NextResponse("Forbidden", {
      status: 403,
      headers: { "content-type": "text/plain; charset=utf-8", "cache-control": "no-store" },
    });
  }

  // Never trust an inbound identity header; only the verified claim sets it.
  const headers = new Headers(req.headers);
  headers.delete(CONSULT_USER_HEADER);
  const who = decision.claims?.email ?? decision.claims?.common_name;
  if (typeof who === "string" && who) headers.set(CONSULT_USER_HEADER, who);
  return NextResponse.next({ request: { headers } });
}
