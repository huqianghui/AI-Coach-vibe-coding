import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "./coverage-helper";

const authDir = join(dirname(fileURLToPath(import.meta.url)), ".auth");
const scenarioId = "scenario-phase-31-skill";
const textSessionId = "session-phase-31-text";
const voiceSessionId = "session-phase-31-voice";

const forbiddenAuthorityKeys = [
  "conversation_id",
  "agent_name",
  "agent_version",
  "skill_id",
  "skill_version_id",
  "sop_snapshot",
  "context",
  "tools",
  "tool_choice",
  "instructions",
  "additional_instructions",
  "previous_response_id",
  "response_id",
  "turn_key",
  "idempotency_key",
  "provider_operation_id",
];

const scenario = {
  id: scenarioId,
  name: "Phase 31 Skill Context Scenario",
  description: "Browser-contract fixture for server-owned Session context",
  tags: ["product:test"],
  mode: "f2f",
  difficulty: "medium",
  status: "active",
  hcp_profile_id: "hcp-phase-31",
  hcp_profile: {
    id: "hcp-phase-31",
    name: "Dr. Context",
    specialty: "Oncology",
    personality_type: "analytical",
    avatar_enabled: true,
    voice_live_instance: { enabled: true },
  },
  key_messages: ["Server-owned context"],
  skill_id: "skill-phase-31",
  skill_version_id: "skill-version-phase-31",
  rubric_id: "rubric-phase-31",
  pass_threshold: 70,
  created_by: "admin-phase-31",
  created_at: "2026-08-06T00:00:00Z",
  updated_at: "2026-08-06T00:00:00Z",
};

function session(id: string, mode: string) {
  return {
    id,
    user_id: "user-phase-31",
    scenario_id: scenarioId,
    scenario_name: scenario.name,
    status: "in_progress",
    started_at: "2026-08-06T00:00:00Z",
    completed_at: null,
    duration_seconds: null,
    key_messages_status: [],
    overall_score: null,
    passed: null,
    mode,
    agent_name: "server-audit-only",
    agent_version: "31",
    message_count: 0,
    created_at: "2026-08-06T00:00:00Z",
    updated_at: "2026-08-06T00:00:00Z",
  };
}

async function installCommonRoutes(page: import("@playwright/test").Page) {
  await page.route("**/api/v1/auth/me", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "user-phase-31",
        username: "user1",
        email: "user1@example.com",
        role: "user",
        is_active: true,
      }),
    }),
  );
  await page.route(`**/api/v1/scenarios/${scenarioId}`, (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(scenario) }),
  );
  await page.route("**/api/v1/config/features", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        features: {
          avatar_enabled: true,
          voice_enabled: true,
          realtime_voice_enabled: true,
          conference_enabled: false,
          voice_live_enabled: true,
          default_voice_mode: "text_only",
          region: "global",
        },
      }),
    }),
  );
}

function sse(text: string, code = "SESSION_TURN_ACCEPTED") {
  return [
    "event: state",
    `data: {"code":"${code}","status":"in_progress"}`,
    "",
    "event: text",
    `data: ${text}`,
    "",
    "event: key_messages",
    "data: []",
    "",
    "event: done",
    "data: ",
    "",
  ].join("\n");
}

