/**
 * Browser-side consult client. It only ever calls this app's own BFF routes
 * (`/api/consult/*`); the Odoo key stays on the server.
 */
import {
  ConsultError,
  type ConsultStage,
  type LeadInput,
  type Plan,
  type PlanSection,
  type PlansResult,
  type SaveLeadResult,
  type SectionInput,
  type TravelEstimate,
  type WalkChecklist,
} from "./types";

async function request<T>(method: "GET" | "POST", path: string, body?: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`/api/consult/${path}`, {
      method,
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ConsultError(0, "You look to be offline. Nothing was saved.");
  }
  const data = (await res.json().catch(() => ({}))) as { error?: string };
  if (!res.ok) throw new ConsultError(res.status, data.error || "Something went wrong. Try again.");
  return data as T;
}

const q = (zip: string) => `zip=${encodeURIComponent(zip)}`;

export const consultApi = {
  zone: (zip: string) => request<{ zone: string | null }>("GET", `zone?${q(zip)}`),
  travel: (zip: string) => request<{ travel: TravelEstimate }>("GET", `travel?${q(zip)}`),
  saveLead: (input: LeadInput) => request<SaveLeadResult>("POST", "lead", input),
  setStage: (id: number, stage: ConsultStage) => request<{ ok: true }>("POST", `lead/${id}/stage`, { stage }),
  saveWalk: (id: number, walk: WalkChecklist) => request<{ ok: true }>("POST", `lead/${id}/walk`, { walk }),
  plans: (id: number) => request<PlansResult>("GET", `lead/${id}/plans`),
  createPlan: (id: number) => request<{ plan: Plan }>("POST", `lead/${id}/plan`, {}),
  saveSection: (id: number, version: number, key: string, input: SectionInput) =>
    request<{ section: PlanSection }>(
      "POST",
      `lead/${id}/plan/${version}/section/${encodeURIComponent(key)}`,
      input,
    ),
  approvePlan: (id: number, version: number) =>
    request<{ plan: Plan }>("POST", `lead/${id}/plan/${version}/approve`, {}),
};

export function errorMessage(err: unknown): string {
  return err instanceof ConsultError ? err.message : "Something went wrong. Try again.";
}
