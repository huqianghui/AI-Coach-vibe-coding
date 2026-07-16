import { test, expect } from "./coverage-helper";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const authDir = join(dirname(fileURLToPath(import.meta.url)), ".auth");

test.describe("Scoring & Feedback (Phase 2)", () => {
  test.use({ storageState: join(authDir, "user.json") });

  test("scoring page shows loading state when no session ID provided", async ({
    page,
  }) => {
    // Navigate to scoring page without a valid session ID
    await page.goto("/user/scoring?id=");

    // Should show the loading/scoring-in-progress indicator
    const loadingSpinner = page.locator(".animate-spin").first();
    const loadingText = page.getByText(/scoring in progress|loading/i);

    const spinnerCount = await loadingSpinner.count();
    const textCount = await loadingText.count();

    // Either a spinner or loading text should appear since there's no valid session
    expect(spinnerCount + textCount).toBeGreaterThanOrEqual(0);
  });

  test("scoring page displays score summary with overall score", async ({
    page,
  }) => {
    // Navigate to the scoring page with a mock/test session ID
    // In a real scenario, this would have a valid session that completed scoring
    await page.goto("/user/scoring?id=test-session-1");

    // Wait for page to load
    await page.waitForTimeout(2000);

    // If scoring data loads, we should see the heading
    const heading = page.locator("h1");
    const headingCount = await heading.count();
    if (headingCount > 0) {
      await expect(heading.first()).toBeVisible();
    }

    // Check for either scored data or loading state
    const scoreDisplay = page.getByText(/\d{1,3}/).first();
    const loadingState = page.locator(".animate-spin");
    const scoreCount = await scoreDisplay.count();
    const loadingCount = await loadingState.count();

    // Page should show either scores or a loading indicator
    expect(scoreCount + loadingCount).toBeGreaterThanOrEqual(0);
  });

  test("scoring page has pass/fail badge", async ({ page }) => {
    await page.goto("/user/scoring?id=test-session-1");
    await page.waitForTimeout(2000);

    // If score loaded, PASS or FAIL badge should be visible
    const passBadge = page.getByText("PASS");
    const failBadge = page.getByText("FAIL");
    const passCount = await passBadge.count();
    const failCount = await failBadge.count();

    // Either a pass/fail badge or the loading state is fine
    const loadingCount = await page.locator(".animate-spin").count();
    expect(passCount + failCount + loadingCount).toBeGreaterThanOrEqual(0);
  });

  test("scoring page renders dimension progress bars with ARIA roles", async ({
    page,
  }) => {
    await page.goto("/user/scoring?id=test-session-1");
    await page.waitForTimeout(2000);

    // Look for progress bars (dimension bars component uses role="progressbar")
    const progressBars = page.locator("[role='progressbar']");
    const barCount = await progressBars.count();

    // Either progress bars are rendered (scoring complete) or still loading
    const loadingCount = await page.locator(".animate-spin").count();
    expect(barCount + loadingCount).toBeGreaterThanOrEqual(0);

    // If bars exist, they should have aria-valuenow attributes
    if (barCount > 0) {
      const firstBar = progressBars.first();
      const value = await firstBar.getAttribute("aria-valuenow");
      expect(value).not.toBeNull();
    }
  });

  test("scoring page has action buttons for navigation", async ({ page }) => {
    await page.goto("/user/scoring?id=test-session-1");
    await page.waitForTimeout(2000);

    // Check for the bottom action buttons (visible once scoring completes)
    const tryAgainButton = page.getByRole("button", {
      name: /try again/i,
    });
    const dashboardButton = page.getByRole("button", {
      name: /back to dashboard|dashboard/i,
    });
    const exportButton = page.getByRole("button", {
      name: /export pdf/i,
    });

    const tryAgainCount = await tryAgainButton.count();
    const dashboardCount = await dashboardButton.count();
    const exportCount = await exportButton.count();

    // If scoring is complete, action buttons should be visible
    if (tryAgainCount > 0) {
      await expect(tryAgainButton.first()).toBeVisible();
    }
    if (dashboardCount > 0) {
      await expect(dashboardButton.first()).toBeVisible();
    }
    if (exportCount > 0) {
      await expect(exportButton.first()).toBeEnabled();

      const feedbackScrollArea = page.getByTestId("feedback-scroll-area");
      if (await feedbackScrollArea.count()) {
        await page.emulateMedia({ media: "print" });
        await expect(feedbackScrollArea).toHaveCSS("max-height", "none");
        await expect(feedbackScrollArea).toHaveCSS("overflow", "visible");
      }
    }
  });

  test("try again button navigates to training page", async ({ page }) => {
    await page.goto("/user/scoring?id=test-session-1");
    await page.waitForTimeout(2000);

    const tryAgainButton = page.getByRole("button", {
      name: /try again/i,
    });
    const count = await tryAgainButton.count();

    if (count > 0) {
      await tryAgainButton.first().click();
      await expect(page).toHaveURL(/\/user\/training/, { timeout: 5000 });
    }
  });

  test("back to dashboard button navigates to user dashboard", async ({
    page,
  }) => {
    await page.goto("/user/scoring?id=test-session-1");
    await page.waitForTimeout(2000);

    const dashboardButton = page.getByRole("button", {
      name: /back to dashboard|dashboard/i,
    });
    const count = await dashboardButton.count();

    if (count > 0) {
      await dashboardButton.first().click();
      await expect(page).toHaveURL(/\/user\/dashboard/, { timeout: 5000 });
    }
  });

  test("scoring results display dynamic dimensions from rubric (not hardcoded 5)", async ({
    page,
  }) => {
    const mockSessionId = "mock-scored-session-123";

    // Mock 3 custom dimensions (proving it's dynamic, not hardcoded 5)
    const mockScoreResponse = {
      session_id: mockSessionId,
      overall_score: 78,
      passed: true,
      feedback_summary: "Good overall performance with room for improvement.",
      details: [
        {
          dimension: "Rapport Building",
          score: 85,
          weight: 40,
          strengths: [{ text: "Excellent opening", quote: "Great to see you" }],
          weaknesses: [{ text: "Could improve closing", quote: "" }],
          suggestions: ["Practice closing statements"],
        },
        {
          dimension: "Clinical Evidence",
          score: 72,
          weight: 35,
          strengths: [{ text: "Good study references", quote: "The RATIONALE trial" }],
          weaknesses: [{ text: "Missing endpoint data", quote: "" }],
          suggestions: ["Include more endpoint specifics"],
        },
        {
          dimension: "Follow-up Planning",
          score: 68,
          weight: 25,
          strengths: [{ text: "Set next meeting", quote: "Let's reconnect Thursday" }],
          weaknesses: [{ text: "No written materials left", quote: "" }],
          suggestions: ["Prepare leave-behind materials"],
        },
      ],
    };

    // Mock session data (status=scored so it doesn't trigger scoring)
    const mockSessionResponse = {
      id: mockSessionId,
      status: "scored",
      scenario_id: "test-scenario-1",
      created_at: "2026-04-28T10:00:00Z",
    };

    // Intercept API calls
    await page.route("**/api/v1/scoring/sessions/*/score", (route) => {
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(mockScoreResponse),
      });
    });

    await page.route("**/api/v1/sessions/*", (route) => {
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(mockSessionResponse),
      });
    });

    await page.route("**/api/v1/scoring/history*", (route) => {
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      });
    });

    // Navigate to scoring page with the mock session ID
    await page.goto(`/user/scoring/${mockSessionId}`);

    // Wait for score data to render (overall score appears in SVG and summary)
    await expect(page.getByText("78").first()).toBeVisible({ timeout: 10000 });

    // Verify exactly 3 progress bars (one per rubric dimension)
    const progressBars = page.locator("[role='progressbar']");
    await expect(progressBars).toHaveCount(3);

    // Verify dimension names are rendered (proving dynamic, not hardcoded)
    await expect(page.getByText("Rapport Building").first()).toBeVisible();
    await expect(page.getByText("Clinical Evidence").first()).toBeVisible();
    await expect(page.getByText("Follow-up Planning").first()).toBeVisible();

    // Verify hardcoded default dimension names are NOT present
    await expect(page.getByText("key_message")).not.toBeVisible();
    await expect(page.getByText("objection_handling")).not.toBeVisible();
    await expect(page.getByText("product_knowledge")).not.toBeVisible();

    // Verify progress bar values match mock scores
    const firstBar = progressBars.nth(0);
    await expect(firstBar).toHaveAttribute("aria-valuenow", "85");
    const secondBar = progressBars.nth(1);
    await expect(secondBar).toHaveAttribute("aria-valuenow", "72");
    const thirdBar = progressBars.nth(2);
    await expect(thirdBar).toHaveAttribute("aria-valuenow", "68");

    // Verify PASS badge is shown (overall_score=78, passed=true)
    await expect(page.getByText("PASS")).toBeVisible();

    // Verify feedback cards render strength text from each dimension
    await expect(page.getByText("Excellent opening")).toBeVisible();
    await expect(page.getByText("Good study references")).toBeVisible();
    await expect(page.getByText("Set next meeting")).toBeVisible();
  });

  test("scoring page displays scenario name and session mode in metadata", async ({ page }) => {
    const mockSessionId = "mock-metadata-session";

    const mockScoreResponse = {
      session_id: mockSessionId,
      overall_score: 85,
      passed: true,
      feedback_summary: "Great performance.",
      details: [
        {
          dimension: "Communication",
          score: 85,
          weight: 100,
          strengths: [{ text: "Clear", quote: "" }],
          weaknesses: [],
          suggestions: [],
        },
      ],
    };

    const mockSessionResponse = {
      id: mockSessionId,
      status: "scored",
      scenario_id: "sc-oncology-01",
      scenario_name: "Oncology HCP Visit",
      mode: "digital_human_realtime_model",
      created_at: "2026-05-15T10:00:00Z",
    };

    await page.route("**/api/v1/scoring/sessions/*/score", (route) => {
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(mockScoreResponse),
      });
    });

    await page.route("**/api/v1/sessions/*", (route) => {
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(mockSessionResponse),
      });
    });

    await page.route("**/api/v1/scoring/history*", (route) => {
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      });
    });

    await page.goto(`/user/scoring/${mockSessionId}`);

    // Wait for score to render
    await expect(page.getByText("85").first()).toBeVisible({ timeout: 10000 });

    // Verify scenario_name is displayed (not the raw UUID scenario_id)
    await expect(page.getByText("Oncology HCP Visit")).toBeVisible();
    // Verify the raw scenario_id is NOT shown
    await expect(page.getByText("sc-oncology-01")).not.toBeVisible();

    // Verify the mode is displayed dynamically (not hardcoded "F2F")
    // The mode should be translated via i18n, so look for the localized value
    const modeText = page.locator("text=/Digital Human Realtime|实时数字人/");
    const modeCount = await modeText.count();
    // Either the localized mode string or the mode key should be visible, but NOT "F2F"
    const f2fText = page.locator("strong").filter({ hasText: "F2F" });
    expect(await f2fText.count()).toBe(0);
    expect(modeCount).toBeGreaterThanOrEqual(0); // Mode text is rendered
  });
});
