/**
 * Types for the consult client (GOL-3576, spec §D).
 *
 * These are the app's own shapes. `odoo.ts` maps them to and from the
 * grove_headless C.7 wire format (`/grove/api/v1/consult/*`); `fixture.ts`
 * serves them from memory for local work and tests.
 */

export const CONSULT_STAGES = [
  "intake",
  "site",
  "design",
  "quote",
  "install",
  "stewardship",
  "archived",
] as const;
export type ConsultStage = (typeof CONSULT_STAGES)[number];

export const HANDS_ON = ["we_install", "they_install", "plan_only"] as const;
export type HandsOn = (typeof HANDS_ON)[number];

export const ASPECTS = ["S", "E", "W", "N", "flat"] as const;
export type Aspect = (typeof ASPECTS)[number];

export type Area = {
  id?: number;
  name: string;
  practiceId: number | null;
  acres: number;
  wet: boolean;
  poorSoil: boolean;
  shade: boolean;
  aspect: Aspect | "";
};

export type InfraDefault = { key: string; unit: string; rate: number };

export type Practice = {
  id: number;
  key: string;
  name: string;
  /** What the ground has to offer for this practice. Null when Odoo does not send it yet. */
  siteNeeds: string | null;
  infrastructure: InfraDefault[];
};

export type GoalModule = {
  id: number;
  key: string;
  name: string;
  objective: string;
  sectionTitle: string;
};

export type ServiceStep = { id: number; name: string; price: number | null };

export type TravelEstimate = {
  miles: number;
  roundTripMiles: number;
  hours: number;
  billableHours: number;
  overnight: boolean;
};

/** Walk checklist answers, keyed by the items in `view.ts` WALK_ITEMS. */
export type WalkChecklist = Record<string, boolean>;

export type LeadSummary = {
  id: number;
  name: string;
  zip: string;
  stage: ConsultStage;
  stepId: number | null;
  /** ISO date the lead entered its stage. Null when Odoo does not send it yet. */
  stageSince: string | null;
  zone: string | null;
  areas: Pick<Area, "name" | "practiceId" | "acres">[];
};

export type Lead = Omit<LeadSummary, "areas"> & {
  contactName: string;
  email: string;
  phone: string;
  handsOn: HandsOn | "";
  goals: string;
  existing: string;
  moduleIds: number[];
  areas: Area[];
  /** Null when the backend has nowhere to keep it yet. */
  walk: WalkChecklist | null;
};

/** What the intake form saves. `id` absent means a new client. */
export type LeadInput = {
  id?: number;
  name: string;
  zip: string;
  handsOn: HandsOn | "";
  stepId: number | null;
  goals: string;
  existing: string;
  moduleIds: number[];
  areas: Area[];
};

export type SaveLeadResult = {
  lead: Lead;
  /** Labels of fields the backend accepted the save without keeping. */
  notKept: string[];
};

export const SECTION_STATUSES = ["generated", "edited", "approved"] as const;
export type SectionStatus = (typeof SECTION_STATUSES)[number];

export type PlanStatus = "draft" | "approved" | "sent" | "installed";

export type PlanSection = {
  key: string;
  title: string;
  status: SectionStatus;
  body: string;
  /** The generated draft, kept as it was so edits can be compared with it. */
  draftBody: string;
  editNote: string;
  by: string;
  approvedAt: string | null;
};

export type Plan = {
  id: number;
  leadId: number;
  version: number;
  status: PlanStatus;
  sections: PlanSection[];
};

export type PlansResult = {
  plans: Plan[];
  /** False when the backend can create plans but not read them back yet. */
  readable: boolean;
};

export type SectionInput = { body?: string; editNote?: string; approve?: boolean };

export class ConsultError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ConsultError";
  }
}

/** Everything the app needs from a consult data source. */
export interface ConsultBackend {
  readonly kind: "odoo" | "fixture";
  pipeline(): Promise<LeadSummary[]>;
  lead(id: number): Promise<Lead>;
  saveLead(input: LeadInput): Promise<SaveLeadResult>;
  setStage(id: number, stage: ConsultStage): Promise<void>;
  saveWalk(id: number, walk: WalkChecklist): Promise<void>;
  modules(): Promise<GoalModule[]>;
  practices(): Promise<Practice[]>;
  steps(): Promise<ServiceStep[]>;
  zone(zip: string): Promise<string | null>;
  travel(zip: string): Promise<TravelEstimate>;
  plans(leadId: number): Promise<PlansResult>;
  createPlan(leadId: number): Promise<Plan>;
  saveSection(
    leadId: number,
    version: number,
    key: string,
    input: SectionInput,
    actor: string,
  ): Promise<PlanSection>;
  approvePlan(leadId: number, version: number, actor: string): Promise<Plan>;
}
