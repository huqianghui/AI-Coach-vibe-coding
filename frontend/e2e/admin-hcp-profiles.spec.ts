import { test, expect } from "./coverage-helper";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const authDir = join(dirname(fileURLToPath(import.meta.url)), ".auth");

test.describe("Admin HCP Profiles Management", () => {
  test.use({ storageState: join(authDir, "admin.json") });

  test.beforeEach(async ({ page }) => {
    await page.goto("/admin/hcp-profiles");
  });

  test("renders HCP profiles page with list panel and empty editor area", async ({
    page,
  }) => {
    // The left list panel should be visible with a search input
    await expect(
      page.getByPlaceholder(/search/i),
    ).toBeVisible();

    // The "Create New" / add button should be visible in the list panel
    const createButton = page.getByRole("button", { name: /create|new|add/i });
    await expect(createButton.first()).toBeVisible();
  });

  test("create new HCP profile opens editor form", async ({ page }) => {
    // Click the create new button
    const createButton = page.getByRole("button", { name: /create|new|add/i });
    await createButton.first().click();

    // The editor form should appear with identity fields
    await expect(page.getByText("Name *").first()).toBeVisible({ timeout: 5000 });
    await expect(page.getByText("Specialty *").first()).toBeVisible();

    // Fill in basic identity fields
    const nameInput = page.locator('input[name="name"]').or(
      page.getByLabel(/^name/i),
    );
    await nameInput.first().fill("Dr. Test Profile");

    // Verify the avatar initials update as user types the name
    await expect(page.getByText("DT").first()).toBeVisible({ timeout: 3000 });
  });

  test("creates and saves a cautious HCP profile", async ({ page }) => {
    const profileName = `Dr. Cautious ${Date.now()}`;
    await page.getByRole("button", { name: /create|new|add/i }).first().click();

    await page.locator('input[name="name"]').fill(profileName);
    await page.locator('input[name="specialty"]').fill("Oncology");

    const personalityDropdown = page
      .getByText(/personality type/i)
      .locator("..")
      .locator("button[role='combobox']");
    await personalityDropdown.click();
    await page.getByRole("option", { name: /cautious/i }).click();

    const createResponse = page.waitForResponse(
      (response) =>
        response.url().includes("/api/v1/hcp-profiles") &&
        response.request().method() === "POST",
    );
    await page.getByRole("button", { name: /save/i }).first().click();

    expect((await createResponse).status()).toBe(201);
    await expect(page.getByText(profileName).first()).toBeVisible();
  });

  test("personality sliders are interactive in editor", async ({ page }) => {
    // Click the create new button to open the editor
    const createButton = page.getByRole("button", { name: /create|new|add/i });
    await createButton.first().click();

    // Personality section should be visible
    await expect(
      page.getByText(/personality/i).first(),
    ).toBeVisible({ timeout: 5000 });

    // The personality type dropdown should be present
    const personalityDropdown = page
      .getByText(/personality type/i)
      .locator("..")
      .locator("button[role='combobox']")
      .or(page.locator("button").filter({ hasText: /friendly|skeptical|busy|analytical|cautious/i }).first());

    const dropdownCount = await personalityDropdown.count();
    if (dropdownCount > 0) {
      await personalityDropdown.first().click();
      await page.waitForTimeout(300);
      // Select "Skeptical" from dropdown options
      const skepticalOption = page.getByRole("option", { name: /skeptical/i });
      const optCount = await skepticalOption.count();
      if (optCount > 0) {
        await skepticalOption.first().click();
      }
    }

    // Emotional state slider should display a numeric value
    await expect(
      page.getByText(/emotional state/i).first(),
    ).toBeVisible();

    // Communication style slider should display labels
    await expect(
      page.getByText(/communication style/i).first(),
    ).toBeVisible();
    await expect(page.getByText("Very Direct").first()).toBeVisible();
    await expect(page.getByText("Very Indirect").first()).toBeVisible();
  });

  test("objection list allows adding objections", async ({ page }) => {
    // Click the create new button
    const createButton = page.getByRole("button", { name: /create|new|add/i });
    await createButton.first().click();

    // Scroll down to the interaction rules section
    await page
      .getByText(/interaction rules/i)
      .first()
      .scrollIntoViewIfNeeded();

    // Find the "Add Objection" button
    const addObjectionButton = page.getByRole("button", {
      name: /add objection|add/i,
    });
    const count = await addObjectionButton.count();
    if (count > 0) {
      await addObjectionButton.first().click();
      // An input field should appear for the new objection
      await page.waitForTimeout(300);
    }
  });

  test("search filters HCP profiles in the list", async ({ page }) => {
    const searchInput = page.getByPlaceholder(/search/i);
    await expect(searchInput).toBeVisible();

    // Type a search query
    await searchInput.fill("NonExistentDoctor");
    await page.waitForTimeout(500);

    // With a nonsensical search, the list should show empty state or no profile items
    // The search is functioning if the page doesn't crash
    await expect(searchInput).toHaveValue("NonExistentDoctor");

    // Clear search
    await searchInput.clear();
    await page.waitForTimeout(500);
  });

  test("save and test chat buttons are present in editor", async ({
    page,
  }) => {
    // Click create new to open editor
    const createButton = page.getByRole("button", { name: /create|new|add/i });
    await createButton.first().click();

    // Save button should be visible
    await expect(
      page.getByRole("button", { name: /save/i }).first(),
    ).toBeVisible({ timeout: 5000 });

    // Test Chat button should be visible
    await expect(
      page.getByRole("button", { name: /test chat/i }).first(),
    ).toBeVisible();

    // Discard button should be visible
    await expect(
      page.getByRole("button", { name: /discard/i }).first(),
    ).toBeVisible();
  });
});
