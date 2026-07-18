/**
 * E2E tests for Phase 28 — Skill Foundry Sync Status Section (Plan 28-03/28-04).
 *
 * Covers the core Skill Foundry sync user story (D-06, D-07):
 *   - Admin sees the Foundry sync status badge in the Skill editor's Settings tab
 *   - Admin clicks retry-sync and the status badge reflects the updated (synced) state
 *   - Admin can reach the Azure Portal via the portal link
 *   - A brand-new, never-synced skill's editor renders the status section without crashing
 *     (regression guard for the local-only default state)
 *
 * These tests use API mocking via page.route() to drive the retry-sync and portal-url flows
 * without a live Azure AI Foundry dependency. Every mocked GET /api/v1/skills/{id} response
 * uses the shared `buildSkillFixture` builder (LOW-10 review fix) so the mock cannot cause
 * unrelated page regions (Content/Resources/Quality tabs) to render incorrectly.
 */
import { test, expect } from "./coverage-helper";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const authDir = join(dirname(fileURLToPath(import.meta.url)), ".auth");

// ─── Shared fixture builder (LOW-10 fix) ────────────────────────────────
//
// Complete, schema-accurate SkillOut shape (backend/app/schemas/skill.py).
// Every mocked GET /api/v1/skills/{id} response in this file MUST use this
// builder (with overrides) instead of an inline partial object, so a missing
// field can never cause an unrelated tab (Content/Resources/Quality) to
// render incorrectly or throw.

interface SkillFixtureOverrides {
  id: string;
  status?: "draft" | "review" | "published" | "archived" | "failed" | "completed";
  foundry_sync_status?: "none" | "pending" | "synced" | "failed";
  foundry_skill_name?: string;
  foundry_cloud_version?: string;
  foundry_sync_error?: string;
}

function buildSkillFixture(overrides: SkillFixtureOverrides) {
  const now = new Date().toISOString();
  return {
    id: overrides.id,
    name: "E2E Test Skill",
    description: "E2E fixture skill for Foundry sync spec",
    product: "TestProduct",
    status: overrides.status ?? "published",
    tags: "",
    quality_score: 80,
    quality_verdict: "pass",
    structure_check_passed: true,
    conversion_status: null,
    current_version: 1,
    created_by: "e2e-admin",
    created_at: now,
    updated_at: now,
    foundry_skill_name: overrides.foundry_skill_name ?? "",
    foundry_sync_status: overrides.foundry_sync_status ?? "none",
    foundry_cloud_version: overrides.foundry_cloud_version ?? "",
    foundry_sync_error: overrides.foundry_sync_error ?? "",
    therapeutic_area: "",
    compatibility: "",
    metadata_json: "{}",
    content: "# E2E Test SOP\n\nStep 1: Greet the HCP.",
    structure_check_details: "{}",
    quality_details: "{}",
    conversion_error: "",
    resources: [],
    versions: [],
    source_materials: [],
  };
}

// Resolved en-US locale strings (frontend/public/locales/en-US/skill.json `foundry.*` keys).
// Confirmed against skill-foundry-status-section.tsx + skill.json, not assumed.
const LABEL_NOT_SYNCED = "Not Synced";
const LABEL_SYNCED = "Foundry Synced";
const RETRY_BUTTON_NAME = /retry sync/i;
const PORTAL_BUTTON_NAME = /view in azure portal/i;

/**
 * Helper: create a skill via API and navigate to its editor's Settings tab.
 * Mirrors admin-skill-editor.spec.ts's beforeEach + tab-index convention
 * (Content=0, Resources=1, Quality=2, Settings=3).
 */
