/**
 * In-memory consult backend for local work and tests (GOL-3576).
 *
 * It serves the whole contract the app is written against, including the
 * parts grove_headless does not expose yet (see README, "Contract gaps").
 * Every client here is made up. Never selected in a production build.
 */
import {
  ConsultError,
  type ConsultBackend,
  type GoalModule,
  type Lead,
  type LeadInput,
  type Plan,
  type PlanSection,
  type Practice,
  type ServiceStep,
} from "./types";
import { ZIP_PATTERN } from "./view";

const MODULES: GoalModule[] = [
  ["lifecycle", "System architecture and lifecycle"],
  ["perennial_integration", "High-value perennial integration"],
  ["soil_and_carbon", "Soil and carbon"],
  ["water_resilience", "Water resilience"],
  ["microclimate_buffering", "Microclimate buffering"],
  ["habitat_and_pest_structuring", "Habitat and pest structuring"],
  ["certification_readiness", "Certification readiness"],
  ["monoculture_transition", "Monoculture transition"],
  ["nutrient_cycling", "Nutrient cycling and closed loop"],
  ["climate_adaptation", "Climate adaptation"],
  ["site_remediation", "Site remediation"],
  ["wildlife_and_deer", "Wildlife and deer"],
].map(([key, name], i) => ({ id: i + 1, key, name, objective: "", sectionTitle: name }));

const infra = (...pairs: [string, string][]) => pairs.map(([key, unit]) => ({ key, unit, rate: 0 }));

const PRACTICES: Practice[] = [
  {
    id: 1,
    key: "homestead_food_forest",
    name: "Homestead food forest",
    siteNeeds: "Any; closest to water and daily access.",
    infrastructure: infra(["drip", "m"], ["deer_fence", "m"], ["paths", "m"]),
  },
  {
    id: 2,
    key: "alley_cropping",
    name: "Alley cropping",
    siteNeeds: "Workable alleys, equipment turning room at headlands.",
    infrastructure: infra(["row_markers", "each"], ["drip", "m"], ["headland_access", "m"]),
  },
  {
    id: 3,
    key: "silvopasture",
    name: "Silvopasture",
    siteNeeds: "Pasture, water for stock, fence lines.",
    infrastructure: infra(["tree_protection", "stem"], ["paddock_fencing", "m"], ["water_points", "each"]),
  },
  {
    id: 4,
    key: "forest_farming",
    name: "Forest farming",
    siteNeeds: "Standing forest with canopy density known; shade-tolerant species only.",
    infrastructure: infra(["access_trails", "m"], ["log_yards", "each"]),
  },
  {
    id: 5,
    key: "mycoforestry",
    name: "Mycoforestry",
    siteNeeds: "Hardwood canopy, moisture, shade.",
    infrastructure: infra(["log_yard", "each"], ["soak_tank", "each"], ["chip_pile", "each"], ["shade_cloth", "m2"]),
  },
  {
    id: 6,
    key: "riparian_buffer",
    name: "Riparian buffer",
    siteNeeds: "Stream or pond edge, flood line mapped.",
    infrastructure: infra(["livestock_exclusion_fence", "m"], ["crossings", "each"]),
  },
  {
    id: 7,
    key: "windbreak_hedgerow",
    name: "Windbreak and hedgerow",
    siteNeeds: "Wind direction and the fields or buildings protected.",
    infrastructure: infra(["protection_stakes", "each"], ["snow_fence", "m"]),
  },
];

const STEPS: ServiceStep[] = [
  { id: 1, name: "Planting consult, 15 minutes", price: 0 },
  { id: 2, name: "Strategy session, per hour", price: 100 },
  { id: 3, name: "Basemaps", price: 150 },
  { id: 4, name: "Whole-property plan", price: 800 },
  { id: 5, name: "Implementation workbook", price: 2000 },
  { id: 6, name: "Stewardship year", price: null },
];

/** USDA zones for the made-up clients' ZIPs, plus a first-digit fallback. */
const ZONES: Record<string, string> = { "37064": "7a", "37174": "7a", "38401": "7a", "37355": "7a", "40330": "6b" };
const ZONE_BY_FIRST_DIGIT = ["6b", "7a", "7b", "8a", "6a", "5a", "6a", "8a", "5b", "9a"];

type Store = { leads: Lead[]; plans: Plan[]; nextId: number };

const daysAgo = (n: number) => new Date(Date.now() - n * 86_400_000).toISOString();

