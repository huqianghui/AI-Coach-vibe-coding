import { describe, expect, it } from "vitest";
import {
  CDN_BASE,
  RECOGNITION_LANGUAGES,
  TURN_DETECTION_TYPES,
  VOICE_NAME_OPTIONS,
  createDefaultVlInstanceForm,
} from "./voice-constants";

describe("voice constants", () => {
  it("exposes supported option catalogs and the Azure CDN", () => {
    expect(VOICE_NAME_OPTIONS.some((item) => item.value === "zh-CN-YunxiNeural")).toBe(true);
    expect(TURN_DETECTION_TYPES.map((item) => item.value)).toContain("semantic_vad");
    expect(RECOGNITION_LANGUAGES.map((item) => item.value)).toEqual(
      expect.arrayContaining(["auto", "zh-CN", "en-US"]),
    );
    expect(CDN_BASE).toContain("learn.microsoft.com");
  });

  it("returns a complete, fresh default instance form", () => {
    const first = createDefaultVlInstanceForm();
    const second = createDefaultVlInstanceForm();

    expect(first).toMatchObject({
      name: "",
      enabled: true,
      voice_live_model: "gpt-4o",
      voice_name: "en-US-AvaNeural",
      avatar_character: "lori",
      avatar_enabled: true,
      recognition_language: "auto",
    });
    expect(first).not.toBe(second);
    first.name = "Changed";
    expect(second.name).toBe("");
  });
});
