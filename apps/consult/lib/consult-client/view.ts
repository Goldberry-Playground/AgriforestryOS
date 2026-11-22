/**
 * Pure helpers shared by the pipeline and the client workspace: labels,
 * validation, the schematic site map and the draft diff. No I/O here.
 */
import {
  ASPECTS,
  CONSULT_STAGES,
  ConsultError,
  HANDS_ON,
  type Area,
  type ConsultStage,
  type HandsOn,
  type InfraDefault,
  type LeadInput,
  type SectionStatus,
} from "./types";

export const STAGE_LABEL: Record<ConsultStage, string> = {
  intake: "Intake",
  site: "Site",
  design: "Design",
  quote: "Quote",
  install: "Install",
  stewardship: "Stewardship",
  archived: "Archived",
};

export const NEXT_ACTION: Record<ConsultStage, string> = {
  intake: "Pick modules and areas, pull the site",
  site: "Walk the site, then draft the plan",
  design: "Edit the plan sections, approve",
  quote: "Send the quote and plan PDF",
  install: "Plant the remaining rows",
  stewardship: "Next visit on the calendar",
  archived: "Nothing",
};

export const HANDS_ON_LABEL: Record<HandsOn, string> = {
  we_install: "We install",
  they_install: "They install, we guide",
  plan_only: "Plan only",
};

export const SECTION_STATUS_LABEL: Record<SectionStatus, string> = {
  generated: "Draft",
  edited: "Edited",
  approved: "Approved",
};

export const ASPECT_LABEL: Record<(typeof ASPECTS)[number], string> = {
  S: "South",
  E: "East",
  W: "West",
  N: "North",
  flat: "Flat",
};

/** The workspace tabs this phase ships, in stage order. */
export const WORKSPACE_TABS = ["intake", "site", "design"] as const;
export type WorkspaceTab = (typeof WORKSPACE_TABS)[number];

export function isStage(value: unknown): value is ConsultStage {
  return typeof value === "string" && (CONSULT_STAGES as readonly string[]).includes(value);
}

export function asTab(value: unknown): WorkspaceTab {
  return (WORKSPACE_TABS as readonly string[]).includes(value as string)
    ? (value as WorkspaceTab)
    : "intake";
}

/** True once the lead has moved past the given workspace tab's stage. */
export function tabDone(tab: WorkspaceTab, stage: ConsultStage): boolean {
  return CONSULT_STAGES.indexOf(stage) > CONSULT_STAGES.indexOf(tab);
}

/** Things to look at on the first walk. Answers are stored on the lead by key. */
export const WALK_ITEMS: { key: string; label: string }[] = [
  { key: "access", label: "Gates and access for a truck and trailer" },
  { key: "water", label: "Water source, pressure and where the lines run" },
  { key: "wet", label: "Wet spots and where water sits after rain" },
  { key: "soil", label: "A soil hole dug in each area" },
  { key: "shade", label: "Canopy and shade through the day" },
  { key: "wind", label: "Prevailing wind and frost pockets" },
  { key: "wildlife", label: "Deer and other wildlife pressure" },
  { key: "utilities", label: "Buried lines and overhead wires" },
  { key: "photos", label: "Photos of each area from two sides" },
];

export function totalAcres(areas: Pick<Area, "acres">[]): number {
  return Math.round(areas.reduce((sum, a) => sum + (Number(a.acres) || 0), 0) * 100) / 100;
}

export function formatAcres(acres: number): string {
  return acres.toLocaleString("en-US", { maximumFractionDigits: 2 });
}

/** Whole days since `since`, or null when the date is missing or unreadable. */
export function daysInStage(since: string | null, now: Date = new Date()): number | null {
  if (!since) return null;
  const then = Date.parse(since);
  if (Number.isNaN(then)) return null;
  return Math.max(0, Math.floor((now.getTime() - then) / 86_400_000));
}

/** `deer_fence` → `deer fence`. */
export function humanizeKey(key: string): string {
  return key.replace(/_/g, " ").trim();
}

