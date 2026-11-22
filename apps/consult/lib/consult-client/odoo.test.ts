import { describe, expect, it, vi } from "vitest";
import { createOdooBackend, leadToWire, odooConfigFromEnv } from "./odoo";
import { ConsultError, type LeadInput } from "./types";

const config = { url: "https://odoo.test", apiKey: "test-key", tenantId: "nursery" };

type Reply = { status?: number; body: unknown };

/** A fetch stand-in that answers by "METHOD path" and records every call. */
function fakeOdoo(replies: Record<string, Reply>) {
  const calls: { method: string; path: string; headers: Record<string, string>; body: unknown }[] = [];
  const fetcher = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
    const path = String(url).replace("https://odoo.test/grove/api/v1", "");
    const method = init?.method ?? "GET";
    calls.push({
      method,
      path,
      headers: init?.headers as Record<string, string>,
      body: init?.body ? JSON.parse(String(init.body)) : undefined,
    });
    const reply = replies[`${method} ${path}`] ?? { status: 404, body: { error: "not found" } };
    return new Response(JSON.stringify(reply.body), { status: reply.status ?? 200 });
  });
  return { calls, backend: createOdooBackend(config, fetcher as unknown as typeof fetch) };
}

const input: LeadInput = {
  name: "Hollow Creek Farm",
  zip: "37064",
  handsOn: "they_install",
  stepId: 4,
  goals: "Fruit",
  existing: "Pond",
  moduleIds: [1, 3],
  areas: [{ name: "Creek edge", practiceId: 6, acres: 1.5, wet: true, poorSoil: false, shade: false, aspect: "flat" }],
};

const wireLead = {
  id: 7,
  name: "Hollow Creek Farm",
  zip: "37064",
  consult_stage: "intake",
  hands_on: "they_install",
  consult_step_id: 4,
  module_ids: [1, 3],
  goals: "Fruit",
  existing: "Pond",
  areas: [{ id: 1, name: "Creek edge", practice_id: 6, acres: 1.5, wet: true, poor_soil: false, shade: false, aspect: "flat" }],
};

describe("odooConfigFromEnv", () => {
  it("fails loudly without a URL and key", () => {
    expect(() => odooConfigFromEnv({})).toThrowError(ConsultError);
  });

  it("defaults the tenant and trims the URL", () => {
    expect(odooConfigFromEnv({ ODOO_URL: "https://odoo.test/", ODOO_API_KEY: "k" })).toEqual({
      url: "https://odoo.test",
      apiKey: "k",
      tenantId: "nursery",
    });
  });
});

describe("leadToWire", () => {
  it("uses Odoo's field names and starts a new client at intake", () => {
    expect(leadToWire(input)).toEqual({
      name: "Hollow Creek Farm",
      zip: "37064",
      grove_consult_stage: "intake",
      grove_hands_on: "they_install",
      grove_goals: "Fruit",
      grove_existing: "Pond",
      consult_step_id: 4,
      module_ids: [1, 3],
      areas: [{ name: "Creek edge", practice_id: 6, acres: 1.5, wet: true, poor_soil: false, shade: false, aspect: "flat" }],
    });
  });

  it("does not touch the stage of an existing client", () => {
    const wire = leadToWire({ ...input, id: 7 });
    expect(wire.id).toBe(7);
    expect(wire).not.toHaveProperty("grove_consult_stage");
  });
});

describe("odoo backend", () => {
  it("sends the key and tenant on every call", async () => {
    const { backend, calls } = fakeOdoo({ "GET /consult/modules": { body: { modules: [] } } });
    await backend.modules();
    expect(calls[0].headers.Authorization).toBe("Bearer test-key");
    expect(calls[0].headers["X-Grove-Tenant"]).toBe("nursery");
  });

  it("round-trips a save and maps the lead back", async () => {
    const { backend, calls } = fakeOdoo({
      "POST /consult/lead": { body: { lead: wireLead } },
      "GET /zone?zip=37064": { body: { zip: "37064", zone: "7a" } },
    });
    const { lead, notKept } = await backend.saveLead(input);
    expect(calls[0].body).toEqual(leadToWire(input));
    expect(lead).toMatchObject({ id: 7, stage: "intake", zone: "7a", handsOn: "they_install", stepId: 4 });
    expect(lead.areas[0]).toMatchObject({ practiceId: 6, wet: true, poorSoil: false });
    expect(lead.walk).toBeNull();
    expect(notKept).toEqual([]);
  });

  it("says which fields Odoo did not keep", async () => {
    const { backend } = fakeOdoo({ "POST /consult/lead": { body: { lead: { ...wireLead, zip: "" } } } });
    expect((await backend.saveLead(input)).notKept).toEqual(["ZIP"]);
  });

  it("fills pipeline areas from each lead while the brief lacks them", async () => {
    const { backend } = fakeOdoo({
      "GET /consult/pipeline": { body: { leads: [{ id: 7, name: "Hollow Creek Farm", zip: "37064", consult_stage: "site" }] } },
      "GET /consult/lead/7": { body: { lead: { ...wireLead, consult_stage: "site" } } },
      "GET /zone?zip=37064": { body: { zone: "7a" } },
    });
    const [row] = await backend.pipeline();
    expect(row).toMatchObject({ id: 7, stage: "site", zone: "7a", stageSince: null });
    expect(row.areas).toHaveLength(1);
  });

  it("treats routes Odoo does not have yet as not available", async () => {
    const { backend } = fakeOdoo({});
    expect(await backend.steps()).toEqual([]);
    expect(await backend.plans(7)).toEqual({ plans: [], readable: false });
    await expect(backend.approvePlan(7, 1, "a@example.com")).rejects.toMatchObject({ status: 501 });
  });

  it("refuses to pretend the walk checklist was saved", async () => {
    const { backend } = fakeOdoo({ "POST /consult/lead": { body: { lead: wireLead } } });
    await expect(backend.saveWalk(7, { access: true })).rejects.toMatchObject({ status: 501 });
  });

  it("passes Odoo's validation message through and names the off switch", async () => {
    const { backend } = fakeOdoo({
      "POST /consult/lead/7/stage": { status: 422, body: { error: "unknown stage" } },
      "GET /consult/practices": { status: 503, body: {} },
    });
    await expect(backend.setStage(7, "site")).rejects.toMatchObject({ status: 422, message: "unknown stage" });
    await expect(backend.practices()).rejects.toMatchObject({ status: 503 });
  });

  it("never leaks the key into an error", async () => {
    const backend = createOdooBackend(config, (async () => {
      throw new Error("connect ECONNREFUSED Bearer test-key");
    }) as unknown as typeof fetch);
    await expect(backend.modules()).rejects.toMatchObject({ status: 502 });
    await backend.modules().catch((err: Error) => expect(err.message).not.toContain("test-key"));
  });
});
