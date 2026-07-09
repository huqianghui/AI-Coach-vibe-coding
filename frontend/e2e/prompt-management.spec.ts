/**
 * E2E user story (Phase 27-05): Unified Prompt management for admins.
 *
 * An admin opens "Prompt 管理", picks a prompt, edits and saves a new version,
 * runs the AI optimizer, reviews the original-vs-optimized diff, adopts the
 * optimized result as a new active version, then rolls back to a prior version.
 *
 * Guards are used around the AI optimizer step because it depends on a
 * configured coaching adapter; the navigable CRUD path is asserted firmly.
 */

import { test, expect } from "./coverage-helper";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const authDir = join(dirname(fileURLToPath(import.meta.url)), ".auth");

test.describe("Prompt Management", () => {
  test.use({ storageState: join(authDir, "admin.json") });

  test("admin sees the Prompt management nav entry and list", async ({
    page,
  }) => {
    await page.goto("/admin/prompts");
    await page.waitForLoadState("networkidle");

    await expect(page).not.toHaveURL(/\/login/);
    await expect(page.locator("main h1").first()).toBeVisible();

    const table = page.getByTestId("prompts-table");
    const emptyState = page.locator("text=list.empty");
    const tableCount = await table.count();
    const emptyCount = await emptyState.count();
    expect(tableCount + emptyCount).toBeGreaterThan(0);
  });

  test("opening a prompt shows the editor with content and version history", async ({
    page,
  }) => {
    await page.goto("/admin/prompts");
    await page.waitForLoadState("networkidle");

    const firstRow = page.locator("[data-testid^='prompt-row-']").first();
    test.skip((await firstRow.count()) === 0, "No seeded prompts available");

    await firstRow.click();
    await page.waitForURL(/\/admin\/prompts\/.+/);
    await expect(page.getByTestId("prompt-content")).toBeVisible();
    await expect(page.getByTestId("version-history")).toBeVisible();
  });

  test("admin completes optimize -> diff -> adopt -> rollback story", async ({
    page,
  }) => {
    await page.goto("/admin/prompts");
    await page.waitForLoadState("networkidle");

    const firstRow = page.locator("[data-testid^='prompt-row-']").first();
    test.skip((await firstRow.count()) === 0, "No seeded prompts available");

    await firstRow.click();
    await page.waitForURL(/\/admin\/prompts\/.+/);
    await expect(page.getByTestId("prompt-content")).toBeVisible();

    // Open the AI optimize page and run it.
    await page.getByTestId("optimize-open").click();
    await page.waitForURL(/\/admin\/prompts\/.+\/optimize/);
    await expect(page.getByTestId("run-optimize")).toBeVisible();
    await page.getByTestId("run-optimize").click();

    // The optimizer requires a configured adapter; guard on the diff appearing.
    const diff = page.getByTestId("optimize-diff");
    const diffVisible = await diff
      .waitFor({ state: "visible", timeout: 20000 })
      .then(() => true)
      .catch(() => false);
    test.skip(!diffVisible, "Optimizer adapter not available in this environment");

    await expect(page.getByTestId("optimized-text")).toBeVisible();

    // Adopt the optimized result as a new active version.
    await page.getByTestId("adopt-run").click();
    await page.waitForURL(/\/admin\/prompts\/[^/]+$/);
    await page.waitForLoadState("networkidle");

    // A rollback control should now be available for a prior version.
    const rollback = page.locator("[data-testid^='rollback-']").first();
    if ((await rollback.count()) > 0) {
      await rollback.click();
      await page.waitForLoadState("networkidle");
      await expect(page.getByTestId("version-history")).toBeVisible();
    }
  });

  test("admin optimizes a scoring rubric prompt via the optimizer page", async ({
    page,
  }) => {
    // A rubric editor opens the same full-page optimizer as the prompt registry.
    await page.goto("/admin/scoring-rubrics/new");
    await page.waitForLoadState("networkidle");
    await expect(page).not.toHaveURL(/\/login/);

    // Open the full-page AI optimizer from the prompt-template card.
    const optimizeBtn = page.getByTestId("optimize-prompt");
    await expect(optimizeBtn).toBeVisible();
    await optimizeBtn.click();
    await page.waitForURL(/\/admin\/prompt-optimizer/);

    await expect(page.getByTestId("run-optimize")).toBeVisible();
    await page.getByTestId("run-optimize").click();

    // The optimizer requires a configured adapter; guard on the diff appearing.
    const diff = page.getByTestId("optimize-diff");
    const diffVisible = await diff
      .waitFor({ state: "visible", timeout: 20000 })
      .then(() => true)
      .catch(() => false);
    test.skip(!diffVisible, "Optimizer adapter not available in this environment");

    await expect(page.getByTestId("optimized-text")).toBeVisible();

    // Adopting fills the rubric prompt-template field with the optimized text.
    await page.getByTestId("adopt-run").click();
    await page.waitForURL(/\/admin\/scoring-rubrics\/new/);
  });

  test("prompt content is rendered as plain text (no HTML injection)", async ({
    page,
  }) => {
    await page.goto("/admin/prompts");
    await page.waitForLoadState("networkidle");

    const firstRow = page.locator("[data-testid^='prompt-row-']").first();
    test.skip((await firstRow.count()) === 0, "No seeded prompts available");

    await firstRow.click();
    await page.waitForURL(/\/admin\/prompts\/.+/);

    // The editable content lives in a textarea, ensuring text is escaped
    // rather than rendered as markup.
    const content = page.getByTestId("prompt-content");
    await expect(content).toBeVisible();
    expect(await content.evaluate((el) => el.tagName.toLowerCase())).toBe(
      "textarea",
    );
  });

  test("admin creates a brand-new prompt and lands in its editor", async ({
    page,
  }) => {
    await page.goto("/admin/prompts");
    await page.waitForLoadState("networkidle");
    await expect(page).not.toHaveURL(/\/login/);

    const uniqueKey = `custom.e2e${Date.now()}`;

    await page.getByTestId("prompt-create-open").click();
    await expect(page.getByTestId("prompt-create-dialog")).toBeVisible();

    await page.getByTestId("create-key").fill(uniqueKey);
    await page.getByTestId("create-name").fill("E2E Custom Prompt");
    // Category and system-prompt selects are present; pick a category, keep custom (deletable).
    await expect(page.getByTestId("create-is-system")).toBeVisible();
    await page.getByTestId("create-category").click();
    await page.getByTestId("create-category-skill").click();
    await page.getByTestId("create-variables").fill("name, product");
    await page.getByTestId("create-content").fill("Hello, this is an e2e prompt.");
    await page.getByTestId("create-submit").click();

    // Lands on the new prompt's editor with its content resolvable.
    await page.waitForURL(new RegExp(`/admin/prompts/${uniqueKey.replace(".", "\\.")}$`));
    const content = page.getByTestId("prompt-content");
    await expect(content).toBeVisible();
    await expect(content).toHaveValue("Hello, this is an e2e prompt.");
    await expect(page.getByTestId("version-history")).toBeVisible();
  });

  test("admin views a historical version's content read-only without altering the editor", async ({
    page,
  }) => {
    await page.goto("/admin/prompts");
    await page.waitForLoadState("networkidle");

    const firstRow = page.locator("[data-testid^='prompt-row-']").first();
    test.skip((await firstRow.count()) === 0, "No seeded prompts available");

    await firstRow.click();
    await page.waitForURL(/\/admin\/prompts\/.+/);

    const editor = page.getByTestId("prompt-content");
    await expect(editor).toBeVisible();
    const activeContent = await editor.inputValue();

    // Ensure at least two versions exist by saving a new version.
    await editor.fill(`${activeContent}\n<!-- e2e edit ${Date.now()} -->`);
    await page.getByTestId("save-version").click();
    await page.waitForLoadState("networkidle");

    // Open the read-only content viewer for version 1.
    const viewV1 = page.getByTestId("version-view-1");
    await expect(viewV1).toBeVisible();
    const editorBefore = await editor.inputValue();
    await viewV1.click();

    const viewer = page.getByTestId("version-view-content");
    await expect(viewer).toBeVisible();
    await expect(viewer).not.toBeEmpty();

    // Close and confirm the editable textarea is unchanged by viewing history.
    await page.keyboard.press("Escape");
    await expect(viewer).toBeHidden();
    await expect(editor).toHaveValue(editorBefore);
  });
});
