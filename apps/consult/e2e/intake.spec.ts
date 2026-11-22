import { expect, test } from "@playwright/test";

test("new client: three areas, modules, save, and the pipeline shows the lead at Intake", async ({ page }) => {
  await page.goto("/pipeline");
  await page.getByRole("link", { name: "New client" }).first().click();
  await expect(page.getByRole("heading", { name: "New client" })).toBeVisible();

  await page.getByLabel("Client", { exact: true }).fill("Walnut Hollow");
  await page.getByLabel("ZIP", { exact: true }).fill("38401");
  await expect(page.getByText(/^Zone \d/)).toBeVisible();
  await page.getByLabel("Service step", { exact: true }).selectOption({ index: 1 });
  await page.getByLabel("How hands-on", { exact: true }).selectOption({ label: "We install" });
  await page.getByLabel("Goals", { exact: true }).fill("Nut trees over pasture, and shade for the creek.");

  const areas = [
    { name: "Hay field alleys", practice: "Alley cropping", acres: "8" },
    { name: "Creek edge", practice: "Riparian buffer", acres: "1.5", wet: true },
    { name: "House orchard", practice: "Homestead food forest", acres: "0.75" },
  ];
  for (const [i, area] of areas.entries()) {
    const n = i + 1;
    await page.getByRole("button", { name: "Add area" }).click();
    await page.getByLabel(`Area ${n} name`, { exact: true }).fill(area.name);
    await page.getByLabel(`Area ${n} practice`, { exact: true }).selectOption({ label: area.practice });
    await page.getByLabel(`Area ${n} acres`, { exact: true }).fill(area.acres);
    if (area.wet) {
      await page.getByRole("row", { name: `Area ${n}` }).getByRole("button", { name: "Wet" }).click();
    }
  }
  await expect(page.getByRole("row", { name: /^Area \d$/ })).toHaveCount(3);

  const modules = page.getByRole("group", { name: "Goal modules" }).getByRole("button");
  await modules.nth(0).click();
  await modules.nth(2).click();
  await expect(page.getByText("2 picked.")).toBeVisible();

  await page.getByRole("button", { name: "Save and go to Site" }).click();
  await expect(page).toHaveURL(/\/client\/\d+\?tab=site$/);
  await expect(page.getByRole("heading", { name: "Walnut Hollow" })).toBeVisible();
  // The wet area carries through to the site map.
  await expect(page.getByRole("img", { name: /Creek edge/ })).toBeVisible();

  await page.goto("/pipeline?stage=intake");
  const row = page.getByRole("row").filter({ hasText: "Walnut Hollow" });
  await expect(row).toBeVisible();
  await expect(row.getByText("Intake", { exact: true })).toBeVisible();
  await expect(row).toContainText("Alley cropping · Riparian buffer · Homestead food forest");
  await expect(row).toContainText("10.25");
});
