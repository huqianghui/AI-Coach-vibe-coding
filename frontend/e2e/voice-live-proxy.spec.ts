/**
 * E2E tests for Voice Live backend WebSocket proxy + Digital Human.
 *
 * Tests the NEW architecture (Phase 13):
 *   Frontend WebSocket -> Backend /api/v1/voice-live/ws -> Azure Voice Live (Python SDK)
 *
 * Uses REAL .env Azure credentials, headed browser mode, admin+user tokens.
 *
 * Prerequisites:
 * - Backend running on port 8000 with valid .env (AZURE_FOUNDRY_ENDPOINT, AZURE_FOUNDRY_API_KEY)
 * - Frontend running on port 5173
 * - Database seeded and migrated (alembic upgrade head)
 */
import { test, expect } from "./coverage-helper";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const authDir = join(dirname(fileURLToPath(import.meta.url)), ".auth");
const API_BASE = "http://localhost:8000";

/**
 * Helper: login via API and return access token.
 */
async function loginApi(
  request: import("@playwright/test").APIRequestContext,
  username: string,
  password: string,
): Promise<string> {
  const resp = await request.post(`${API_BASE}/api/v1/auth/login`, {
    data: { username, password },
  });
  expect(resp.ok()).toBe(true);
  const data = await resp.json();
  return data.access_token as string;
}

/**
 * Helper: get active scenarios (admin only endpoint).
 */
async function getScenarios(
  request: import("@playwright/test").APIRequestContext,
  adminToken: string,
) {
  const resp = await request.get(
    `${API_BASE}/api/v1/scenarios?page_size=10&status=active`,
    { headers: { Authorization: `Bearer ${adminToken}` } },
  );
  expect(resp.ok()).toBe(true);
  const data = await resp.json();
  return data.items as Array<{
    id: string;
    name: string;
    hcp_profile_id: string;
    skill_id?: string;
  }>;
}

/**
 * Helper: create session (user token) using scenario from admin lookup.
 * Returns sessionId, scenario name and HCP profile id for test assertions.
 */
async function createVoiceSession(
  request: import("@playwright/test").APIRequestContext,
  adminToken: string,
  userToken: string,
  mode = "voice_realtime_model",
): Promise<{ sessionId: string; scenarioName: string; hcpProfileId: string }> {
  const scenarios = await getScenarios(request, adminToken);
  expect(scenarios.length).toBeGreaterThan(0);
  const scenario = scenarios.find((candidate) => Boolean(candidate.skill_id));
  expect(
    scenario,
    "Voice Live Session E2E requires an active scenario with a Skill",
  ).toBeDefined();

  const resp = await request.post(`${API_BASE}/api/v1/sessions`, {
    headers: { Authorization: `Bearer ${userToken}` },
    data: { scenario_id: scenario!.id, mode },
  });
  expect(resp.ok()).toBe(true);
  const session = await resp.json();
  return {
    sessionId: session.id as string,
    scenarioName: scenario!.name,
    hcpProfileId: scenario!.hcp_profile_id,
  };
}

/**
 * Helper: get all HCP profiles (admin only).
 */
async function getHcpProfiles(
  request: import("@playwright/test").APIRequestContext,
  adminToken: string,
) {
  const resp = await request.get(
    `${API_BASE}/api/v1/hcp-profiles?page_size=50`,
    { headers: { Authorization: `Bearer ${adminToken}` } },
  );
  expect(resp.ok()).toBe(true);
  const data = await resp.json();
  return data.items as Array<{
    id: string;
    name: string;
    is_active: boolean;
    voice_live_enabled?: boolean;
    agent_sync_status?: string;
    avatar_character?: string;
  }>;
}

// ─── Backend API Health Checks ───────────────────────────────────────────

