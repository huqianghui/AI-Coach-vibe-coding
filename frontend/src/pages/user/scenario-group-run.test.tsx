import { describe, it, expect } from "vitest";
import { getAvailableModes } from "./scenario-group-run";
import type { Scenario, HcpProfileSummary } from "@/types/scenario";
import type { VoiceLiveInstanceSummary } from "@/types/hcp";

const makeVoiceLiveInstance = (
  overrides: Partial<VoiceLiveInstanceSummary> = {},
): VoiceLiveInstanceSummary => ({
  id: "vl-1",
  name: "Default VL Instance",
  voice_live_model: "gpt-4o-realtime",
  enabled: true,
  voice_name: "en-US-JennyNeural",
  avatar_character: "lori",
  avatar_style: "casual",
  avatar_enabled: true,
  ...overrides,
});

const makeHcpProfile = (
  overrides: Partial<HcpProfileSummary> = {},
): HcpProfileSummary => ({
  id: "hcp-1",
  name: "Dr. Test",
  specialty: "Oncology",
  avatar_url: "",
  personality_type: "friendly",
  voice_live_instance_id: "vl-1",
  voice_live_instance: makeVoiceLiveInstance(),
  ...overrides,
});

const makeScenario = (overrides: Partial<Scenario> = {}): Scenario => ({
  id: "sc-1",
  name: "Test Scenario",
  description: "A test scenario",
  mode: "f2f",
  difficulty: "easy",
  status: "active",
  hcp_profile_id: "hcp-1",
  hcp_profile: makeHcpProfile(),
  key_messages: [],
  skill_id: null,
  skill_version_id: null,
  rubric_id: "rubric-1",
  pass_threshold: 70,
  created_by: "admin",
  created_at: "2024-01-01",
  updated_at: "2024-01-01",
  ...overrides,
});

describe("getAvailableModes (scenario-group-run.tsx)", () => {
  it("offers voice and digital-human modes when VL instance has voice + avatar enabled", () => {
    const scenario = makeScenario();
    const features = { voice_live_enabled: true, avatar_enabled: true };

    const { modes, defaultMode } = getAvailableModes(scenario, features);

    expect(modes).toContain("voice_realtime_model");
    expect(modes).toContain("digital_human_realtime_model");
    expect(defaultMode).toBe("digital_human_realtime_model");
  });

  it("offers voice mode but NOT digital-human mode when VL instance avatar_enabled is false", () => {
    const scenario = makeScenario({
      hcp_profile: makeHcpProfile({
        voice_live_instance: makeVoiceLiveInstance({ avatar_enabled: false }),
      }),
    });
    const features = { voice_live_enabled: true, avatar_enabled: true };

    const { modes, defaultMode } = getAvailableModes(scenario, features);

    expect(modes).toContain("voice_realtime_model");
    expect(modes).not.toContain("digital_human_realtime_model");
    expect(defaultMode).toBe("voice_realtime_model");
  });

  it("offers voice mode but NOT avatar mode for conference scenario when features.avatar_enabled is false", () => {
    const scenario = makeScenario({ mode: "conference" });
    const features = {
      voice_enabled: true,
      voice_live_enabled: true,
      avatar_enabled: false,
    };

    const { modes, defaultMode } = getAvailableModes(scenario, features);

    expect(modes).toContain("voice_realtime_model");
    expect(modes).not.toContain("digital_human_realtime_model");
    expect(defaultMode).toBe("voice_realtime_model");
  });

  it("offers only text mode when HCP has no bound VoiceLiveInstance", () => {
    const scenario = makeScenario({
      hcp_profile: makeHcpProfile({
        voice_live_instance_id: null,
        voice_live_instance: undefined,
      }),
    });
    const features = { voice_live_enabled: true, avatar_enabled: true };

    const { modes, defaultMode } = getAvailableModes(scenario, features);

    expect(modes).toEqual(["text"]);
    expect(defaultMode).toBe("text");
  });

  it("offers full gating matrix for conference mode with avatar enabled", () => {
    const scenario = makeScenario({
      mode: "conference",
      hcp_profile: makeHcpProfile({
        voice_live_instance: makeVoiceLiveInstance({ enabled: true, avatar_enabled: true }),
      }),
    });
    const features = {
      voice_enabled: true,
      voice_live_enabled: true,
      avatar_enabled: true,
    };

    const { modes, defaultMode } = getAvailableModes(scenario, features);

    expect(modes).toContain("voice_realtime_model");
    expect(modes).toContain("digital_human_realtime_model");
    expect(defaultMode).toBe("digital_human_realtime_model");
  });

  it("returns only text mode when scenario is null/undefined", () => {
    const features = { voice_live_enabled: true, avatar_enabled: true };

    const { modes, defaultMode } = getAvailableModes(undefined, features);

    expect(modes).toEqual(["text"]);
    expect(defaultMode).toBe("text");
  });
});
