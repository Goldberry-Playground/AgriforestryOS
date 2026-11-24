/**
 * Server-only consult backend that talks to grove_headless (C.7 routes under
 * `/grove/api/v1/consult`). It holds the Odoo API key, so nothing in here may
 * be imported from a client component; the browser goes through the BFF in
 * `app/api/consult`.
 *
 * A few things the workspace needs are not on the C.7 routes yet (see README,
 * "Contract gaps"). Where a route or field is missing this client reads it as
 * "not available" instead of failing, and picks the value up as soon as Odoo
 * starts sending it.
 */
import {
  ConsultError,
  type Area,
  type ConsultBackend,
  type ConsultStage,
  type Lead,
  type LeadInput,
  type LeadSummary,
  type Plan,
  type PlanSection,
  type TravelEstimate,
} from "./types";
import { isStage } from "./view";

type Wire = Record<string, unknown>;

export type OdooConfig = { url: string; apiKey: string; tenantId: string };
export type Fetcher = typeof fetch;

const BASE = "/grove/api/v1";
const TIMEOUT_MS = 15_000;
const HYDRATE_BATCH = 6;

export function odooConfigFromEnv(env: Record<string, string | undefined> = process.env): OdooConfig {
  const url = (env.ODOO_URL ?? "").replace(/\/+$/, "");
  const apiKey = env.ODOO_API_KEY ?? "";
  if (!url || !apiKey) throw new ConsultError(500, "ODOO_URL and ODOO_API_KEY are not set for this app.");
  return { url, apiKey, tenantId: env.ODOO_TENANT_ID || "nursery" };
}

const text = (value: unknown): string => (typeof value === "string" ? value : "");
const num = (value: unknown): number => (typeof value === "number" && Number.isFinite(value) ? value : 0);
const idOrNull = (value: unknown): number | null => (typeof value === "number" && value > 0 ? value : null);
const list = (value: unknown): Wire[] => (Array.isArray(value) ? (value as Wire[]) : []);

function areaFromWire(a: Wire): Area {
  return {
    id: idOrNull(a.id) ?? undefined,
    name: text(a.name),
    practiceId: idOrNull(a.practice_id),
    acres: num(a.acres),
    wet: a.wet === true,
    poorSoil: a.poor_soil === true,
    shade: a.shade === true,
    aspect: text(a.aspect) as Area["aspect"],
  };
}

function summaryFromWire(l: Wire): LeadSummary {
  return {
    id: num(l.id),
    name: text(l.name),
    zip: text(l.zip),
    stage: isStage(l.consult_stage) ? l.consult_stage : "intake",
    stepId: idOrNull(l.consult_step_id),
    stageSince: text(l.stage_since) || null,
    zone: text(l.zone) || null,
    areas: list(l.areas).map(areaFromWire),
  };
}

function leadFromWire(l: Wire): Lead {
  const walk = l.walk_checklist;
  return {
    ...summaryFromWire(l),
    areas: list(l.areas).map(areaFromWire),
    contactName: text(l.contact_name),
    email: text(l.email),
    phone: text(l.phone),
    handsOn: text(l.hands_on) as Lead["handsOn"],
    goals: text(l.goals),
    existing: text(l.existing),
    moduleIds: Array.isArray(l.module_ids) ? (l.module_ids as number[]) : [],
    walk: walk && typeof walk === "object" ? (walk as Lead["walk"]) : null,
  };
}

function sectionFromWire(s: Wire): PlanSection {
  const body = text(s.body);
  return {
    key: text(s.key),
    title: text(s.title),
    status: (text(s.status) || "generated") as PlanSection["status"],
    body,
    draftBody: typeof s.draft_body === "string" ? s.draft_body : body,
    editNote: text(s.edit_note),
    by: text(s.by),
    approvedAt: text(s.approved_at) || null,
  };
}