export function infraSummary(infra: InfraDefault[]): string {
  return infra.map((i) => `${humanizeKey(i.key)} (per ${humanizeKey(i.unit)})`).join(", ");
}

export const ZIP_PATTERN = /^\d{5}$/;

export function blankArea(): Area {
  return { name: "", practiceId: null, acres: 0, wet: false, poorSoil: false, shade: false, aspect: "" };
}

export type LeadErrors = {
  name?: string;
  zip?: string;
  /** One entry per area row, in order; empty object when the row is fine. */
  areas: { name?: string; practiceId?: string; acres?: string }[];
};

export function validateLead(input: LeadInput): LeadErrors {
  const errors: LeadErrors = { areas: [] };
  if (!input.name.trim()) errors.name = "Add the client's name.";
  if (input.zip && !ZIP_PATTERN.test(input.zip)) errors.zip = "A ZIP is five digits.";
  errors.areas = input.areas.map((area) => {
    const row: LeadErrors["areas"][number] = {};
    if (!area.name.trim()) row.name = "Name this area.";
    if (area.practiceId == null) row.practiceId = "Pick a practice.";
    if (!(area.acres > 0)) row.acres = "Acres must be more than zero.";
    return row;
  });
  return errors;
}

export function hasErrors(errors: LeadErrors): boolean {
  return Boolean(
    errors.name || errors.zip || errors.areas.some((row) => Object.keys(row).length > 0),
  );
}

function str(value: unknown, max: number): string {
  return typeof value === "string" ? value.slice(0, max) : "";
}

function posInt(value: unknown): number | null {
  return typeof value === "number" && Number.isInteger(value) && value > 0 ? value : null;
}

/**
 * Turns an untrusted request body into a LeadInput, dropping anything the
 * form does not send. Throws a 422 ConsultError when it fails validation.
 */
export function parseLeadInput(raw: unknown): LeadInput {
  if (typeof raw !== "object" || raw === null) throw new ConsultError(422, "Send the client as JSON.");
  const body = raw as Record<string, unknown>;
  const areasRaw = Array.isArray(body.areas) ? body.areas.slice(0, 50) : [];
  const input: LeadInput = {
    name: str(body.name, 200).trim(),
    zip: str(body.zip, 10).trim(),
    handsOn: (HANDS_ON as readonly string[]).includes(body.handsOn as string)
      ? (body.handsOn as HandsOn)
      : "",
    stepId: posInt(body.stepId),
    goals: str(body.goals, 5000),
    existing: str(body.existing, 5000),
    moduleIds: Array.isArray(body.moduleIds)
      ? [...new Set(body.moduleIds.map(posInt).filter((id): id is number => id !== null))]
      : [],
    areas: areasRaw.map((item) => {
      const a = (typeof item === "object" && item !== null ? item : {}) as Record<string, unknown>;
      const acres = typeof a.acres === "number" && Number.isFinite(a.acres) ? a.acres : 0;
      return {
        name: str(a.name, 120).trim(),
        practiceId: posInt(a.practiceId),
        acres: Math.round(acres * 100) / 100,
        wet: a.wet === true,
        poorSoil: a.poorSoil === true,
        shade: a.shade === true,
        aspect: (ASPECTS as readonly string[]).includes(a.aspect as string)
          ? (a.aspect as Area["aspect"])
          : "",
      };
    }),
  };
  const id = posInt(body.id);
  if (id !== null) input.id = id;
  const errors = validateLead(input);
  if (hasErrors(errors)) {
    const first =
      errors.name ?? errors.zip ?? errors.areas.flatMap((row) => Object.values(row))[0] ?? "";
    throw new ConsultError(422, first || "That client did not pass the checks.");
  }
  return input;
}

// ── schematic site map ─────────────────────────────────────────────────────

export const MAP_WIDTH = 640;
const MAP_PAD = 16;
const MAP_GAP = 12;
const MAP_MIN_SIDE = 72;
const MAP_MAX_SIDE = 200;

