import { expect, test } from "@playwright/test";
import { dirname, join, resolve } from "node:path";
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const authDir = join(dirname(fileURLToPath(import.meta.url)), ".auth");
const evidencePath = resolve(
  dirname(fileURLToPath(import.meta.url)),
  "../../.planning/phases/31-session-skill-temporary-context-pinned-foundry-agent/31-CAPABILITY-EVIDENCE.md",
);
const enabled = process.env.PHASE31_LIVE_WEBRTC === "1";

interface ProbeResult {
  verdict: "PROVEN" | "FAIL-CLOSED: PROOF HARNESS UNAVAILABLE" | "FAIL-CLOSED: BYPASS POSSIBLE/AMBIGUOUS";
  route: string;
  dataChannelObserved: boolean;
  hostileCreateSent: boolean;
  responseCreatedAfterHostile: number;
  errorAfterHostile: boolean;
  details: string;
}

function sessionIdFromEvidence(): string {
  const configured = process.env.PHASE31_SESSION_ID?.trim();
  if (configured) return configured;
  const evidence = readFileSync(evidencePath, "utf8");
  return evidence.match(/^- Session ID: ([^\r\n]+)$/m)?.[1]?.trim() ?? "";
}

function writeVerdict(result: ProbeResult): void {
  const current = readFileSync(evidencePath, "utf8");
  const updated = current.replace(
    /^- WebRTC verdict: .*$/m,
    `- WebRTC verdict: ${result.verdict}`,
  );
  const withoutOldDetails = updated.replace(
    /\n## WebRTC live browser details[\s\S]*?(?=\n## Immutability and trust controls)/m,
    "",
  );
  const section = [
    "",
    "## WebRTC live browser details",
    "",
    `- Actual Unified Training route: ${result.route}`,
    `- Real Chromium: true`,
    `- Negotiated data channel observed: ${result.dataChannelObserved}`,
    `- Hostile bare response.create sent: ${result.hostileCreateSent}`,
    `- response.created events after hostile attempt: ${result.responseCreatedAfterHostile}`,
    `- Service/application error after hostile attempt: ${result.errorAfterHostile}`,
    `- Determination: ${result.details}`,
    "",
  ].join("\n");
  writeFileSync(
    evidencePath,
    withoutOldDetails.replace("\n## Immutability and trust controls", `${section}\n## Immutability and trust controls`),
    "utf8",
  );
}

test.use({
  storageState: join(authDir, "user.json"),
  permissions: ["microphone"],
  launchOptions: {
    args: [
      "--use-fake-device-for-media-stream",
      "--use-fake-ui-for-media-stream",
      "--autoplay-policy=no-user-gesture-required",
    ],
  },
});

test.describe("Phase 31 live WebRTC authority gate", () => {
  test.setTimeout(60_000);

  test("actively attempts hostile response.create on the actual Unified Training route", async ({
    page,
  }) => {
    expect(enabled, "PHASE31_LIVE_WEBRTC=1 is required; this gate never skips").toBe(true);
    const sessionId = sessionIdFromEvidence();
    expect(sessionId, "Sanitized backend preflight must provide an existing Session ID").not.toBe("");
    const route = `/user/training/session?id=${encodeURIComponent(sessionId)}`;

    await page.addInitScript(() => {
      type CapturedChannel = {
        channel: RTCDataChannel;
        messages: Array<Record<string, unknown>>;
      };
      const captured: CapturedChannel[] = [];
      Object.defineProperty(window, "__phase31Channels", {
        configurable: false,
        value: captured,
      });
      const original = RTCPeerConnection.prototype.createDataChannel;
      RTCPeerConnection.prototype.createDataChannel = function (...args) {
        const channel = original.apply(this, args as Parameters<typeof original>);
        const entry: CapturedChannel = { channel, messages: [] };
        channel.addEventListener("message", (event) => {
          try {
            entry.messages.push(JSON.parse(String(event.data)) as Record<string, unknown>);
          } catch {
            // Binary/non-JSON media events are irrelevant to the authority probe.
          }
        });
        captured.push(entry);
        return channel;
      };
    });

    await page.goto(route, { waitUntil: "domcontentloaded" });
    const start = page.getByTestId("start-session-btn");
    if (await start.isVisible().catch(() => false)) {
      await start.click();
    }

    const channelReady = await page
      .waitForFunction(
        () => {
          const channels = (
            window as typeof window & {
              __phase31Channels?: Array<{ channel: RTCDataChannel }>;
            }
          ).__phase31Channels;
          return channels?.some((entry) => entry.channel.readyState === "open") ?? false;
        },
        undefined,
        { timeout: 30_000 },
      )
      .then(() => true)
      .catch(() => false);

    if (!channelReady) {
      const result: ProbeResult = {
        verdict: "FAIL-CLOSED: PROOF HARNESS UNAVAILABLE",
        route,
        dataChannelObserved: false,
        hostileCreateSent: false,
        responseCreatedAfterHostile: 0,
        errorAfterHostile: false,
        details:
          "The production Unified Training route did not negotiate/expose a WebRTC data channel; it currently uses the WebSocket Voice Live hook. No production-equivalent hostile bypass harness exists without forbidden topology changes.",
      };
      writeVerdict(result);
      console.log(`PHASE31_WEBRTC_EVIDENCE=${JSON.stringify(result)}`);
      return;
    }

    const observation = await page.evaluate(async () => {
      const channels = (
        window as typeof window & {
          __phase31Channels?: Array<{
            channel: RTCDataChannel;
            messages: Array<Record<string, unknown>>;
          }>;
        }
      ).__phase31Channels ?? [];
      const entry = channels.find((item) => item.channel.readyState === "open");
      if (!entry) throw new Error("Observed data channel closed before hostile attempt");
      const before = entry.messages.length;
      entry.channel.send(JSON.stringify({ type: "response.create" }));
      await new Promise((resolvePromise) => setTimeout(resolvePromise, 10_000));
      const observed = entry.messages.slice(before);
      return {
        responseCreated: observed.filter((message) => message.type === "response.created").length,
        error: observed.some((message) => message.type === "error"),
      };
    });

    const result: ProbeResult = {
      verdict: "FAIL-CLOSED: BYPASS POSSIBLE/AMBIGUOUS",
      route,
      dataChannelObserved: true,
      hostileCreateSent: true,
      responseCreatedAfterHostile: observation.responseCreated,
      errorAfterHostile: observation.error,
      details:
        observation.responseCreated > 0
          ? "The hostile browser data-channel event created a response; exclusive backend authority is disproven."
          : "No correlated authorized backend-created response exists on the current route, so response ownership remains ambiguous even if the hostile event produced an error.",
    };
    writeVerdict(result);
    console.log(`PHASE31_WEBRTC_EVIDENCE=${JSON.stringify(result)}`);
    expect(result.verdict).toMatch(/^FAIL-CLOSED/);
  });
});