function planFromWire(p: Wire): Plan {
  return {
    id: num(p.id),
    leadId: num(p.lead_id),
    version: num(p.version),
    status: (text(p.status) || "draft") as Plan["status"],
    sections: list(p.section_ids ?? p.sections).map(sectionFromWire),
  };
}

/** The body `POST /consult/lead` takes. Odoo names the scalar fields by column. */
export function leadToWire(input: LeadInput): Wire {
  const wire: Wire = {
    name: input.name,
    zip: input.zip,
    grove_hands_on: input.handsOn || false,
    grove_goals: input.goals,
    grove_existing: input.existing,
    consult_step_id: input.stepId,
    module_ids: input.moduleIds,
    areas: input.areas.map((a) => ({
      name: a.name,
      practice_id: a.practiceId,
      acres: a.acres,
      wet: a.wet,
      poor_soil: a.poorSoil,
      shade: a.shade,
      aspect: a.aspect || false,
    })),
  };
  if (input.id !== undefined) wire.id = input.id;
  else wire.grove_consult_stage = "intake";
  return wire;
}

export function createOdooBackend(config: OdooConfig, fetcher: Fetcher = fetch): ConsultBackend {
  const zoneCache = new Map<string, string | null>();

  async function call(method: "GET" | "POST", path: string, body?: Wire): Promise<Wire> {
    let res: Response;
    try {
      res = await fetcher(`${config.url}${BASE}${path}`, {
        method,
        headers: {
          Authorization: `Bearer ${config.apiKey}`,
          "X-Grove-Tenant": config.tenantId,
          Accept: "application/json",
          ...(body ? { "Content-Type": "application/json" } : {}),
        },
        body: body ? JSON.stringify(body) : undefined,
        cache: "no-store",
        signal: AbortSignal.timeout(TIMEOUT_MS),
      });
    } catch {
      throw new ConsultError(502, "Odoo did not answer. Try again in a moment.");
    }
    let data: Wire = {};
    try {
      data = (await res.json()) as Wire;
    } catch {
      // Non-JSON error pages fall through to the status handling below.
    }
    if (res.ok) return data;
    if (res.status === 503) throw new ConsultError(503, "Consult is switched off in Odoo.");
    if (res.status === 401 || res.status === 403) {
      throw new ConsultError(502, "Odoo turned down this app's API key.");
    }
    throw new ConsultError(res.status, text(data.error) || `Odoo answered ${res.status}.`);
  }

  /** Runs a call against a route that may not exist yet; 404 becomes null. */
  async function optional(method: "GET" | "POST", path: string, body?: Wire): Promise<Wire | null> {
    try {
      return await call(method, path, body);
    } catch (err) {
      if (err instanceof ConsultError && err.status === 404) return null;
      throw err;
    }
  }

  async function zone(zip: string): Promise<string | null> {
    if (!zip) return null;
    if (!zoneCache.has(zip)) {
      const data = await optional("GET", `/zone?zip=${encodeURIComponent(zip)}`);
      zoneCache.set(zip, data ? text(data.zone) || null : null);
    }
    return zoneCache.get(zip) ?? null;
  }

  async function withZone<T extends LeadSummary>(lead: T): Promise<T> {
    if (lead.zone || !lead.zip) return lead;
    return { ...lead, zone: await zone(lead.zip).catch(() => null) };
  }

  async function lead(id: number): Promise<Lead> {
    const data = await call("GET", `/consult/lead/${id}`);
    return withZone(leadFromWire((data.lead ?? {}) as Wire));
  }

  return {
    kind: "odoo",

    async pipeline() {
      const briefs = list((await call("GET", "/consult/pipeline")).leads);
      const out: LeadSummary[] = [];
      // The pipeline brief does not carry areas yet, so read each lead for them.
      for (let i = 0; i < briefs.length; i += HYDRATE_BATCH) {
        const batch = briefs.slice(i, i + HYDRATE_BATCH).map(async (brief) => {
          if (Array.isArray(brief.areas)) return withZone(summaryFromWire(brief));
          const full = await lead(num(brief.id));
          const { id, name, zip, stage, stepId, stageSince, zone: z, areas } = full;
          return { id, name, zip, stage, stepId, stageSince, zone: z, areas };
        });
        out.push(...(await Promise.all(batch)));
      }
      return out;
    },

    lead,

    async saveLead(input) {
      const data = await call("POST", "/consult/lead", leadToWire(input));
      const saved = await withZone(leadFromWire((data.lead ?? {}) as Wire));
      const notKept: string[] = [];
      if (saved.name !== input.name) notKept.push("client name");
      if (saved.zip !== input.zip) notKept.push("ZIP");
      return { lead: saved, notKept };
    },

    async setStage(id, stage: ConsultStage) {
      await call("POST", `/consult/lead/${id}/stage`, { stage });
    },

    async saveWalk(id, walk) {
      const data = await call("POST", "/consult/lead", { id, walk_checklist: walk });
      const kept = ((data.lead ?? {}) as Wire).walk_checklist;
      if (!kept || typeof kept !== "object") {
        throw new ConsultError(501, "Odoo has nowhere to keep the walk checklist yet.");
      }
    },

    async modules() {
      return list((await call("GET", "/consult/modules")).modules).map((m) => ({
        id: num(m.id),
        key: text(m.key),
        name: text(m.name),
        objective: text(m.objective),
        sectionTitle: text(m.section_title),
      }));
    },

    async practices() {
      return list((await call("GET", "/consult/practices")).practices).map((p) => ({
        id: num(p.id),
        key: text(p.key),
        name: text(p.name),
        siteNeeds: typeof p.site_needs === "string" ? p.site_needs : null,
        infrastructure: list(p.infrastructure_defaults).map((i) => ({
          key: text(i.key),
          unit: text(i.unit),
          rate: num(i.rate),
        })),
      }));
    },

    async steps() {
      const data = await optional("GET", "/consult/steps");
      return list(data?.steps).map((s) => ({
        id: num(s.id),
        name: text(s.name),
        price: typeof s.price === "number" ? s.price : null,
      }));
    },

    zone,

    async travel(zip): Promise<TravelEstimate> {
      const t = ((await call("GET", `/consult/travel?zip=${encodeURIComponent(zip)}`)).travel ?? {}) as Wire;
      return {
        miles: num(t.miles),
        roundTripMiles: num(t.round_trip_miles),
        hours: num(t.hours),
        billableHours: num(t.billable_hours),
        overnight: t.overnight === true,
      };
    },

    async plans(leadId) {
      const data = await optional("GET", `/consult/lead/${leadId}/plans`);
      if (!data) return { plans: [], readable: false };
      return { plans: list(data.plans).map(planFromWire), readable: true };
    },

    async createPlan(leadId) {
      const data = await call("POST", `/consult/lead/${leadId}/plan`, {});
      return planFromWire((data.plan ?? {}) as Wire);
    },

    async saveSection(leadId, version, key, input, actor) {
      const body: Wire = { actor };
      if (input.body !== undefined) body.body = input.body;
      if (input.editNote !== undefined) body.edit_note = input.editNote;
      if (input.approve) body.approve = true;
      const data = await call(
        "POST",
        `/consult/lead/${leadId}/plan/${version}/section/${encodeURIComponent(key)}`,
        body,
      );
      return { ...sectionFromWire((data.section ?? {}) as Wire), body: input.body ?? "", editNote: input.editNote ?? "" };
    },

    async approvePlan(leadId, version, actor) {
      const data = await optional("POST", `/consult/lead/${leadId}/plan/${version}/approve`, { actor });
      if (!data) throw new ConsultError(501, "Odoo cannot approve a whole plan from here yet.");
      return planFromWire((data.plan ?? {}) as Wire);
    },
  };
}
