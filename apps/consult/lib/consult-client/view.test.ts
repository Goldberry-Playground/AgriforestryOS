import { describe, expect, it } from "vitest";
import { ConsultError, type LeadInput } from "./types";
import {
  daysInStage,
  diffWords,
  hasErrors,
  infraSummary,
  layoutSiteMap,
  parseLeadInput,
  tabDone,
  totalAcres,
  validateLead,
} from "./view";

const input = (patch: Partial<LeadInput> = {}): LeadInput => ({
  name: "Hollow Creek Farm",
  zip: "37064",
  handsOn: "",
  stepId: null,
  goals: "",
  existing: "",
  moduleIds: [],
  areas: [],
  ...patch,
});

const area = { name: "Orchard", practiceId: 1, acres: 2, wet: false, poorSoil: false, shade: false, aspect: "S" as const };

describe("validateLead", () => {
  it("passes a named client with no areas", () => {
    expect(hasErrors(validateLead(input()))).toBe(false);
  });

  it("asks for a name and a five-digit ZIP", () => {
    const errors = validateLead(input({ name: " ", zip: "3706" }));
    expect(errors.name).toBeTruthy();
    expect(errors.zip).toBeTruthy();
  });

  it("flags each incomplete area by row", () => {
    const errors = validateLead(input({ areas: [area, { ...area, name: "", practiceId: null, acres: 0 }] }));
    expect(errors.areas[0]).toEqual({});
    expect(Object.keys(errors.areas[1]).sort()).toEqual(["acres", "name", "practiceId"]);
    expect(hasErrors(errors)).toBe(true);
  });
});

describe("parseLeadInput", () => {
  it("keeps the form's fields and drops everything else", () => {
    const parsed = parseLeadInput({
      ...input({ areas: [area], moduleIds: [3, 3, 4] }),
      id: 12,
      grove_consult_stage: "archived",
      areas: [{ ...area, farmos_land_uuid: "x" }],
    });
    expect(parsed.id).toBe(12);
    expect(parsed.moduleIds).toEqual([3, 4]);
    expect(parsed.areas).toEqual([area]);
    expect(parsed).not.toHaveProperty("grove_consult_stage");
  });

  it("refuses an invalid client with a 422", () => {
    expect(() => parseLeadInput({ name: "" })).toThrowError(ConsultError);
    try {
      parseLeadInput(input({ areas: [{ ...area, acres: -1 }] }));
    } catch (err) {
      expect((err as ConsultError).status).toBe(422);
    }
  });
});

describe("pipeline helpers", () => {
  it("counts whole days in a stage", () => {
    const now = new Date("2026-11-22T12:00:00Z");
    expect(daysInStage("2026-11-16T13:00:00Z", now)).toBe(5);
    expect(daysInStage(null, now)).toBeNull();
    expect(daysInStage("not a date", now)).toBeNull();
  });

  it("sums acres without float drift", () => {
    expect(totalAcres([{ acres: 0.1 }, { acres: 0.2 }])).toBe(0.3);
  });

  it("marks a tab done once the lead is past it", () => {
    expect(tabDone("intake", "site")).toBe(true);
    expect(tabDone("site", "site")).toBe(false);
    expect(tabDone("design", "intake")).toBe(false);
  });

  it("reads infrastructure defaults in plain words", () => {
    expect(infraSummary([{ key: "deer_fence", unit: "m", rate: 0 }])).toBe("deer fence (per m)");
  });
});

describe("layoutSiteMap", () => {
  it("sizes areas by acreage and keeps them inside the frame", () => {
    const layout = layoutSiteMap([{ acres: 1 }, { acres: 16 }, { acres: 4 }, { acres: 9 }, { acres: 9 }]);
    const [small, big] = layout.blocks;
    expect(big.w).toBeGreaterThan(small.w);
    for (const b of layout.blocks) {
      expect(b.x + b.w).toBeLessThanOrEqual(layout.width);
      expect(b.y + b.h).toBeLessThanOrEqual(layout.height);
    }
    expect(new Set(layout.blocks.map((b) => b.y)).size).toBeGreaterThan(1);
  });
});

describe("diffWords", () => {
  it("marks what was removed from and added to the draft", () => {
    expect(diffWords("Plant ten chestnuts in rows.", "Plant twelve chestnuts in rows.")).toEqual([
      { kind: "same", text: "Plant " },
      { kind: "removed", text: "ten" },
      { kind: "added", text: "twelve" },
      { kind: "same", text: " chestnuts in rows." },
    ]);
  });

  it("shows a rewrite as the old text then the new, not word by word", () => {
    expect(diffWords("What we saw at the farm.", "Twelve acres of hay with a woodlot.")).toEqual([
      { kind: "removed", text: "What we saw at the farm." },
      { kind: "same", text: "\n" },
      { kind: "added", text: "Twelve acres of hay with a woodlot." },
    ]);
    expect(diffWords("", "New text.")).toEqual([{ kind: "added", text: "New text." }]);
  });

  it("returns one unchanged part when nothing was edited", () => {
    expect(diffWords("Same.", "Same.")).toEqual([{ kind: "same", text: "Same." }]);
  });
});