export type MapBlock = { index: number; x: number; y: number; w: number; h: number };
export type MapLayout = { width: number; height: number; blocks: MapBlock[] };

/**
 * Lays areas out as squares whose side grows with the square root of their
 * acreage, wrapped into rows. It is a schematic, not a survey: sizes compare
 * the areas with each other and nothing else.
 */
export function layoutSiteMap(areas: Pick<Area, "acres">[]): MapLayout {
  const biggest = Math.max(1, ...areas.map((a) => Math.sqrt(Math.max(0, a.acres))));
  const blocks: MapBlock[] = [];
  let x = MAP_PAD;
  let y = MAP_PAD;
  let rowHeight = 0;
  areas.forEach((area, index) => {
    const share = Math.sqrt(Math.max(0, area.acres)) / biggest;
    const side = Math.round(Math.max(MAP_MIN_SIDE, share * MAP_MAX_SIDE));
    if (x + side > MAP_WIDTH - MAP_PAD && x > MAP_PAD) {
      x = MAP_PAD;
      y += rowHeight + MAP_GAP;
      rowHeight = 0;
    }
    blocks.push({ index, x, y, w: side, h: side });
    x += side + MAP_GAP;
    rowHeight = Math.max(rowHeight, side);
  });
  return { width: MAP_WIDTH, height: Math.max(200, y + rowHeight + MAP_PAD), blocks };
}

// ── draft diff ─────────────────────────────────────────────────────────────

export type DiffPart = { kind: "same" | "added" | "removed"; text: string };

const DIFF_CELL_LIMIT = 1_500_000;
/** Below this share of kept words the edit is a rewrite, not a touch-up. */
const DIFF_REWRITE_SHARE = 0.5;

const isWord = (token: string) => /\S/.test(token);

/** The draft struck out whole, then the new text on its own line. */
function rewrite(draft: string, body: string): DiffPart[] {
  const parts: DiffPart[] = [];
  if (draft) parts.push({ kind: "removed", text: draft });
  if (draft && body) parts.push({ kind: "same", text: "\n" });
  if (body) parts.push({ kind: "added", text: body });
  return parts;
}

/**
 * Word-level diff from the generated draft to the edited body. When less than
 * half the words survive, word-by-word marks turn to confetti, so the two
 * texts are shown one after the other instead.
 */
export function diffWords(draft: string, body: string): DiffPart[] {
  if (draft === body) return draft ? [{ kind: "same", text: draft }] : [];
  const a = draft.match(/\s+|[^\s]+/g) ?? [];
  const b = body.match(/\s+|[^\s]+/g) ?? [];
  if (a.length * b.length > DIFF_CELL_LIMIT) return rewrite(draft, body);
  const cols = b.length + 1;
  const lcs = new Uint32Array((a.length + 1) * cols);
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      lcs[i * cols + j] =
        a[i] === b[j]
          ? lcs[(i + 1) * cols + j + 1] + 1
          : Math.max(lcs[(i + 1) * cols + j], lcs[i * cols + j + 1]);
    }
  }
  const parts: DiffPart[] = [];
  const push = (kind: DiffPart["kind"], text: string) => {
    const last = parts[parts.length - 1];
    if (last && last.kind === kind) last.text += text;
    else parts.push({ kind, text });
  };
  let i = 0;
  let j = 0;
  let kept = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {
      if (isWord(a[i])) kept++;
      push("same", a[i]);
      i++;
      j++;
    } else if (lcs[(i + 1) * cols + j] >= lcs[i * cols + j + 1]) {
      push("removed", a[i++]);
    } else {
      push("added", b[j++]);
    }
  }
  while (i < a.length) push("removed", a[i++]);
  while (j < b.length) push("added", b[j++]);
  const words = Math.max(a.filter(isWord).length, b.filter(isWord).length);
  if (kept < words * DIFF_REWRITE_SHARE) return rewrite(draft, body);
  return parts;
}