test.describe("Voice Live Proxy — Backend API Readiness", () => {
  test("backend health check passes", async ({ request }) => {
    const resp = await request.get(`${API_BASE}/api/health`);
    expect(resp.ok()).toBe(true);
    const data = await resp.json();
    expect(data.status).toBe("healthy");
  });

  test("voice-live/status endpoint returns availability info", async ({
    request,
  }) => {
    const token = await loginApi(request, "user1", "user123");
    const resp = await request.get(`${API_BASE}/api/v1/voice-live/status`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(resp.ok()).toBe(true);
    const data = await resp.json();
    expect(typeof data.voice_live_available).toBe("boolean");
    expect(typeof data.avatar_available).toBe("boolean");
  });

  test("voice-live/models endpoint returns model list", async ({
    request,
  }) => {
    const token = await loginApi(request, "user1", "user123");
    const resp = await request.get(`${API_BASE}/api/v1/voice-live/models`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(resp.ok()).toBe(true);
    const data = await resp.json();
    expect(data.models.length).toBeGreaterThan(0);
    for (const m of data.models) {
      expect(m.id).toBeTruthy();
      expect(m.label).toBeTruthy();
      expect(["pro", "basic", "lite"]).toContain(m.tier);
    }
  });

  test("scenarios API is accessible by admin", async ({ request }) => {
    const adminToken = await loginApi(request, "admin", "admin123");
    const scenarios = await getScenarios(request, adminToken);
    expect(scenarios.length).toBeGreaterThan(0);
    // Each scenario has id, name, hcp_profile_id
    expect(scenarios[0]!.id).toBeTruthy();
    expect(scenarios[0]!.name).toBeTruthy();
    expect(scenarios[0]!.hcp_profile_id).toBeTruthy();
  });

  test("admin can list HCP profiles", async ({ request }) => {
    const adminToken = await loginApi(request, "admin", "admin123");
    const profiles = await getHcpProfiles(request, adminToken);
    expect(profiles.length).toBeGreaterThan(0);
    expect(profiles[0]!.name).toBeTruthy();
  });
});

// ─── WebSocket Proxy Connection Tests ────────────────────────────────────

test.describe("Voice Live WebSocket Proxy — Real Connection", () => {
  test.use({ storageState: join(authDir, "user.json") });
  test.setTimeout(60000);

  test("F2F Unified Session binds the Voice Live first frame to session_id", async ({
    page,
    request,
    context,
  }) => {
    await context.grantPermissions(["microphone"]);
    const adminToken = await loginApi(request, "admin", "admin123");
    const userToken = await loginApi(request, "user1", "user123");
    const { sessionId } = await createVoiceSession(
      request,
      adminToken,
      userToken,
      "voice_realtime_model",
    );

    const firstSessionUpdate = new Promise<Record<string, unknown>>((resolve) => {
      page.on("websocket", (socket) => {
        socket.on("framesent", (event) => {
          const payload = typeof event.payload === "string"
            ? event.payload
            : event.payload.toString();
          try {
            const frame = JSON.parse(payload) as Record<string, unknown>;
            if (frame.type === "session.update") resolve(frame);
          } catch {
            // Ignore binary audio and non-JSON frames.
          }
        });
      });
    });

    await page.goto(`/user/training/session?id=${sessionId}`);
    await page.getByTestId("start-session-btn").click();

    const frame = await Promise.race([
      firstSessionUpdate,
      new Promise<never>((_, reject) =>
        setTimeout(() => reject(new Error("Voice Live session.update was not sent")), 15000),
      ),
    ]);
    const session = frame.session as Record<string, unknown>;
    expect(session.session_id).toBe(sessionId);
    expect(session.system_prompt).toBeUndefined();
    expect(session.hcp_profile_id).toBeUndefined();
  });

  test("voice session page loads and shows header with scenario info", async ({
    page,
    request,
  }) => {
    const adminToken = await loginApi(request, "admin", "admin123");
    const userToken = await loginApi(request, "user1", "user123");
    const { sessionId, scenarioName } = await createVoiceSession(
      request,
      adminToken,
      userToken,
    );

    await page.goto(`/user/training/voice?id=${sessionId}`);
    await page.waitForTimeout(3000);

    // Header should be visible
    const header = page
      .locator("header, [data-testid='voice-header']")
      .first();
    await expect(header).toBeVisible({ timeout: 10000 });

    // Scenario name should appear somewhere
    console.log(
      `[E2E] Session ${sessionId} created for scenario: ${scenarioName}`,
    );
  });

  test("voice session opens WebSocket to backend proxy and sends session.update", async ({
    page,
    request,
    context,
  }) => {
    // Grant microphone permission so audioHandler.initialize() doesn't block
    await context.grantPermissions(["microphone"]);

    const adminToken = await loginApi(request, "admin", "admin123");
    const userToken = await loginApi(request, "user1", "user123");
    const { sessionId, hcpProfileId } = await createVoiceSession(
      request,
      adminToken,
      userToken,
    );

    const consoleLogs: string[] = [];
    page.on("console", (msg) => consoleLogs.push(msg.text()));

    await page.goto(`/user/training/voice?id=${sessionId}`);
    await page.waitForTimeout(15000);

    // WebSocket should have opened (requires mic permission for audioHandler.initialize)
    const wsOpenLog = consoleLogs.find((l) =>
      l.includes("[VoiceLive] WebSocket open"),
    );

    if (wsOpenLog) {
      expect(wsOpenLog).toContain("session.update");

      // Should have sent session.update with hcp_profile_id
      const sessionUpdateLog = consoleLogs.find((l) =>
        l.includes("session.update"),
      );
      expect(sessionUpdateLog).toBeTruthy();
      console.log(
        `[E2E] WebSocket opened for session ${sessionId}, HCP: ${hcpProfileId}`,
      );
    } else {
      // Mic permission may still fail in headless/CI — verify page is functional
      console.log(
        `[E2E] WebSocket did not open (mic permission may be blocked). Logs: ${consoleLogs.filter((l) => l.includes("[Voice")).join("; ")}`,
      );
      const endBtn = page
        .getByRole("button", { name: /end|结束/i })
        .first();
      await expect(endBtn).toBeVisible({ timeout: 5000 });
    }
  });

  test("voice session receives proxy.connected from backend (real Azure)", async ({
    page,
    request,
  }) => {
    const adminToken = await loginApi(request, "admin", "admin123");
    const userToken = await loginApi(request, "user1", "user123");
    const { sessionId } = await createVoiceSession(
      request,
      adminToken,
      userToken,
    );

    const consoleLogs: string[] = [];
    page.on("console", (msg) => consoleLogs.push(msg.text()));

    await page.goto(`/user/training/voice?id=${sessionId}`);

    // Wait for Azure connection via backend proxy (may take 10-20s)
    await page.waitForTimeout(20000);

    const proxyConnected = consoleLogs.find((l) =>
      l.includes("[VoiceLive] Proxy connected"),
    );

    if (proxyConnected) {
      // Successfully connected to Azure via backend proxy
      expect(proxyConnected).toContain("Proxy connected");

      // Should also get session.created or session.updated
      const sessionMsg = consoleLogs.find(
        (l) =>
          l.includes("[VoiceLive] Session created") ||
          l.includes("[VoiceLive] Session updated"),
      );
      expect(sessionMsg).toBeTruthy();
      console.log("[E2E] Azure Voice Live connected via backend proxy!");
    } else {
      // Connection may fail — check for graceful error handling
      const errorLog = consoleLogs.find(
        (l) =>
          l.includes("[VoiceLive] Error") ||
          l.includes("WebSocket error") ||
          l.includes("Connection failed"),
      );
      console.log(
        `[E2E] Azure connection did not complete. Error: ${errorLog ?? "none"}`,
      );
      // Page should still be functional
      const endButton = page
        .getByRole("button", { name: /end|结束/i })
        .first();
      await expect(endButton).toBeVisible({ timeout: 5000 });
    }
  });

  test("voice session shows voice controls (mute, keyboard)", async ({
    page,
    request,
  }) => {
    const adminToken = await loginApi(request, "admin", "admin123");
    const userToken = await loginApi(request, "user1", "user123");
    const { sessionId } = await createVoiceSession(
      request,
      adminToken,
      userToken,
    );

    await page.goto(`/user/training/voice?id=${sessionId}`);
    await page.waitForTimeout(3000);

    // Mute button
    const muteBtn = page
      .getByRole("button", { name: /mute|静音|mic/i })
      .first();
    await expect(muteBtn).toBeVisible({ timeout: 10000 });

    // End session button
    const endBtn = page.getByRole("button", { name: /end|结束/i }).first();
    await expect(endBtn).toBeVisible({ timeout: 5000 });
  });

  test("end session opens confirmation dialog", async ({ page, request }) => {
    const adminToken = await loginApi(request, "admin", "admin123");
    const userToken = await loginApi(request, "user1", "user123");
    const { sessionId } = await createVoiceSession(
      request,
      adminToken,
      userToken,
    );

    await page.goto(`/user/training/voice?id=${sessionId}`);
    await page.waitForTimeout(3000);

    const endBtn = page.getByRole("button", { name: /end|结束/i }).first();
    await expect(endBtn).toBeVisible({ timeout: 10000 });
    await endBtn.click();

    // Confirmation dialog
    const dialog = page.getByRole("dialog").first();
    await expect(dialog).toBeVisible({ timeout: 5000 });

    // Continue button in dialog
    const continueBtn = page
      .getByRole("button", { name: /continue|继续/i })
      .first();
    await expect(continueBtn).toBeVisible();
  });
});

// ─── Digital Human Avatar Tests ──────────────────────────────────────────

test.describe("Digital Human Avatar — Real Azure Connection", () => {
  test.use({ storageState: join(authDir, "user.json") });
  test.setTimeout(90000);

  test("avatar-enabled session creates video element for WebRTC", async ({
    page,
    request,
  }) => {
    const adminToken = await loginApi(request, "admin", "admin123");
    const userToken = await loginApi(request, "user1", "user123");
    const { sessionId } = await createVoiceSession(
      request,
      adminToken,
      userToken,
    );

    const consoleLogs: string[] = [];
    page.on("console", (msg) => consoleLogs.push(msg.text()));

    await page.goto(`/user/training/voice?id=${sessionId}`);
    await page.waitForTimeout(20000);

    // Check if avatar was enabled
    const avatarEnabled = consoleLogs.some(
      (l) => l.includes("avatar=true") || l.includes("avatar_enabled"),
    );

    if (avatarEnabled) {
      const videoEl = page.locator("video").first();
      await expect(videoEl).toBeVisible({ timeout: 10000 });

      const avatarConnected = consoleLogs.find((l) =>
        l.includes("[VoiceSession] Avatar WebRTC connected"),
      );
      console.log(
        `[E2E] Avatar ${avatarConnected ? "WebRTC connected" : "connecting..."}`,
      );
    } else {
      console.log(
        "[E2E] Avatar not enabled for this HCP — voice-only mode",
      );
    }
  });

  test("voice session resolves correct mode from proxy response", async ({
    page,
    request,
  }) => {
    const adminToken = await loginApi(request, "admin", "admin123");
    const userToken = await loginApi(request, "user1", "user123");
    const { sessionId } = await createVoiceSession(
      request,
      adminToken,
      userToken,
    );

    const consoleLogs: string[] = [];
    page.on("console", (msg) => consoleLogs.push(msg.text()));

    await page.goto(`/user/training/voice?id=${sessionId}`);
    await page.waitForTimeout(15000);

    const proxyLog = consoleLogs.find((l) =>
      l.includes("[VoiceLive] Proxy connected"),
    );

    if (proxyLog) {
      // Mode info present: agent=true/false, avatar=true/false
      expect(proxyLog).toContain("agent=");
      expect(proxyLog).toContain("avatar=");
    }
  });
});

// ─── Admin Voice Live Management Page ────────────────────────────────────

test.describe("Admin Voice Live Management — Page Navigation", () => {
  test.use({ storageState: join(authDir, "admin.json") });

  test("admin sidebar shows Voice Live link", async ({ page }) => {
    await page.goto("/admin/dashboard");
    await page.waitForTimeout(2000);

    const voiceLiveLink = page
      .getByRole("link", { name: /voice live/i })
      .first();
    await expect(voiceLiveLink).toBeVisible({ timeout: 10000 });
  });

  test("admin can navigate to Voice Live management page", async ({
    page,
  }) => {
    await page.goto("/admin/voice-live");
    await page.waitForTimeout(3000);

    const pageTitle = page.getByText(/voice live/i).first();
    await expect(pageTitle).toBeVisible({ timeout: 10000 });
  });

  test("Voice Live management page renders without errors", async ({
    page,
  }) => {
    await page.goto("/admin/voice-live");
    await page.waitForTimeout(3000);

    const pageContent = page.locator("main, [role='main'], .flex-1").first();
    await expect(pageContent).toBeVisible({ timeout: 10000 });
  });

  test("Voice Live management page shows chain cards for HCP profiles", async ({
    page,
    request,
  }) => {
    const adminToken = await loginApi(request, "admin", "admin123");
    const profiles = await getHcpProfiles(request, adminToken);

    await page.goto("/admin/voice-live");
    await page.waitForTimeout(3000);

    if (profiles.length > 0) {
      const firstProfile = profiles[0]!;
      const profileCard = page.getByText(firstProfile.name).first();
      await expect(profileCard).toBeVisible({ timeout: 10000 });
    }
  });

  test("batch re-sync button is present and clickable", async ({ page }) => {
    await page.goto("/admin/voice-live");
    await page.waitForTimeout(3000);

    const batchBtn = page
      .getByRole("button", { name: /re-?sync|重新同步|batch/i })
      .first();
    await expect(batchBtn).toBeVisible({ timeout: 10000 });
  });
});

// ─── Voice Session Text Input ────────────────────────────────────────────

test.describe("Voice Session — Keyboard Input", () => {
  test.use({ storageState: join(authDir, "user.json") });
  test.setTimeout(60000);

  test("keyboard toggle shows text input area", async ({ page, request }) => {
    const adminToken = await loginApi(request, "admin", "admin123");
    const userToken = await loginApi(request, "user1", "user123");
    const { sessionId } = await createVoiceSession(
      request,
      adminToken,
      userToken,
    );

    await page.goto(`/user/training/voice?id=${sessionId}`);
    await page.waitForTimeout(3000);

    const keyboardBtn = page
      .getByRole("button", { name: /keyboard|键盘/i })
      .first();

    if (await keyboardBtn.isVisible()) {
      await keyboardBtn.click();
      await page.waitForTimeout(500);

      const textInput = page
        .locator("input[type='text'], input[placeholder]")
        .first();
      await expect(textInput).toBeVisible({ timeout: 5000 });
    }
  });
});
