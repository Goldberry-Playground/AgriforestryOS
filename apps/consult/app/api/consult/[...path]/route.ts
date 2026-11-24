import { NextResponse, type NextRequest } from "next/server";
import { CONSULT_USER_HEADER } from "@/lib/access";
import { getBackend } from "@/lib/consult-client/backend";
import { ConsultError, type ConsultBackend, type SectionInput } from "@/lib/consult-client/types";
import { WALK_ITEMS, ZIP_PATTERN, isStage, parseLeadInput } from "@/lib/consult-client/view";

/**
 * BFF for the consult workspace. The browser calls these; they call Odoo with
 * the server-held key. Only the routes listed here exist: nothing is proxied
 * through by path, so the browser cannot reach any other Odoo endpoint.
 */
export const dynamic = "force-dynamic";

type Ctx = { backend: ConsultBackend; ids: number[]; key: string; body: unknown; zip: string; actor: string };
type Route = {
  method: "GET" | "POST";
  pattern: RegExp;
  /** The route reads a `?zip=` and should not run without a well-formed one. */
  needsZip?: true;
  run: (ctx: Ctx) => Promise<unknown>;
};

const ID = "(\\d{1,12})";

const ROUTES: Route[] = [
  {
    method: "GET",
    pattern: /^zone$/,
    needsZip: true,
    run: async ({ backend, zip }) => ({ zone: await backend.zone(zip) }),
  },
  {
    method: "GET",
    pattern: /^travel$/,
    needsZip: true,
    run: async ({ backend, zip }) => ({ travel: await backend.travel(zip) }),
  },
  {
    method: "POST",
    pattern: /^lead$/,
    run: ({ backend, body }) => backend.saveLead(parseLeadInput(body)),
  },
  {
    method: "POST",
    pattern: new RegExp(`^lead/${ID}/stage$`),
    run: async ({ backend, ids, body }) => {
      const stage = (body as { stage?: unknown }).stage;
      if (!isStage(stage)) throw new ConsultError(422, "That is not a consult stage.");
      await backend.setStage(ids[0], stage);
      return { ok: true };
    },
  },
  {
    method: "POST",
    pattern: new RegExp(`^lead/${ID}/walk$`),
    run: async ({ backend, ids, body }) => {
      const sent = ((body as { walk?: unknown }).walk ?? {}) as Record<string, unknown>;
      const walk = Object.fromEntries(WALK_ITEMS.map(({ key }) => [key, sent[key] === true]));
      await backend.saveWalk(ids[0], walk);
      return { ok: true };
    },
  },
  {
    method: "GET",
    pattern: new RegExp(`^lead/${ID}/plans$`),
    run: ({ backend, ids }) => backend.plans(ids[0]),
  },
  {
    method: "POST",
    pattern: new RegExp(`^lead/${ID}/plan$`),
    run: async ({ backend, ids }) => ({ plan: await backend.createPlan(ids[0]) }),
  },
  {
    method: "POST",
    pattern: new RegExp(`^lead/${ID}/plan/${ID}/section/([a-z0-9_]{1,64})$`),
    run: async ({ backend, ids, key, body, actor }) => {
      const sent = body as Record<string, unknown>;
      const input: SectionInput = {};
      if (typeof sent.body === "string") input.body = sent.body.slice(0, 50_000);
      if (typeof sent.editNote === "string") input.editNote = sent.editNote.slice(0, 2_000);
      if (sent.approve === true) input.approve = true;
      return { section: await backend.saveSection(ids[0], ids[1], key, input, actor) };
    },
  },
  {
    method: "POST",
    pattern: new RegExp(`^lead/${ID}/plan/${ID}/approve$`),
    run: async ({ backend, ids, actor }) => ({ plan: await backend.approvePlan(ids[0], ids[1], actor) }),
  },
];

function json(status: number, data: unknown) {
  return NextResponse.json(data, { status, headers: { "cache-control": "no-store" } });
}

/** Writes must come from this app's own pages, as JSON. */
function sameOrigin(req: NextRequest): boolean {
  const site = req.headers.get("sec-fetch-site");
  if (site) return site === "same-origin";
  const origin = req.headers.get("origin");
  if (!origin) return true;
  const host = req.headers.get("x-forwarded-host") ?? req.headers.get("host");
  try {
    return new URL(origin).host === host;
  } catch {
    return false;
  }
}

async function handle(req: NextRequest, segments: string[]) {
  const method = req.method as "GET" | "POST";
  const path = segments.join("/");
  for (const route of ROUTES) {
    const match = route.method === method ? route.pattern.exec(path) : null;
    if (!match) continue;
    try {
      let body: unknown = {};
      if (method === "POST") {
        if (!sameOrigin(req) || !req.headers.get("content-type")?.startsWith("application/json")) {
          return json(403, { error: "This request did not come from the consult app." });
        }
        body = await req.json().catch(() => null);
        if (typeof body !== "object" || body === null) return json(422, { error: "Send JSON." });
      }
      const zip = req.nextUrl.searchParams.get("zip") ?? "";
      if (route.needsZip && !ZIP_PATTERN.test(zip)) {
        return json(422, { error: "A ZIP is five digits." });
      }
      const captures = match.slice(1);
      const ids = captures.filter((c) => /^\d+$/.test(c)).map(Number);
      const key = captures.find((c) => !/^\d+$/.test(c)) ?? "";
      const actor = req.headers.get(CONSULT_USER_HEADER) || "local";
      return json(200, await route.run({ backend: getBackend(), ids, key, body, zip, actor }));
    } catch (err) {
      if (err instanceof ConsultError) return json(err.status >= 400 ? err.status : 500, { error: err.message });
      console.error(`[consult] ${method} /api/consult/${path} failed`, err);
      return json(500, { error: "Something went wrong on our side. Try again." });
    }
  }
  return json(404, { error: "Not found." });
}

type Params = { params: Promise<{ path: string[] }> };

export async function GET(req: NextRequest, { params }: Params) {
  return handle(req, (await params).path);
}

export async function POST(req: NextRequest, { params }: Params) {
  return handle(req, (await params).path);
}
