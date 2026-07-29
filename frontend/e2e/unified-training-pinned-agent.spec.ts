import { expect, test } from "./coverage-helper";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const authDir = join(dirname(fileURLToPath(import.meta.url)), ".auth");
const scenarioId = "scenario-phase-30";
const textSessionId = "session-phase-30-text";
const voiceSessionId = "session-phase-30-voice";

const forbiddenIdentityKeys = [
  "agent_name",
  "agent_version",
  "agent_response_id",
  "additional_instructions",
  "focus_instruction",
];

const scenario = {
  id: scenarioId,
  name: "Phase 30 Pinned Agent Scenario",
  description: "Deterministic browser acceptance scenario",
  tags: ["product:test"],
  product: "Test Product",
  therapeutic_area: "Oncology",
  mode: "f2f",
  difficulty: "medium",
  status: "active",
  hcp_profile_id: "hcp-phase-30",
  hcp_profile: {
    id: "hcp-phase-30",
    name: "Dr. Pinned",
    specialty: "Oncology",
    personality_type: "analytical",
    avatar_url: "",
    avatar_enabled: false,
    voice_live_instance: { enabled: false },
    agent_version: "99",
  },
  key_messages: ["Pinned Agent key message"],
  skill_id: "skill-audit-only",
  skill_version_id: "skill-version-audit-only",
  rubric_id: "rubric-phase-30",
  pass_threshold: 70,
  created_by: "admin-phase-30",
  created_at: "2026-07-27T00:00:00Z",
  updated_at: "2026-07-27T00:00:00Z",
};

function session(id: string, mode: string) {
  return {
    id,
    user_id: "user-phase-30",
    scenario_id: scenarioId,
    scenario_name: scenario.name,
    status: "created",
    started_at: null,
    completed_at: null,
    duration_seconds: null,
    key_messages_status: [
      {
        message: "Pinned Agent key message",
        delivered: false,
        detected_at: null,
      },
    ],
    overall_score: null,
    passed: null,
    mode,
    agent_name: "hcp-pinned-agent",
    agent_version: "7",
    message_count: 0,
    created_at: "2026-07-27T00:00:00Z",
    updated_at: "2026-07-27T00:00:00Z",
  };
}

async function installCommonRoutes(page: import("@playwright/test").Page) {
  await page.route("**/api/v1/auth/me", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "user-phase-30",
        username: "user1",
        email: "user1@example.com",
        role: "user",
        is_active: true,
      }),
    }),
  );
  await page.route("**/api/v1/scenarios/active*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([scenario]),
    }),
  );
  await page.route(`**/api/v1/scenarios/${scenarioId}`, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(scenario),
    }),
  );
  await page.route("**/api/v1/scenario-groups/active", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: "[]" }),
  );
  await page.route("**/api/v1/config/features", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        features: {
          avatar_enabled: false,
          voice_enabled: false,
          realtime_voice_enabled: false,
          conference_enabled: false,
          voice_live_enabled: false,
          default_voice_mode: "text_only",
          region: "global",
        },
      }),
    }),
  );
}

test.describe("Unified Training pinned Foundry Agent", () => {
  test.use({ storageState: join(authDir, "user.json") });

  test("creates an identity-minimal session and preserves text SSE UX and pin audit", async ({
    page,
  }) => {
    await installCommonRoutes(page);

    let createBody: Record<string, unknown> | undefined;
    let messageBody: Record<string, unknown> | undefined;
    let sessionReadCount = 0;

    await page.route("**/api/v1/sessions", async (route) => {
      if (route.request().method() !== "POST") {
        await route.continue();
        return;
      }
      createBody = route.request().postDataJSON() as Record<string, unknown>;
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify(session(textSessionId, "text")),
      });
    });
    await page.route(`**/api/v1/sessions/${textSessionId}`, async (route) => {
      sessionReadCount += 1;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(session(textSessionId, "text")),
      });
    });
    await page.route(
      `**/api/v1/sessions/${textSessionId}/message`,
      async (route) => {
        messageBody = route.request().postDataJSON() as Record<string, unknown>;
        const sse = [
          "event: text",
          "data: Grounded response from pinned Agent",
          "",
          "event: key_messages",
          'data: [{"message":"Pinned Agent key message","delivered":true,"detected_at":"2026-07-27T00:00:01Z"}]',
          "",
          "event: hint",
          'data: {"content":"Use the grounded evidence","metadata":{"type":"guidance"}}',
          "",
          "event: done",
          "data: ",
          "",
        ].join("\n");
        await route.fulfill({
          status: 200,
          contentType: "text/event-stream",
          body: sse,
        });
      },
    );

    await page.goto("/user/training");
    await page.getByRole("button", { name: /开始培训|Start Training/ }).click();
    await expect(page).toHaveURL(new RegExp(`${textSessionId}$`));

    expect(createBody).toEqual({ scenario_id: scenarioId, mode: "text" });
    for (const key of forbiddenIdentityKeys) {
      expect(createBody).not.toHaveProperty(key);
    }

    await page.getByTestId("text-input").fill("Ask the pinned HCP Agent");
    await page.getByTestId("send-btn").click();

    await expect(page.getByTestId("chat-area")).toContainText(
      "Grounded response from pinned Agent",
    );
    await expect(page.getByText("Use the grounded evidence")).toBeVisible();
    await expect(page.getByText("Pinned Agent key message").first()).toBeVisible();
    expect(messageBody).toEqual({ message: "Ask the pinned HCP Agent" });
    for (const key of forbiddenIdentityKeys) {
      expect(messageBody).not.toHaveProperty(key);
    }

    // Simulate the mutable HCP profile moving to version 99. Reloading the
    // existing session still returns its immutable version 7 audit pin.
    scenario.hcp_profile.agent_version = "99";
    const sessionResponse = page.waitForResponse(
      (response) =>
        response.url().endsWith(`/api/v1/sessions/${textSessionId}`) &&
        response.request().method() === "GET",
    );
    await page.reload();
    const persisted = await (await sessionResponse).json();
    expect(persisted.agent_name).toBe("hcp-pinned-agent");
    expect(persisted.agent_version).toBe("7");
    expect(sessionReadCount).toBeGreaterThanOrEqual(2);
  });

  test("sends only session_id in the trusted Voice Live first frame", async ({
    page,
    context,
  }) => {
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
        body: JSON.stringify(session(voiceSessionId, "voice_realtime_model")),
      }),
    );

    const firstSessionUpdate = new Promise<Record<string, unknown>>((resolve) => {
      page.on("websocket", (socket) => {
        socket.on("framesent", (event) => {
          const payload =
            typeof event.payload === "string"
              ? event.payload
              : event.payload.toString();
          try {
            const frame = JSON.parse(payload) as Record<string, unknown>;
            if (frame.type === "session.update") resolve(frame);
          } catch {
            // Audio frames are binary and are intentionally ignored.
          }
        });
      });
    });

    await page.goto(`/user/training/session?id=${voiceSessionId}`);
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
  });
});
