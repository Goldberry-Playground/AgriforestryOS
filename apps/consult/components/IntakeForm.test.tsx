// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { IntakeForm } from "./IntakeForm";
import { ConsultError, type GoalModule, type Lead, type LeadInput, type Practice, type ServiceStep } from "@/lib/consult-client/types";

const router = { push: vi.fn(), replace: vi.fn(), refresh: vi.fn() };
vi.mock("next/navigation", () => ({ useRouter: () => router }));

const api = vi.hoisted(() => ({
  zone: vi.fn(),
  travel: vi.fn(),
  saveLead: vi.fn(),
}));
vi.mock("@/lib/consult-client/browser", () => ({
  consultApi: api,
  errorMessage: (err: unknown) => (err instanceof Error ? err.message : "Something went wrong."),
}));

const modules: GoalModule[] = [
  { id: 1, key: "lifecycle", name: "System architecture and lifecycle", objective: "", sectionTitle: "" },
  { id: 3, key: "soil_and_carbon", name: "Soil and carbon", objective: "", sectionTitle: "" },
];
const practices: Practice[] = [
  { id: 2, key: "alley_cropping", name: "Alley cropping", siteNeeds: "Workable alleys.", infrastructure: [] },
];
const steps: ServiceStep[] = [{ id: 4, name: "Whole-property plan", price: 800 }];

/** Answers a save the way the BFF does: the lead as stored, with an id. */
function echoSave(input: LeadInput) {
  const lead: Lead = {
    ...input,
    id: input.id ?? 501,
    stage: "intake",
    stageSince: null,
    zone: "7a",
    contactName: "",
    email: "",
    phone: "",
    walk: {},
  };
  return Promise.resolve({ lead, notKept: [] });
}

beforeEach(() => {
  api.zone.mockResolvedValue({ zone: "7a" });
  api.travel.mockResolvedValue({
    travel: { miles: 40, roundTripMiles: 80, hours: 1.8, billableHours: 0.8, overnight: false },
  });
  api.saveLead.mockImplementation(echoSave);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const view = (lead: Lead | null = null) =>
  render(<IntakeForm lead={lead} modules={modules} practices={practices} steps={steps} />);

describe("IntakeForm", () => {
  it("round-trips a new client: fill, save, and show what was stored", async () => {
    const user = userEvent.setup();
    view();

    await user.type(screen.getByLabelText("Client"), "Sycamore Bend");
    await user.type(screen.getByLabelText("ZIP"), "38401");
    await user.selectOptions(screen.getByLabelText("Service step"), "Whole-property plan ($800)");
    await user.selectOptions(screen.getByLabelText("How hands-on"), "We install");
    await user.type(screen.getByLabelText("Goals"), "Chestnuts in the hay field.");
    await user.type(screen.getByLabelText("What they already have"), "A tractor.");
    await user.click(screen.getByRole("button", { name: "Soil and carbon" }));
    await user.click(screen.getByRole("button", { name: "Add area" }));
    await user.type(screen.getByLabelText("Area 1 name"), "Hay field alleys");
    await user.selectOptions(screen.getByLabelText("Area 1 practice"), "Alley cropping");
    await user.type(screen.getByLabelText("Area 1 acres"), "8");

    await waitFor(() => expect(screen.getByText("Zone 7a")).toBeTruthy());
    expect(screen.getByText("80 mi round trip · 0.8 h billable")).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(api.saveLead).toHaveBeenCalledTimes(1));
    expect(api.saveLead).toHaveBeenCalledWith({
      id: undefined,
      name: "Sycamore Bend",
      zip: "38401",
      handsOn: "we_install",
      stepId: 4,
      goals: "Chestnuts in the hay field.",
      existing: "A tractor.",
      moduleIds: [3],
      areas: [{ name: "Hay field alleys", practiceId: 2, acres: 8, wet: false, poorSoil: false, shade: false, aspect: "" }],
    });
    await waitFor(() => expect(screen.getByText("Saved.")).toBeTruthy());
    expect(router.replace).toHaveBeenCalledWith("/client/501");
    // The form now holds the stored lead, so nothing typed was lost on the way back.
    expect((screen.getByLabelText("Client") as HTMLInputElement).value).toBe("Sycamore Bend");
    expect((screen.getByLabelText("Area 1 name") as HTMLInputElement).value).toBe("Hay field alleys");
    expect(screen.getByRole("button", { name: "Soil and carbon" }).getAttribute("aria-pressed")).toBe("true");
  });

  it("goes to Site after Save and go to Site", async () => {
    const user = userEvent.setup();
    view();
    await user.type(screen.getByLabelText("Client"), "Sycamore Bend");
    await user.click(screen.getByRole("button", { name: "Save and go to Site" }));
    await waitFor(() => expect(router.push).toHaveBeenCalledWith("/client/501?tab=site"));
  });

  it("does not save an incomplete client and says what to fix", async () => {
    const user = userEvent.setup();
    view();
    await user.type(screen.getByLabelText("ZIP"), "384");
    await user.click(screen.getByRole("button", { name: "Add area" }));
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(api.saveLead).not.toHaveBeenCalled();
    expect(screen.getByText("Add the client's name.")).toBeTruthy();
    expect(screen.getByText("A ZIP is five digits.")).toBeTruthy();
    expect(screen.getByText(/5 things need fixing/)).toBeTruthy();
    expect(screen.getByLabelText("Client").getAttribute("aria-invalid")).toBe("true");
  });

  it("keeps the entries when the save fails", async () => {
    api.saveLead.mockRejectedValueOnce(new ConsultError(502, "Odoo did not answer. Try again in a moment."));
    const user = userEvent.setup();
    view();
    await user.type(screen.getByLabelText("Client"), "Sycamore Bend");
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(screen.getByText(/Odoo did not answer/)).toBeTruthy());
    expect((screen.getByLabelText("Client") as HTMLInputElement).value).toBe("Sycamore Bend");
    expect(router.replace).not.toHaveBeenCalled();
  });

  it("says so when Odoo saved the client but dropped a field", async () => {
    api.saveLead.mockImplementationOnce(async (input: LeadInput) => ({
      ...(await echoSave(input)),
      notKept: ["ZIP"],
    }));
    const user = userEvent.setup();
    view();
    await user.type(screen.getByLabelText("Client"), "Sycamore Bend");
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(screen.getByText("Saved, but Odoo did not keep the ZIP yet.")).toBeTruthy());
  });
});