function seed(): Store {
  const area = (
    id: number,
    name: string,
    practiceId: number,
    acres: number,
    flags: Partial<Pick<Lead["areas"][number], "wet" | "poorSoil" | "shade" | "aspect">> = {},
  ) => ({ id, name, practiceId, acres, wet: false, poorSoil: false, shade: false, aspect: "" as const, ...flags });
  const base = { contactName: "", email: "", phone: "", existing: "", walk: {} };
  const leads: Lead[] = [
    {
      ...base,
      id: 101,
      name: "Hollow Creek Farm",
      zip: "37064",
      zone: "7a",
      stage: "site",
      stepId: 4,
      stageSince: daysAgo(6),
      handsOn: "they_install",
      goals: "Fruit and nuts for the house, and shade for the sheep by year five.",
      existing: "Two old apple trees, a spring-fed pond, woven wire on the north line.",
      moduleIds: [1, 3, 4],
      areas: [
        area(1, "House orchard", 1, 0.75, { aspect: "S" }),
        area(2, "Lower pasture", 3, 6, { poorSoil: true, aspect: "E" }),
        area(3, "Creek edge", 6, 1.5, { wet: true, aspect: "flat" }),
      ],
      walk: { access: true, water: true },
    },
    {
      ...base,
      id: 102,
      name: "Ridgeline Homestead",
      zip: "37174",
      zone: "7a",
      stage: "intake",
      stepId: 2,
      stageSince: daysAgo(2),
      handsOn: "plan_only",
      goals: "A windbreak for the garden and something to eat from it.",
      moduleIds: [5],
      areas: [area(4, "North fence line", 7, 0.5, { aspect: "N" })],
    },
    {
      ...base,
      id: 103,
      name: "Sycamore Bend",
      zip: "38401",
      zone: "7a",
      stage: "design",
      stepId: 4,
      stageSince: daysAgo(11),
      handsOn: "we_install",
      goals: "Chestnuts in the hay field without giving up the hay.",
      existing: "Twelve acres in hay, a tractor, no irrigation.",
      moduleIds: [1, 2, 3],
      areas: [
        area(5, "Hay field alleys", 2, 8, { aspect: "S" }),
        area(6, "Woodlot", 4, 3, { shade: true, aspect: "W" }),
      ],
      walk: Object.fromEntries(["access", "water", "wet", "soil", "shade", "wind", "wildlife", "utilities", "photos"].map((k) => [k, true])),
    },
    {
      ...base,
      id: 104,
      name: "Three Oaks Dairy",
      zip: "40330",
      zone: "6b",
      stage: "quote",
      stepId: 5,
      stageSince: daysAgo(19),
      handsOn: "we_install",
      goals: "Shade and browse in the paddocks nearest the barn.",
      moduleIds: [3, 12],
      areas: [area(7, "Barn paddocks", 3, 14, { aspect: "flat" })],
    },
  ];
  const store: Store = { leads, plans: [], nextId: 200 };
  const plan = buildPlan(store, leads[2]);
  plan.sections[0].body =
    "Twelve acres of hay with a three-acre woodlot on the west side. Rows run on contour so the alleys still take the mower.";
  plan.sections[0].status = "edited";
  plan.sections[0].editNote = "Walked it: the alleys need to fit the mower.";
  plan.sections[0].by = "consultant@example.com";
  store.plans.push(plan);
  return store;
}

function buildPlan(store: Store, lead: Lead): Plan {
  const version = store.plans.filter((p) => p.leadId === lead.id).length + 1;
  const places = lead.areas.map((a) => `${a.name} (${a.acres} ac)`).join(", ") || "no areas yet";
  const section = (key: string, title: string, draft: string): PlanSection => ({
    key,
    title,
    status: "generated",
    body: draft,
    draftBody: draft,
    editNote: "",
    by: "",
    approvedAt: null,
  });
  return {
    id: store.nextId++,
    leadId: lead.id,
    version,
    status: "draft",
    sections: [
      section("site_summary", "Site summary", `What we saw at ${lead.name}: ${places}.`),
      ...MODULES.filter((m) => lead.moduleIds.includes(m.id)).map((m) =>
        section(m.key, m.sectionTitle, `${m.name} across ${places}. Write what the client should expect here.`),
      ),
      section("next_steps", "Next steps", "What happens next, who does it, and when."),
    ],
  };
}

const globalStore = globalThis as { __consultFixture?: Store };

function store(): Store {
  return (globalStore.__consultFixture ??= seed());
}

/** Puts the fixture back to its seeded clients. Tests call this between runs. */
export function resetFixture(): void {
  globalStore.__consultFixture = seed();
}

