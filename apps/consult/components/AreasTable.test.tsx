// @vitest-environment jsdom
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AreasTable } from "./AreasTable";
import type { Area, Practice } from "@/lib/consult-client/types";

afterEach(cleanup);

const practices: Practice[] = [
  {
    id: 1,
    key: "homestead_food_forest",
    name: "Homestead food forest",
    siteNeeds: "Any; closest to water and daily access.",
    infrastructure: [
      { key: "drip", unit: "m", rate: 0 },
      { key: "deer_fence", unit: "m", rate: 0 },
    ],
  },
  { id: 6, key: "riparian_buffer", name: "Riparian buffer", siteNeeds: null, infrastructure: [] },
];

const orchard: Area = { name: "House orchard", practiceId: 1, acres: 0.75, wet: false, poorSoil: false, shade: false, aspect: "S" };

/** Holds the areas the way the intake form does, and reports every change. */
function Harness({ initial, onChange }: { initial: Area[]; onChange: (areas: Area[]) => void }) {
  const [areas, setAreas] = useState(initial);
  return (
    <AreasTable
      areas={areas}
      practices={practices}
      onChange={(next) => {
        setAreas(next);
        onChange(next);
      }}
    />
  );
}

describe("AreasTable", () => {
  it("explains itself when there are no areas", () => {
    render(<AreasTable areas={[]} practices={practices} onChange={() => {}} />);
    expect(screen.getByText(/No areas yet/)).toBeTruthy();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("shows the practice's site needs and infrastructure read-only", () => {
    render(<AreasTable areas={[orchard]} practices={practices} onChange={() => {}} />);
    const row = screen.getByRole("row", { name: "Area 1" });
    expect(within(row).getByText("Needs: Any; closest to water and daily access.")).toBeTruthy();
    expect(within(row).getByText("Comes with: drip (per m), deer fence (per m)")).toBeTruthy();
    expect(within(row).queryByRole("textbox", { name: /needs/i })).toBeNull();
  });

  it("builds an area from the row's controls", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Harness initial={[]} onChange={onChange} />);

    await user.click(screen.getByRole("button", { name: "Add area" }));
    await user.type(screen.getByLabelText("Area 1 name"), "Creek edge");
    await user.selectOptions(screen.getByLabelText("Area 1 practice"), "Riparian buffer");
    await user.type(screen.getByLabelText("Area 1 acres"), "1.5");
    await user.click(screen.getByRole("button", { name: "Wet" }));
    await user.click(screen.getByRole("button", { name: "Shade" }));
    await user.selectOptions(screen.getByLabelText("Area 1 aspect"), "Flat");

    expect(onChange).toHaveBeenLastCalledWith([
      { name: "Creek edge", practiceId: 6, acres: 1.5, wet: true, poorSoil: false, shade: true, aspect: "flat" },
    ]);
    expect(screen.getByRole("button", { name: "Wet" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("button", { name: "Poor soil" }).getAttribute("aria-pressed")).toBe("false");
  });

  it("removes an area and puts it back on undo", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const second = { ...orchard, name: "Lower pasture" };
    render(<Harness initial={[orchard, second]} onChange={onChange} />);

    await user.click(screen.getByRole("button", { name: "Remove area 1, House orchard" }));
    expect(onChange).toHaveBeenLastCalledWith([second]);
    expect(screen.getByRole("status").textContent).toContain("Removed House orchard.");

    await user.click(screen.getByRole("button", { name: "Undo" }));
    expect(onChange).toHaveBeenLastCalledWith([orchard, second]);
  });

  it("marks the fields that failed validation", () => {
    render(
      <AreasTable
        areas={[{ ...orchard, name: "", acres: 0 }]}
        practices={practices}
        errors={[{ name: "Name this area.", acres: "Acres must be more than zero." }]}
        onChange={() => {}}
      />,
    );
    expect(screen.getByLabelText("Area 1 name").getAttribute("aria-invalid")).toBe("true");
    expect(screen.getByLabelText("Area 1 acres").getAttribute("aria-invalid")).toBe("true");
    expect(screen.getByText("Name this area.")).toBeTruthy();
  });
});