async function createSkillAndOpenEditor(
  page: import("@playwright/test").Page,
): Promise<string> {
  await page.goto("/admin/skills");
  const resp = await page.evaluate(async () => {
    const r = await fetch("/api/v1/skills", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${localStorage.getItem("access_token")}`,
      },
      body: JSON.stringify({ name: "E2E Test Skill" }),
    });
    return r.json();
  });
  await page.goto(`/admin/skills/${resp.id}/edit`);
  await page.waitForURL(/\/admin\/skills\/[^/]+\/edit/, { timeout: 10000 });
  return resp.id as string;
}

test.describe("Skill Foundry Sync — Editor Status Section", () => {
  test.use({ storageState: join(authDir, "admin.json") });

  test("settings tab shows a Foundry sync status badge", async ({ page }) => {
    // No mocking — real backend, real default foundry_sync_status="none" for a
    // freshly-created skill.
    await createSkillAndOpenEditor(page);

    const settingsTab = page.locator("[role='tab']").nth(3);
    await expect(settingsTab).toBeVisible({ timeout: 10000 });
    await settingsTab.click();
    await page.waitForTimeout(500);

    const statusBadge = page.getByText(LABEL_NOT_SYNCED);
    await expect(statusBadge.first()).toBeVisible({ timeout: 5000 });
  });

  test("retry button calls foundry-sync and the status badge reflects the updated state", async ({
    page,
  }) => {
    const skillId = await createSkillAndOpenEditor(page);

    const syncedFixture = buildSkillFixture({
      id: skillId,
      status: "published",
      foundry_sync_status: "synced",
      foundry_skill_name: "e2e-mock-skill",
      foundry_cloud_version: "1",
    });

    await page.route(`**/api/v1/skills/${skillId}/foundry-sync`, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(syncedFixture),
      }),
    );
    await page.route(`**/api/v1/skills/${skillId}`, async (route) => {
      if (route.request().method() !== "GET") {
        await route.continue();
        return;
      }
      // Post-mutation refetch (query invalidation) must reflect the mocked synced
      // state instead of the real unsynced DB row — full fixture, not a partial
      // object (LOW-10).
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(syncedFixture),
      });
    });

    const settingsTab = page.locator("[role='tab']").nth(3);
    await expect(settingsTab).toBeVisible({ timeout: 10000 });
    await settingsTab.click();
    await page.waitForTimeout(500);

    const retryBtn = page.getByRole("button", { name: RETRY_BUTTON_NAME });
    await expect(retryBtn.first()).toBeVisible({ timeout: 5000 });
    await retryBtn.first().click();
    await page.waitForTimeout(500);

    const statusBadge = page.getByText(LABEL_SYNCED);
    await expect(statusBadge.first()).toBeVisible({ timeout: 5000 });
  });

  test("portal link button opens the Foundry portal URL", async ({ page }) => {
    const skillId = await createSkillAndOpenEditor(page);

    const syncedFixture = buildSkillFixture({
      id: skillId,
      status: "published",
      foundry_sync_status: "synced",
      foundry_skill_name: "e2e-mock-skill",
      foundry_cloud_version: "1",
    });

    await page.route(`**/api/v1/skills/${skillId}`, async (route) => {
      if (route.request().method() !== "GET") {
        await route.continue();
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(syncedFixture),
      });
    });
    await page.route(`**/api/v1/skills/${skillId}/foundry-portal-url`, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          url: "https://ai.azure.com/mock-portal",
          skill_name: "e2e-mock-skill",
          foundry_version: "1",
        }),
      }),
    );

    const settingsTab = page.locator("[role='tab']").nth(3);
    await expect(settingsTab).toBeVisible({ timeout: 10000 });
    await settingsTab.click();
    await page.waitForTimeout(500);

    const portalBtn = page.getByRole("button", { name: PORTAL_BUTTON_NAME });
    await expect(portalBtn.first()).toBeVisible({ timeout: 5000 });

    const [popup] = await Promise.all([
      page.waitForEvent("popup"),
      portalBtn.first().click(),
    ]);
    expect(popup.url()).toContain("ai.azure.com/mock-portal");
  });

  test("retry button is hidden for a never-published (draft) skill (WR-02)", async ({
    page,
  }) => {
    const skillId = await createSkillAndOpenEditor(page);

    const draftFixture = buildSkillFixture({
      id: skillId,
      status: "draft",
      foundry_sync_status: "none",
    });

    await page.route(`**/api/v1/skills/${skillId}`, async (route) => {
      if (route.request().method() !== "GET") {
        await route.continue();
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(draftFixture),
      });
    });

    const settingsTab = page.locator("[role='tab']").nth(3);
    await expect(settingsTab).toBeVisible({ timeout: 10000 });
    await settingsTab.click();
    await page.waitForTimeout(500);

    const statusBadge = page.getByText(LABEL_NOT_SYNCED);
    await expect(statusBadge.first()).toBeVisible({ timeout: 5000 });

    // Backend rejects retry-sync with 422 for non-published skills (skills.py
    // retry_foundry_sync). The button must not be rendered at all so the admin
    // cannot trigger a request that will always fail.
    const retryBtn = page.getByRole("button", { name: RETRY_BUTTON_NAME });
    expect(await retryBtn.count()).toBe(0);

    const notPublishedNote = page.getByText(/foundry sync is only available for published skills/i);
    await expect(notPublishedNote.first()).toBeVisible({ timeout: 5000 });
  });

  test("no-sync regression: status section renders without error for a never-synced skill", async ({
    page,
  }) => {
    const consoleErrors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });

    // No mocking — real backend, second freshly-created skill guards against a
    // crash when foundry_skill_name/foundry_sync_error are empty strings.
    await createSkillAndOpenEditor(page);

    const settingsTab = page.locator("[role='tab']").nth(3);
    await expect(settingsTab).toBeVisible({ timeout: 10000 });
    await settingsTab.click();
    await page.waitForTimeout(500);

    const statusBadge = page.getByText(LABEL_NOT_SYNCED);
    await expect(statusBadge.first()).toBeVisible({ timeout: 5000 });

    const errorBoundaryText = page.getByText(/something went wrong|error boundary/i);
    expect(await errorBoundaryText.count()).toBe(0);
    expect(consoleErrors).toEqual([]);
  });
});
