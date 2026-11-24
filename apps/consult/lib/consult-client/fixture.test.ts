import { beforeEach, describe, expect, it } from "vitest";
import { fixtureEnabled } from "./backend";
import { fixtureBackend as fx, resetFixture } from "./fixture";

beforeEach(() => resetFixture());

describe("fixture backend", () => {
  it("is never used in a production build", () => {
    expect(fixtureEnabled({ CONSULT_FIXTURE: "1", NODE_ENV: "production" })).toBe(false);
    expect(fixtureEnabled({ CONSULT_FIXTURE: "1", NODE_ENV: "development" })).toBe(true);
    expect(fixtureEnabled({ NODE_ENV: "development" })).toBe(false);
  });

  it("puts a new client in the pipeline at intake", async () => {
    const { lead } = await fx.saveLead({
      name: "Test Acres",
      zip: "37064",
      handsOn: "",
      stepId: null,
      goals: "",
      existing: "",
      moduleIds: [1],
      areas: [{ name: "Field", practiceId: 2, acres: 3, wet: false, poorSoil: false, shade: false, aspect: "" }],
    });
    const row = (await fx.pipeline()).find((l) => l.id === lead.id);
    expect(row).toMatchObject({ name: "Test Acres", stage: "intake", zone: "7a" });
    expect(row?.areas).toEqual([{ name: "Field", practiceId: 2, acres: 3 }]);
  });

  it("locks a plan only once every section is approved", async () => {
    const plan = await fx.createPlan(102);
    await expect(fx.approvePlan(102, plan.version, "a@example.com")).rejects.toMatchObject({ status: 422 });
    for (const section of plan.sections) {
      await fx.saveSection(102, plan.version, section.key, { approve: true }, "a@example.com");
    }
    expect((await fx.approvePlan(102, plan.version, "a@example.com")).status).toBe("approved");
    await expect(
      fx.saveSection(102, plan.version, plan.sections[0].key, { body: "x" }, "a@example.com"),
    ).rejects.toMatchObject({ status: 422 });
  });

  it("keeps the draft and demotes an approved section when its text changes", async () => {
    const plan = await fx.createPlan(102);
    const { key, draftBody } = plan.sections[0];
    await fx.saveSection(102, plan.version, key, { approve: true }, "a@example.com");
    const edited = await fx.saveSection(102, plan.version, key, { body: "New text.", editNote: "Walked it." }, "b@example.com");
    expect(edited).toMatchObject({ status: "edited", body: "New text.", draftBody, editNote: "Walked it.", by: "b@example.com" });
  });
});
