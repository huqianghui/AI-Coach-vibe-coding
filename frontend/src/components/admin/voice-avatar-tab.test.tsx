import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import type { VoiceLiveInstance } from "@/types/voice-live";

// ---- Mocks ----

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en-US" },
  }),
}));

vi.mock("sonner", () => ({
  toast: { error: vi.fn(), warning: vi.fn(), success: vi.fn(), info: vi.fn() },
}));

const MOCK_INSTANCE: VoiceLiveInstance = {
  id: "inst-001",
  name: "Test Voice Config",
  description: "A test instance",
  voice_live_model: "gpt-4o",
  enabled: true,
  voice_name: "en-US-AvaNeural",
  voice_type: "azure-standard",
  voice_temperature: 0.9,
  voice_custom: false,
  avatar_character: "lisa",
  avatar_style: "casual",
  avatar_customized: false,
  turn_detection_type: "server_vad",
  noise_suppression: false,
  echo_cancellation: false,
  eou_detection: false,
  recognition_language: "auto",
  model_instruction: "",
  response_temperature: 0.8,
  proactive_engagement: true,
  auto_detect_language: true,
  playback_speed: 1.0,
  custom_lexicon_enabled: false,
  custom_lexicon_url: "",
  avatar_enabled: true,
  hcp_count: 2,
  created_by: "admin-001",
  created_at: "2026-04-01T00:00:00Z",
  updated_at: "2026-04-01T00:00:00Z",
};

let mockInstances: VoiceLiveInstance[] = [];

vi.mock("@/hooks/use-voice-live-instances", () => ({
  useVoiceLiveInstances: () => ({
    data: { items: mockInstances, total: mockInstances.length },
    isLoading: false,
  }),
}));

// Mock the two child panels the component delegates to
let capturedLeftPanelProps: Record<string, unknown> | null = null;
let capturedPlaygroundProps: Record<string, unknown> | null = null;

vi.mock("@/components/admin/agent-config-left-panel", () => ({
  AgentConfigLeftPanel: (props: Record<string, unknown>) => {
    capturedLeftPanelProps = props;
    return <div data-testid="agent-config-left-panel">AgentConfigLeftPanel</div>;
  },
}));

vi.mock("@/components/admin/playground-preview-panel", () => ({
  PlaygroundPreviewPanel: (props: Record<string, unknown>) => {
    capturedPlaygroundProps = props;
    return <div data-testid="playground-preview-panel">PlaygroundPreviewPanel</div>;
  },
}));

// Import after mocks
import { VoiceAvatarTab } from "./voice-avatar-tab";
import { useForm, FormProvider } from "react-hook-form";
import type { HcpFormValues } from "@/pages/admin/hcp-profile-editor";

/** Wrapper providing react-hook-form context */
function TestWrapper({
  instanceId = null,
  isNew = false,
  profile,
}: {
  instanceId?: string | null;
  isNew?: boolean;
  profile?: { id: string; name: string; agent_id?: string };
}) {
  const form = useForm<HcpFormValues>({
    defaultValues: {
      name: "Test HCP",
      specialty: "Oncology",
      hospital: "",
      title: "",
      personality_type: "friendly",
      emotional_state: 30,
      communication_style: 50,
      expertise_areas: [],
      prescribing_habits: "",
      concerns: "",
      objections: [],
      probe_topics: [],
      difficulty: "medium",
      voice_live_instance_id: instanceId,
      agent_instructions_override: "",
    },
  });

  return (
    <FormProvider {...form}>
      <VoiceAvatarTab
        form={form}
        isNew={isNew}
        profile={profile as never}
      />
    </FormProvider>
  );
}

describe("VoiceAvatarTab (two-panel layout)", () => {
  beforeEach(() => {
    capturedLeftPanelProps = null;
    capturedPlaygroundProps = null;
    mockInstances = [MOCK_INSTANCE];
  });

  it("renders both panels", () => {
    render(<TestWrapper instanceId="inst-001" />);
    expect(screen.getByTestId("agent-config-left-panel")).toBeInTheDocument();
    expect(screen.getByTestId("playground-preview-panel")).toBeInTheDocument();
  });

  it("passes form, isNew, and onAutoInstructionsChange to AgentConfigLeftPanel", () => {
    render(<TestWrapper instanceId="inst-001" isNew={false} />);
    expect(capturedLeftPanelProps).toBeTruthy();
    expect(capturedLeftPanelProps!.isNew).toBe(false);
    expect(capturedLeftPanelProps!.voiceModeEnabled).toBeUndefined();
    expect(capturedLeftPanelProps!.onVoiceModeChange).toBeUndefined();
    expect(typeof capturedLeftPanelProps!.onAutoInstructionsChange).toBe("function");
  });

  it("passes avatar data from selected VL instance to PlaygroundPreviewPanel", () => {
    mockInstances = [MOCK_INSTANCE];
    render(<TestWrapper instanceId="inst-001" />);
    expect(capturedPlaygroundProps).toBeTruthy();
    expect(capturedPlaygroundProps!.avatarCharacter).toBe("lisa");
    expect(capturedPlaygroundProps!.avatarStyle).toBe("casual");
    expect(capturedPlaygroundProps!.avatarEnabled).toBe(true);
  });

  it("passes undefined avatar data when no instance is selected", () => {
    mockInstances = [MOCK_INSTANCE];
    render(<TestWrapper instanceId={null} />);
    expect(capturedPlaygroundProps).toBeTruthy();
    expect(capturedPlaygroundProps!.avatarCharacter).toBeUndefined();
    expect(capturedPlaygroundProps!.avatarStyle).toBeUndefined();
    expect(capturedPlaygroundProps!.avatarEnabled).toBe(false);
  });

  it("sets disabled=true on PlaygroundPreviewPanel when isNew is true", () => {
    render(<TestWrapper instanceId={null} isNew={true} />);
    expect(capturedPlaygroundProps).toBeTruthy();
    expect(capturedPlaygroundProps!.disabled).toBe(true);
  });

  it("sets disabled=false on PlaygroundPreviewPanel when isNew is false", () => {
    render(<TestWrapper instanceId={null} isNew={false} />);
    expect(capturedPlaygroundProps).toBeTruthy();
    expect(capturedPlaygroundProps!.disabled).toBe(false);
  });

  it("passes profile data to PlaygroundPreviewPanel", () => {
    const profile = { id: "hcp-1", name: "Dr. Test", agent_id: "agent-1" };
    render(
      <TestWrapper instanceId={null} isNew={false} profile={profile} />,
    );
    expect(capturedPlaygroundProps).toBeTruthy();
    expect(capturedPlaygroundProps!.hcpProfileId).toBe("hcp-1");
    expect(capturedPlaygroundProps!.profileName).toBe("Dr. Test");
    expect(capturedPlaygroundProps!.agentId).toBe("agent-1");
  });

  it("derives voiceModeEnabled=true for PlaygroundPreviewPanel from a bound VL instance (D-11)", () => {
    render(<TestWrapper instanceId="inst-001" />);
    expect(capturedPlaygroundProps!.voiceModeEnabled).toBe(true);
  });

  it("derives voiceModeEnabled=false for PlaygroundPreviewPanel when no VL instance is bound (D-11)", () => {
    render(<TestWrapper instanceId={null} />);
    expect(capturedPlaygroundProps!.voiceModeEnabled).toBe(false);
  });
});
