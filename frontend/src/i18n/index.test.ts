import { describe, it, expect, vi } from "vitest";

// Track all calls made to i18n.use and i18n.init during module initialization.
// We use vi.hoisted to ensure these are available when the mock factory runs.
const useCalls = vi.hoisted(() => [] as unknown[]);
const initCalls = vi.hoisted(() => [] as unknown[][]);

vi.mock("i18next", () => {
  const mockI18n = {
    use: vi.fn((plugin: unknown) => {
      useCalls.push(plugin);
      return mockI18n;
    }),
    init: vi.fn((...args: unknown[]) => {
      initCalls.push(args);
      return mockI18n;
    }),
    language: "en-US",
    t: vi.fn((key: string) => key),
  };
  return { default: mockI18n };
});

vi.mock("react-i18next", () => ({
  initReactI18next: { type: "3rdParty", init: vi.fn() },
}));

vi.mock("i18next-browser-languagedetector", () => ({
  default: class MockDetector {},
}));

vi.mock("i18next-http-backend", () => ({
  default: class MockBackend {},
}));

// Import triggers the module-level initialization chain
import i18n from "@/i18n/index";

describe("i18n initialization", () => {
  it("should export an i18n instance", () => {
    expect(i18n).toBeDefined();
    expect(typeof i18n.use).toBe("function");
    expect(typeof i18n.init).toBe("function");
  });

  it("should call use() three times for HttpBackend, LanguageDetector, and initReactI18next", () => {
    expect(useCalls).toHaveLength(3);
  });

  it("should call init() once with configuration", () => {
    expect(initCalls).toHaveLength(1);
    expect(initCalls[0]).toBeDefined();
  });

  it("should configure fallback language and supported languages", () => {
    const config = initCalls[0]![0] as Record<string, unknown>;
    expect(config["fallbackLng"]).toBe("en-US");
    expect(config["supportedLngs"]).toEqual(["en-US", "zh-CN"]);
    expect(config["defaultNS"]).toBe("common");
  });

  it("should configure the correct namespaces", () => {
    const config = initCalls[0]![0] as Record<string, unknown>;
    expect(config["ns"]).toEqual([
      "common",
      "auth",
      "nav",
      "dashboard",
      "training",
      "coach",
      "admin",
      "scoring",
      "analytics",
      "conference",
      "skill",
      "voice",
      "meta-skill",
      "session",
      "prompts",
    ]);
  });

  it("should configure backend loadPath", () => {
    const config = initCalls[0]![0] as Record<string, unknown>;
    const backend = config["backend"] as Record<string, string>;
    expect(backend["loadPath"]).toBe("/locales/{{lng}}/{{ns}}.json");
  });

  it("should configure detection to use localStorage and navigator", () => {
    const config = initCalls[0]![0] as Record<string, unknown>;
    const detection = config["detection"] as Record<string, unknown>;
    expect(detection["order"]).toEqual(["localStorage", "navigator"]);
    expect(detection["caches"]).toEqual(["localStorage"]);
    expect(detection["lookupLocalStorage"]).toBe("i18nextLng");
  });

  it("should disable escapeValue in interpolation", () => {
    const config = initCalls[0]![0] as Record<string, unknown>;
    const interpolation = config["interpolation"] as Record<string, unknown>;
    expect(interpolation["escapeValue"]).toBe(false);
  });
});