function find(id: number): Lead {
  const lead = store().leads.find((l) => l.id === id);
  if (!lead) throw new ConsultError(404, "That client is not in the pipeline.");
  return lead;
}

function findPlan(leadId: number, version: number): Plan {
  const plan = store().plans.find((p) => p.leadId === leadId && p.version === version);
  if (!plan) throw new ConsultError(404, "That plan version does not exist.");
  return plan;
}

const copy = <T,>(value: T): T => structuredClone(value);

function zoneFor(zip: string): string | null {
  if (!ZIP_PATTERN.test(zip) || zip === "00000") return null;
  return ZONES[zip] ?? ZONE_BY_FIRST_DIGIT[Number(zip[0])];
}

export const fixtureBackend: ConsultBackend = {
  kind: "fixture",

  async pipeline() {
    return copy(store().leads).map((lead) => ({
      id: lead.id,
      name: lead.name,
      zip: lead.zip,
      stage: lead.stage,
      stepId: lead.stepId,
      stageSince: lead.stageSince,
      zone: lead.zone,
      areas: lead.areas.map(({ name, practiceId, acres }) => ({ name, practiceId, acres })),
    }));
  },

  async lead(id) {
    return copy(find(id));
  },

  async saveLead(input: LeadInput) {
    const s = store();
    let lead: Lead;
    if (input.id === undefined) {
      lead = {
        id: s.nextId++,
        name: "",
        zip: "",
        zone: null,
        stage: "intake",
        stepId: null,
        stageSince: new Date().toISOString(),
        contactName: "",
        email: "",
        phone: "",
        handsOn: "",
        goals: "",
        existing: "",
        moduleIds: [],
        areas: [],
        walk: {},
      };
      s.leads.unshift(lead);
    } else {
      lead = find(input.id);
    }
    Object.assign(lead, {
      name: input.name,
      zip: input.zip,
      zone: zoneFor(input.zip),
      handsOn: input.handsOn,
      stepId: input.stepId,
      goals: input.goals,
      existing: input.existing,
      moduleIds: [...input.moduleIds],
      areas: input.areas.map((a) => ({ ...a, id: a.id ?? s.nextId++ })),
    });
    return { lead: copy(lead), notKept: [] };
  },

  async setStage(id, stage) {
    const lead = find(id);
    if (lead.stage !== stage) {
      lead.stage = stage;
      lead.stageSince = new Date().toISOString();
    }
  },

  async saveWalk(id, walk) {
    find(id).walk = { ...walk };
  },

  async modules() {
    return copy(MODULES);
  },

  async practices() {
    return copy(PRACTICES);
  },

  async steps() {
    return copy(STEPS);
  },

  async zone(zip) {
    return zoneFor(zip);
  },

  async travel(zip) {
    if (!zoneFor(zip)) throw new ConsultError(422, "No travel estimate for that ZIP.");
    const miles = 20 + (Number(zip) % 180);
    const hours = Math.round((miles / 45) * 2 * 10) / 10;
    return {
      miles,
      roundTripMiles: miles * 2,
      hours,
      billableHours: Math.max(0, Math.round((hours - 1) * 10) / 10),
      overnight: miles > 150,
    };
  },

  async plans(leadId) {
    find(leadId);
    return { plans: copy(store().plans.filter((p) => p.leadId === leadId)), readable: true };
  },

  async createPlan(leadId) {
    const s = store();
    const plan = buildPlan(s, find(leadId));
    s.plans.push(plan);
    return copy(plan);
  },

  async saveSection(leadId, version, key, input, actor) {
    const plan = findPlan(leadId, version);
    if (plan.status !== "draft") throw new ConsultError(422, "This plan is approved and locked.");
    const section = plan.sections.find((sec) => sec.key === key);
    if (!section) throw new ConsultError(404, "That section is not in this plan.");
    if (input.body !== undefined && input.body !== section.body) {
      section.body = input.body;
      section.status = "edited";
      section.approvedAt = null;
      section.by = actor;
    }
    if (input.editNote !== undefined) section.editNote = input.editNote;
    if (input.approve) {
      section.status = "approved";
      section.approvedAt = new Date().toISOString();
      section.by = actor;
    }
    return copy(section);
  },

  async approvePlan(leadId, version) {
    const plan = findPlan(leadId, version);
    if (plan.sections.some((sec) => sec.status !== "approved")) {
      throw new ConsultError(422, "Approve every section before approving the plan.");
    }
    plan.status = "approved";
    return copy(plan);
  },
};
