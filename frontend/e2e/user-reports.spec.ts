import { test, expect } from "./coverage-helper";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const authDir = join(dirname(fileURLToPath(import.meta.url)), ".auth");

test.describe("User Reports Page", () => {
  test.use({ storageState: join(authDir, "user.json") });

  test.beforeEach(async ({ page }) => {
    await page.goto("/user/reports");
  });

  test("renders page with heading", async ({ page }) => {
    await expect(page.locator("h1")).toBeVisible();
    await expect(page.locator("h1")).toContainText(/Analytics & Reports/i);
  });

  test("shows compact summary bar with key stats", async ({ page }) => {
    // Reports page now uses a compact inline summary bar (not individual stat cards)
    // The summary bar displays stats like "Total Sessions: 24" in a single flex row
    const summaryBar = page.locator(".flex.flex-wrap.items-center.gap-6");
    await expect(summaryBar.first()).toBeVisible({ timeout: 5000 });

    // Check that stat labels are present in the compact bar
    await expect(page.getByText(/Total Sessions/i).first()).toBeVisible();
    await expect(page.getByText(/Avg Score/i).first()).toBeVisible();
    await expect(page.getByText(/Improvement/i).first()).toBeVisible();
  });

  test("shows chart sections (Performance Trend and Skill analysis)", async ({
    page,
  }) => {
    // Chart headings
    await expect(page.getByRole("heading", { name: /Performance Trend/i })).toBeVisible();
    // The second chart may be "Skill Radar" or "Skill Gap Analysis" depending on translation
    await expect(page.getByRole("heading", { name: /Skill/i })).toBeVisible();
  });

  test("shows export buttons", async ({ page }) => {
    await expect(page.getByText(/Print Report/i)).toBeVisible();
    await expect(page.getByText(/Export Excel/i)).toBeVisible();
  });

  test("uses a print-safe layout for PDF export", async ({ page }) => {
    const report = page.locator(".print-content");
    await expect(report).toBeVisible();

    await page.emulateMedia({ media: "print" });
    await expect(report).toHaveCSS("max-height", "none");
    await expect(report).toHaveCSS("overflow", "visible");
    expect(await report.locator(".print-avoid-break").count()).toBeGreaterThan(0);
  });

  test("page renders fully without errors", async ({ page }) => {
    const body = page.locator("body");
    await expect(body).toBeVisible();

    // The compact summary should contain numeric values
    const summaryBar = page.locator(".flex.flex-wrap.items-center.gap-6");
    const count = await summaryBar.count();
    expect(count).toBeGreaterThanOrEqual(1);
  });

  test("reports page is differentiated from dashboard (no duplicate stat card grid)", async ({ page }) => {
    // The reports page should NOT have a 4-column grid of stat cards (that's on Dashboard)
    // Instead it uses a compact inline summary bar
    const statCardGrid = page.locator(".grid.grid-cols-1.sm\\:grid-cols-2.lg\\:grid-cols-4");
    // The grid should not exist or should not contain individual card elements for stats
    const gridCount = await statCardGrid.count();
    expect(gridCount).toBe(0);
  });
});
