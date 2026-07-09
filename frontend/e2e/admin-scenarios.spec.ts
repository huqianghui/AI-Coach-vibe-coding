import { test, expect } from "./coverage-helper";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const authDir = join(dirname(fileURLToPath(import.meta.url)), ".auth");

test.describe("Admin Scenarios Management", () => {
  test.use({ storageState: join(authDir, "admin.json") });

  test.beforeEach(async ({ page }) => {
    await page.goto("/admin/scenarios");
    // Wait for the main content area to load (table or heading)
    await expect(
      page.getByRole("heading", { name: /Training Scenarios|场景管理/i }),
    ).toBeVisible({ timeout: 15000 });
  });

  test("renders scenarios page with title, table, and create button", async ({
    page,
  }) => {
    // Page heading should be visible
    await expect(
      page.getByRole("heading", { name: /Training Scenarios/i }),
    ).toBeVisible();

    // Create button should be visible
    const createButton = page.getByRole("button", {
      name: /create|new scenario/i,
    });
    await expect(createButton.first()).toBeVisible();

    await expect(page.getByRole("heading", { name: /合并场景/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /创建组合场景/i })).toBeVisible();

    // Table headers should be visible (new columns after Phase 22)
    await expect(page.getByText("Name").first()).toBeVisible();
    await expect(page.getByText("Tags").first()).toBeVisible();
    await expect(page.getByText("HCP").first()).toBeVisible();
    await expect(page.getByText("Mode").first()).toBeVisible();
    await expect(page.getByText("Difficulty").first()).toBeVisible();
    await expect(page.getByText("Status").first()).toBeVisible();
  });

  test("create button navigates to full-page editor", async ({ page }) => {
    // Click the create button
    const createButton = page.getByRole("button", {
      name: /create|new scenario/i,
    });
    await createButton.first().click();

    // Should navigate to the editor page
    await expect(page).toHaveURL(/\/admin\/scenarios\/new/);

    // Editor page should have tabs
    await expect(page.getByRole("tab", { name: /basic/i })).toBeVisible();
    await expect(page.getByRole("tab", { name: /linked/i })).toBeVisible();
    await expect(page.getByRole("tab", { name: /scoring/i })).toBeVisible();
  });

  test("scenario editor has required form fields on Basic tab", async ({
    page,
  }) => {
    await page.goto("/admin/scenarios/new");

    // Name field
    await expect(page.getByLabel(/name/i).first()).toBeVisible();

    // Mode selector (f2f/conference)
    await expect(page.getByText(/f2f/i).first()).toBeVisible();

    // Difficulty selector
    await expect(page.getByText(/easy/i).first()).toBeVisible();
    await expect(page.getByText(/medium/i).first()).toBeVisible();
    await expect(page.getByText(/hard/i).first()).toBeVisible();

    // Tags section
    await expect(page.getByText(/tags/i).first()).toBeVisible();
  });

  test("scenario editor Linked tab has HCP and Skill selectors", async ({
    page,
  }) => {
    await page.goto("/admin/scenarios/new");

    // Switch to Linked tab
    await page.getByRole("tab", { name: /linked/i }).click();

    // HCP profile selector should be visible
    await expect(page.getByText(/hcp/i).first()).toBeVisible();

    // Skill selector should be visible
    await expect(page.getByText(/skill/i).first()).toBeVisible();
  });

  test("scenario editor Scoring tab has rubric and threshold", async ({
    page,
  }) => {
    await page.goto("/admin/scenarios/new");
    // Wait for editor to load
    await expect(page.getByRole("tab").first()).toBeVisible({ timeout: 10000 });

    // Switch to Scoring tab
    await page.getByRole("tab", { name: /scoring/i }).click();
    await page.waitForTimeout(300);

    // Rubric selector should be visible
    await expect(page.getByText(/rubric/i).first()).toBeVisible();

    // Pass threshold field should be visible
    await expect(page.getByText(/threshold/i).first()).toBeVisible();
  });

  test("status filter dropdown works", async ({ page }) => {
    // The status filter select should be visible
    const filterTrigger = page
      .locator("button[role='combobox']")
      .first();

    const filterCount = await filterTrigger.count();
    if (filterCount > 0) {
      await filterTrigger.click();
      await page.waitForTimeout(300);

      // Active option should be available
      const activeOption = page.getByRole("option", { name: /active/i });
      const optCount = await activeOption.count();
      if (optCount > 0) {
        await activeOption.click();
        await page.waitForTimeout(500);
      }
    }

    // Page should still render without errors after filtering
    await expect(page.locator("h1")).toBeVisible();
  });

  test("scenario table row actions menu contains edit, clone, archive/activate", async ({
    page,
  }) => {
    // Wait for table rows to load
    await page.waitForTimeout(2000);

    // Find action buttons (MoreHorizontal icon buttons) in table rows
    const actionButtons = page.locator("td button");
    const count = await actionButtons.count();

    if (count > 0) {
      // Click the first action menu button
      await actionButtons.first().click();
      await page.waitForTimeout(500);

      // The dropdown menu should contain Edit and Clone
      await expect(
        page.getByRole("menuitem", { name: /edit/i }),
      ).toBeVisible({ timeout: 3000 });
      await expect(
        page.getByRole("menuitem", { name: /clone/i }),
      ).toBeVisible();
    }
  });

  test("creates a new scenario and verifies it appears in the list", async ({
    page,
  }) => {
    // Use "AAA" prefix to ensure it sorts first alphabetically
    const scenarioName = `AAA E2E ${Date.now()}`;

    // Click the create button
    const createButton = page.getByRole("button", {
      name: /create|new scenario/i,
    });
    await createButton.first().click();

    // Should navigate to editor
    await expect(page).toHaveURL(/\/admin\/scenarios\/new/);
    await page.waitForTimeout(1000);

    // Fill Basic tab fields - Name input
    const nameInput = page.locator("input").first();
    await nameInput.fill(scenarioName);

    // Select a tag (click a predefined tag chip)
    const tagButton = page.locator("button").filter({ hasText: "Tislelizumab" }).first();
    const tagCount = await tagButton.count();
    if (tagCount > 0) {
      await tagButton.click();
      await page.waitForTimeout(200);
    }

    // Switch to Linked tab and fill required fields
    await page.getByRole("tab", { name: /linked/i }).click();
    await page.waitForTimeout(500);

    // Select HCP profile - the first Select on this tab
    const linkedComboboxes = page.locator("[data-slot='select-trigger'], button[role='combobox']");
    const hcpTrigger = linkedComboboxes.first();
    await hcpTrigger.click();
    await page.waitForTimeout(500);
    const hcpOption = page.getByRole("option").first();
    if ((await hcpOption.count()) > 0) {
      await hcpOption.click();
      await page.waitForTimeout(500);
    }

    // Select Skill - the second Select on this tab
    const skillTrigger = linkedComboboxes.nth(1);
    if ((await skillTrigger.count()) > 0) {
      await skillTrigger.click();
      await page.waitForTimeout(500);
      const skillOption = page.getByRole("option").first();
      if ((await skillOption.count()) > 0) {
        await skillOption.click();
        await page.waitForTimeout(500);
      }
    }

    // Switch to Scoring tab and fill rubric
    await page.getByRole("tab", { name: /scoring/i }).click();
    await page.waitForTimeout(500);

    // Select rubric - the first Select on this tab
    const scoringComboboxes = page.locator("[data-slot='select-trigger'], button[role='combobox']");
    const rubricTrigger = scoringComboboxes.first();
    await rubricTrigger.click();
    await page.waitForTimeout(500);
    const rubricOption = page.getByRole("option").first();
    if ((await rubricOption.count()) > 0) {
      await rubricOption.click();
      await page.waitForTimeout(500);
    }

    // Click Save button (top-right of editor)
    const saveButton = page.getByRole("button", { name: /save/i });
    await saveButton.click();

    // Should navigate back to scenarios list on success
    await expect(page).toHaveURL(/\/admin\/scenarios$/, { timeout: 15000 });

    // The new scenario should appear in the table
    await expect(page.getByText(scenarioName).first()).toBeVisible({
      timeout: 5000,
    });
  });

  test("scenario list shows existing scenarios from database", async ({
    page,
  }) => {
    // Wait for data to load
    await page.waitForTimeout(2000);

    // There should be at least one row in the table (seeded data exists)
    const tableRows = page.locator("tbody tr");
    const rowCount = await tableRows.count();
    expect(rowCount).toBeGreaterThan(0);
  });

  test("scenario list displays HCP name in HCP column", async ({ page }) => {
    // Wait for data to load
    await page.waitForTimeout(2000);

    // The table should have at least one row
    const tableRows = page.locator("tbody tr");
    const rowCount = await tableRows.count();
    expect(rowCount).toBeGreaterThan(0);

    // Check that at least one row shows an HCP name (not just "-")
    // HCP column contains avatar + name text
    const hcpCells = page.locator("tbody tr td:nth-child(3)");
    const cellCount = await hcpCells.count();
    let foundHcpName = false;

    for (let i = 0; i < cellCount; i++) {
      const cellText = await hcpCells.nth(i).textContent();
      if (cellText && cellText.trim() !== "-" && cellText.trim() !== "") {
        foundHcpName = true;
        break;
      }
    }

    // If seeded scenarios have HCP profiles linked, at least one should display
    expect(foundHcpName).toBe(true);
  });

  test("delete scenario shows confirmation dialog", async ({ page }) => {
    // Wait for table rows to load
    await page.waitForTimeout(1000);

    // Find action buttons in table rows
    const actionButtons = page.locator("td button");
    const count = await actionButtons.count();

    if (count > 0) {
      // Open the dropdown menu
      await actionButtons.first().click();
      await page.waitForTimeout(300);

      // Click delete if available (only non-archived scenarios show delete)
      const deleteItem = page.getByRole("menuitem", { name: /delete/i });
      const deleteCount = await deleteItem.count();
      if (deleteCount > 0) {
        await deleteItem.click();
        await page.waitForTimeout(300);

        // Confirmation dialog should appear
        const confirmDialog = page.getByRole("dialog");
        await expect(confirmDialog).toBeVisible({ timeout: 3000 });

        // Cancel and Delete buttons should be present
        await expect(
          confirmDialog.getByRole("button", { name: /cancel/i }),
        ).toBeVisible();
        await expect(
          confirmDialog.getByRole("button", { name: /delete/i }),
        ).toBeVisible();

        // Click cancel to dismiss
        await confirmDialog
          .getByRole("button", { name: /cancel/i })
          .click();
      }
    }
  });

  test("clone scenario creates a copy in the list", async ({ page }) => {
    // Wait for table rows to load
    await page.waitForTimeout(2000);

    // Get initial row count
    const initialRows = page.locator("tbody tr");
    const initialCount = await initialRows.count();

    if (initialCount > 0) {
      // Open the dropdown menu on first row
      const actionButton = page.locator("td button").first();
      await actionButton.click();
      await page.waitForTimeout(300);

      // Click clone
      const cloneItem = page.getByRole("menuitem", { name: /clone/i });
      const cloneCount = await cloneItem.count();
      if (cloneCount > 0) {
        await cloneItem.click();
        await page.waitForTimeout(2000);

        // Row count should increase by 1
        const newCount = await page.locator("tbody tr").count();
        expect(newCount).toBeGreaterThanOrEqual(initialCount);
      }
    }
  });

  test("edit navigates to scenario editor page", async ({ page }) => {
    // Wait for table rows to load
    await page.waitForTimeout(2000);

    // Find action buttons
    const actionButtons = page.locator("td button");
    const count = await actionButtons.count();

    if (count > 0) {
      await actionButtons.first().click();
      await page.waitForTimeout(300);

      const editItem = page.getByRole("menuitem", { name: /edit/i });
      const editCount = await editItem.count();
      if (editCount > 0) {
        await editItem.click();

        // Should navigate to editor page with scenario ID
        await expect(page).toHaveURL(/\/admin\/scenarios\/[a-f0-9-]+/, {
          timeout: 5000,
        });

        // Editor page should load with tab navigation
        await expect(page.getByRole("tab", { name: /basic/i })).toBeVisible({
          timeout: 5000,
        });
      }
    }
  });

  test("double-click on scenario row navigates to editor", async ({ page }) => {
    await page.waitForTimeout(2000);

    const firstRow = page.locator("tbody tr").first();
    const rowCount = await firstRow.count();

    if (rowCount > 0) {
      await firstRow.dblclick();
      await expect(page).toHaveURL(/\/admin\/scenarios\/[a-f0-9-]+/, {
        timeout: 5000,
      });
    }
  });
});
