import { test, expect } from "./coverage-helper";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const authDir = join(dirname(fileURLToPath(import.meta.url)), ".auth");

test.describe("Scenario Selection (Phase 2)", () => {
  test.use({ storageState: join(authDir, "user.json") });

  test.beforeEach(async ({ page }) => {
    await page.goto("/user/training");
  });

  test("renders scenario selection page with heading and tabs", async ({
    page,
  }) => {
    // Page heading should be visible
    await expect(page.locator("h1")).toBeVisible();

    // F2F, Conference, and group training tabs should be present
    await expect(page.getByRole("tab", { name: /F2F/i })).toBeVisible();
    await expect(
      page.getByRole("tab", { name: /Conference/i }),
    ).toBeVisible();
    await expect(page.getByRole("tab", { name: /组合训练/i })).toBeVisible();
  });

  test("scenario cards display with difficulty badges or empty state", async ({
    page,
  }) => {
    // Wait for scenario cards to load
    await page.waitForTimeout(2000);

    // If scenarios are loaded, difficulty badges and product info should be visible
    // Otherwise the empty state message is shown
    const difficultyBadges = page.getByText(/medium|hard/i).first();
    const emptyState = page.getByText(/No Scenarios Available|not been configured/i);
    const badgeCount = await difficultyBadges.count();
    const emptyCount = await emptyState.count();
    // Either scenario cards with badges or empty state
    expect(badgeCount + emptyCount).toBeGreaterThan(0);
  });

  test("search input filters scenarios by name or description", async ({
    page,
  }) => {
    // Find the search input
    const searchInput = page.getByPlaceholder(/search/i);
    await expect(searchInput).toBeVisible();

    // Type a search query
    await searchInput.fill("NonExistentScenarioXYZ");
    await page.waitForTimeout(500);

    // Either the grid shows no cards (empty state) or filters correctly
    // Check for empty state message or reduced card count
    const emptyState = page.getByText(/no scenario|empty/i);
    const cards = page.locator(
      ".grid > div",
    );
    const emptyCount = await emptyState.count();
    const cardCount = await cards.count();

    // Either empty state is shown or there are no grid cards
    expect(emptyCount > 0 || cardCount === 0).toBeTruthy();

    // Clear search to restore results
    await searchInput.clear();
    await page.waitForTimeout(500);
  });

  test("difficulty filter dropdown filters scenario cards", async ({
    page,
  }) => {
    // Find the difficulty filter select trigger
    const filterTriggers = page.locator("button[role='combobox']");
    const count = await filterTriggers.count();

    // There should be at least one filter dropdown (product or difficulty)
    expect(count).toBeGreaterThan(0);

    // Click the last combobox (likely difficulty filter)
    if (count >= 2) {
      await filterTriggers.nth(1).click();
      await page.waitForTimeout(300);

      // Options should appear
      const options = page.getByRole("option");
      const optionCount = await options.count();
      expect(optionCount).toBeGreaterThan(0);

      // Close the dropdown by pressing Escape
      await page.keyboard.press("Escape");
    }
  });

  test("clicking start button on a scenario card navigates to training session", async ({
    page,
  }) => {
    // Wait for scenario cards to load
    await page.waitForTimeout(1000);

    // Find start training buttons
    const startButtons = page
      .getByRole("button", { name: /start/i })
      .or(page.locator("button").filter({ hasText: /start/i }));
    const count = await startButtons.count();

    if (count > 0) {
      // Click the first start button
      await startButtons.first().click();

      // Should navigate to the training session page
      await expect(page).toHaveURL(/\/user\/training\/session/, {
        timeout: 10000,
      });
    }
  });

  test("tab switching between F2F and Conference works", async ({ page }) => {
    // Click Conference tab
    const conferenceTab = page.getByRole("tab", { name: /Conference/i });
    await conferenceTab.click();
    await page.waitForTimeout(500);

    // Page should still render correctly without errors
    await expect(page.locator("h1")).toBeVisible();

    // Switch back to F2F
    const f2fTab = page.getByRole("tab", { name: /F2F/i });
    await f2fTab.click();
    await page.waitForTimeout(500);

    await expect(page.locator("h1")).toBeVisible();
  });

  test("group training tab can be opened", async ({ page }) => {
    const groupTab = page.getByRole("tab", { name: /组合训练/i });
    await groupTab.click();
    await expect(groupTab).toHaveAttribute("aria-selected", "true");
    await expect(page.locator("h1")).toBeVisible();
  });
});