test.describe("Unified Training server-owned Skill context", () => {
  test.use({ storageState: join(authDir, "user.json") });

  test("completes two text turns with exact message-only browser payloads", async ({ page }) => {
    await installCommonRoutes(page);
    await page.route(`**/api/v1/sessions/${textSessionId}`, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(session(textSessionId, "text")),
      }),
    );
    const requestBodies: Record<string, unknown>[] = [];
    await page.route(`**/api/v1/sessions/${textSessionId}/message`, async (route) => {
      requestBodies.push(route.request().postDataJSON() as Record<string, unknown>);
      const turn = requestBodies.length;
      await route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: sse(turn === 1 ? "Step N guided response" : "Step N plus 1 guided response"),
      });
    });

    await page.goto(`/user/training/session?id=${textSessionId}`);
    await page.getByTestId("text-input").fill("First user turn");
    await page.getByTestId("send-btn").click();
    await expect(page.getByTestId("chat-area")).toContainText("Step N guided response");
    await page.getByTestId("text-input").fill("Second user turn");
    await page.getByTestId("send-btn").click();
    await expect(page.getByTestId("chat-area")).toContainText("Step N plus 1 guided response");

    expect(requestBodies).toEqual([
      { message: "First user turn" },
      { message: "Second user turn" },
    ]);
    for (const body of requestBodies) {
      expect(Object.keys(body)).toEqual(["message"]);
      for (const key of forbiddenAuthorityKeys) expect(body).not.toHaveProperty(key);
    }
  });

  test("explicitly resumes a disconnected turn and renders one assistant result", async ({ page }) => {
    await installCommonRoutes(page);
    await page.route(`**/api/v1/sessions/${textSessionId}`, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(session(textSessionId, "text")),
      }),
    );
    let requestCount = 0;
    await page.route(`**/api/v1/sessions/${textSessionId}/message`, async (route) => {
      requestCount += 1;
      if (requestCount === 1) {
        await route.abort("connectionreset");
        return;
      }
      expect(route.request().postDataJSON()).toEqual({ message: "Reconnect turn" });
      await route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: sse("Committed winner", "SESSION_TURN_RESUMED"),
      });
    });

    await page.goto(`/user/training/session?id=${textSessionId}`);
    await page.getByTestId("text-input").fill("Reconnect turn");
    await page.getByTestId("send-btn").click();
    await expect(page.getByTestId("resume-turn-btn")).toBeVisible();
    expect(requestCount).toBe(1);
    await page.getByTestId("resume-turn-btn").click();

    await expect(page.getByTestId("chat-area")).toContainText("Committed winner");
    await expect(page.getByText("Committed winner")).toHaveCount(1);
    expect(requestCount).toBe(2);
  });

  test("starts Skill-bound digital human with only the trusted Session identifier", async ({ page, context }) => {
    await installCommonRoutes(page);
    await context.grantPermissions(["microphone"]);
    await page.addInitScript(() => {
      const stream = new MediaStream();
      Object.defineProperty(navigator, "mediaDevices", {
        configurable: true,
        value: { getUserMedia: async () => stream },
      });

      class FakeAudioNode {
        connect() {
          return this;
        }
      }
      class FakeAudioContext {
        sampleRate = 24_000;
        destination = new FakeAudioNode();
        audioWorklet = { addModule: async () => undefined };
        createMediaStreamSource() {
          return new FakeAudioNode();
        }
        createAnalyser() {
          return Object.assign(new FakeAudioNode(), { fftSize: 256 });
        }
        async close() {
          return undefined;
        }
      }
      class FakeAudioWorkletNode extends FakeAudioNode {
        port = { postMessage: () => undefined, onmessage: null };
      }
      Object.defineProperty(window, "AudioContext", {
        configurable: true,
        value: FakeAudioContext,
      });
      Object.defineProperty(window, "AudioWorkletNode", {
        configurable: true,
        value: FakeAudioWorkletNode,
      });
    });
    await page.route(`**/api/v1/sessions/${voiceSessionId}`, (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(session(voiceSessionId, "digital_human_realtime_model")),
      }),
    );
    const textFallbackRequests: string[] = [];
    page.on("request", (request) => {
      const path = new URL(request.url()).pathname;
      if (/\/api\/v1\/sessions\/[^/]+\/message$/.test(path)) {
        textFallbackRequests.push(request.url());
      }
    });
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
            // Binary microphone frames are intentionally ignored.
          }
        });
      });
    });

    await page.goto(`/user/training/session?id=${voiceSessionId}`);
    await expect(page.getByTestId("transport-unavailable")).toHaveCount(0);
    await expect(page.getByRole("status").filter({ hasText: "Digital Human Realtime" })).toBeVisible();
    await expect(page.getByTestId("start-session-btn")).toBeVisible();
    await page.getByTestId("start-session-btn").click();

    const frame = await Promise.race([
      firstSessionUpdate,
      new Promise<never>((_, reject) =>
        setTimeout(
          () => reject(new Error("Voice Live session.update was not sent")),
          15_000,
        ),
      ),
    ]);
    expect(frame).toEqual({
      type: "session.update",
      session: { session_id: voiceSessionId },
    });
    expect(textFallbackRequests).toEqual([]);
  });
});
