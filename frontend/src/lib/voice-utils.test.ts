import { describe, it, expect } from "vitest";
import { encodePcmToBase64, resolveMode } from "./voice-utils";
import type { VoiceLiveToken } from "@/types/voice-live";

/**
 * Tests for resolveMode() — auto-resolution of the best session mode from token data.
 * Priority: Digital Human Realtime Agent > Digital Human Realtime Model > Voice Realtime Agent > Voice Realtime Model.
 */

const baseToken: VoiceLiveToken = {
  endpoint: "wss://test.api.cognitive.microsoft.com",
  token: "test-token",
  region: "eastus2",
  model: "gpt-4o-realtime",
  avatar_enabled: false,
  avatar_character: "",
  voice_name: "en-US-JennyNeural",
};

describe("encodePcmToBase64", () => {
  it("clips samples and converts positive, negative, and zero PCM values", () => {
    const encoded = encodePcmToBase64(new Float32Array([-2, -0.5, 0, 0.5, 2]));
    const binary = atob(encoded);
    const bytes = Uint8Array.from(binary, (value) => value.charCodeAt(0));
    const samples = Array.from(new Int16Array(bytes.buffer));

    expect(samples).toEqual([-32768, -16384, 0, 16383, 32767]);
  });

  it("returns an empty payload for empty audio", () => {
    expect(encodePcmToBase64(new Float32Array())).toBe("");
  });

  it("treats a missing indexed sample as silence", () => {
    const sparseLike = { length: 1 } as Float32Array;
    expect(atob(encodePcmToBase64(sparseLike))).toBe("\0\0");
  });
});

describe("resolveMode", () => {
  it("returns digital_human_realtime_agent when avatar_enabled + agent_id", () => {
    const token: VoiceLiveToken = {
      ...baseToken,
      avatar_enabled: true,
      avatar_character: "lisa",
      agent_id: "agent-123",
      project_name: "demo-project",
    };
    expect(resolveMode(token)).toBe("digital_human_realtime_agent");
  });

  it("returns digital_human_realtime_model when avatar_enabled but no agent_id", () => {
    const token: VoiceLiveToken = {
      ...baseToken,
      avatar_enabled: true,
      avatar_character: "lisa",
    };
    expect(resolveMode(token)).toBe("digital_human_realtime_model");
  });

  it("returns voice_realtime_agent when agent_id but no avatar", () => {
    const token: VoiceLiveToken = {
      ...baseToken,
      avatar_enabled: false,
      agent_id: "agent-456",
      project_name: "my-project",
    };
    expect(resolveMode(token)).toBe("voice_realtime_agent");
  });

  it("returns voice_realtime_model when no avatar and no agent_id", () => {
    expect(resolveMode(baseToken)).toBe("voice_realtime_model");
  });

  it("agent_id with empty string is treated as no agent", () => {
    const token: VoiceLiveToken = {
      ...baseToken,
      avatar_enabled: false,
      agent_id: "",
    };
    // Empty string is falsy → should fall through to voice_realtime_model
    expect(resolveMode(token)).toBe("voice_realtime_model");
  });

  it("agent_id undefined is treated as no agent", () => {
    const token: VoiceLiveToken = {
      ...baseToken,
      avatar_enabled: false,
      agent_id: undefined,
    };
    expect(resolveMode(token)).toBe("voice_realtime_model");
  });

  it("avatar_enabled takes priority over agent_id for mode selection", () => {
    // Both avatar + agent → digital_human_realtime_agent (highest priority)
    const token: VoiceLiveToken = {
      ...baseToken,
      avatar_enabled: true,
      avatar_character: "lisa",
      agent_id: "agent-789",
    };
    expect(resolveMode(token)).toBe("digital_human_realtime_agent");
  });
});
