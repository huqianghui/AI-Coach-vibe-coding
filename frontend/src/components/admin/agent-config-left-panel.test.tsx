import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useEffect } from "react";
import { useForm, FormProvider } from "react-hook-form";
import type { VoiceLiveInstance } from "@/types/voice-live";
import type { HcpFormValues } from "@/pages/admin/hcp-profile-editor";

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

const mockNavigate = vi.fn();
vi.mock("react-router-dom", () => ({
  useNavigate: () => mockNavigate,
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
  hcp_count: 0,
  created_by: "admin-001",
  created_at: "2026-04-01T00:00:00Z",
  updated_at: "2026-04-01T00:00:00Z",
};

let mockInstances: VoiceLiveInstance[] = [MOCK_INSTANCE];
const mockAssignMutate = vi.fn();
const mockUnassignMutate = vi.fn();

vi.mock("@/hooks/use-voice-live-instances", () => ({
  useVoiceLiveInstances: () => ({
    data: { items: mockInstances, total: mockInstances.length },
    isLoading: false,
  }),
  useAssignVoiceLiveInstance: () => ({
    mutate: mockAssignMutate,
    isPending: false,
  }),
  useUnassignVoiceLiveInstance: () => ({
    mutate: mockUnassignMutate,
    isPending: false,
  }),
}));

let mockKbConfigs: Array<{ id: string; index_name: string }> = [];
const mockRemoveKbMutate = vi.fn();

vi.mock("@/hooks/use-knowledge-base", () => ({
  useHcpKnowledgeConfigs: () => ({ data: mockKbConfigs }),
  useRemoveKnowledgeConfig: () => ({
    mutate: mockRemoveKbMutate,
    isPending: false,
  }),
}));

vi.mock("@/components/admin/connect-kb-dialog", () => ({
  ConnectKbDialog: ({ open }: { open: boolean }) => (
    <div data-testid="connect-kb-dialog" data-open={open} />
  ),
}));

vi.mock("@/components/admin/agent-foundation-model-select", () => ({
  AgentFoundationModelSelect: ({ value }: { value: string }) => (
    <div data-testid="agent-foundation-model-select" data-value={value} />
  ),
}));

let capturedInstructionsProps: Record<string, unknown> | null = null;
vi.mock("@/components/admin/instructions-section", () => ({
  InstructionsSection: (props: Record<string, unknown>) => {
    capturedInstructionsProps = props;
    return <div data-testid="instructions-section">InstructionsSection</div>;
  },
}));

// Import after mocks
import { AgentConfigLeftPanel } from "./agent-config-left-panel";

function TestWrapper({
  instanceId = null,
  isNew = false,
  profile,
  onAutoInstructionsChange,
  withValidationError = false,
}: {
  instanceId?: string | null;
  isNew?: boolean;
  profile?: { id: string; name: string };
  onAutoInstructionsChange?: (instructions: string) => void;
  withValidationError?: boolean;
}) {
  const form = useForm<HcpFormValues>({
    defaultValues: {
      name: "Dr. Test",
      specialty: "Oncology",
      hospital: "",
      title: "",
      personality_type: "friendly",
      emotional_state: 50,
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

  useEffect(() => {
    if (withValidationError) {
      form.setError("voice_live_instance_id", {
        type: "custom",
        message: "hcp.vlInstanceValidationError",
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <FormProvider {...form}>
      <AgentConfigLeftPanel
        form={form}
        profile={profile as never}
        isNew={isNew}
        onAutoInstructionsChange={onAutoInstructionsChange}
      />
    </FormProvider>
  );
}

describe("AgentConfigLeftPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    capturedInstructionsProps = null;
    mockInstances = [MOCK_INSTANCE];
    mockKbConfigs = [];
  });

  // ── D-11: VL Instance Summary Card ────────────────────────
  it("shows assigned-state badges when an instance is selected", () => {
    render(<TestWrapper instanceId="inst-001" />);
    expect(screen.getAllByText("Test Voice Config").length).toBeGreaterThan(0);
    expect(screen.getAllByText("gpt-4o").length).toBeGreaterThan(0);
    expect(screen.getAllByText("en-US-AvaNeural").length).toBeGreaterThan(0);
    expect(screen.getAllByText("lisa · casual").length).toBeGreaterThan(0);
  });

  it("shows empty-state title, required badge, and body when no instance is assigned", () => {
    render(<TestWrapper instanceId={null} />);
    expect(
      screen.getByText("admin:hcp.vlInstanceEmptyTitle"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("admin:hcp.vlInstanceRequiredBadge"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("admin:hcp.vlInstanceEmptyBody"),
    ).toBeInTheDocument();
  });

  it("does not render the old VoiceLiveModelSelect component (replaced by AgentFoundationModelSelect, D-14)", () => {
    render(<TestWrapper instanceId="inst-001" />);
    expect(screen.queryByTestId("model-select")).not.toBeInTheDocument();
    // The admin:hcp.modelDeployment label is intentionally reused (D-14) as
    // the header for the new Agent Foundation Model dropdown card.
    expect(
      screen.getByTestId("agent-foundation-model-select"),
    ).toBeInTheDocument();
  });

  it("does not render a voice mode Switch toggle", () => {
    render(<TestWrapper instanceId="inst-001" />);
    expect(screen.queryByRole("switch")).not.toBeInTheDocument();
    expect(
      screen.queryByText("admin:hcp.voiceModeToggle"),
    ).not.toBeInTheDocument();
  });

  it("renders inline validation error when voice_live_instance_id has a form error", () => {
    render(<TestWrapper instanceId={null} withValidationError />);
    expect(
      screen.getByText("admin:hcp.vlInstanceValidationError"),
    ).toBeInTheDocument();
  });

  it("shows VL management link", () => {
    render(<TestWrapper />);
    expect(
      screen.getByText("admin:voiceLive.goToVlManagement"),
    ).toBeInTheDocument();
  });

  it("navigates to VL management when link is clicked", async () => {
    const user = userEvent.setup();
    render(<TestWrapper />);
    await user.click(screen.getByText("admin:voiceLive.goToVlManagement"));
    expect(mockNavigate).toHaveBeenCalledWith("/admin/voice-live");
  });

  it("shows disabled hint for new profiles", () => {
    render(<TestWrapper isNew={true} />);
    expect(
      screen.getByText("admin:hcp.playgroundDisabledNew"),
    ).toBeInTheDocument();
  });

  it("does not show disabled hint for existing profiles", () => {
    render(<TestWrapper isNew={false} />);
    expect(
      screen.queryByText("admin:hcp.playgroundDisabledNew"),
    ).not.toBeInTheDocument();
  });

  // ── Remove instance button + dialog (D-11 unassign flow) ──
  it("shows remove button (X) when instance is selected", () => {
    render(<TestWrapper instanceId="inst-001" />);
    expect(
      screen.getByTitle("admin:voiceLive.removeInstance"),
    ).toBeInTheDocument();
  });

  it("does not show remove button when no instance is selected", () => {
    render(<TestWrapper instanceId={null} />);
    expect(
      screen.queryByTitle("admin:voiceLive.removeInstance"),
    ).not.toBeInTheDocument();
  });

  it("shows remove confirmation dialog when X button is clicked", async () => {
    const user = userEvent.setup();
    render(
      <TestWrapper
        instanceId="inst-001"
        profile={{ id: "hcp-1", name: "Dr. Test" }}
      />,
    );

    await user.click(screen.getByTitle("admin:voiceLive.removeInstance"));
    const removeTexts = screen.getAllByText("admin:voiceLive.removeInstance");
    expect(removeTexts.length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("common:cancel")).toBeInTheDocument();
  });

  it("calls unassign mutation when remove is confirmed", async () => {
    const user = userEvent.setup();
    render(
      <TestWrapper
        instanceId="inst-001"
        profile={{ id: "hcp-1", name: "Dr. Test" }}
      />,
    );

    await user.click(screen.getByTitle("admin:voiceLive.removeInstance"));
    const removeButtons = screen.getAllByText(
      "admin:voiceLive.removeInstance",
    );
    // Second occurrence is the destructive confirm button inside the dialog
    await user.click(removeButtons[1]!.closest("button")!);
    expect(mockUnassignMutate).toHaveBeenCalledWith(
      "hcp-1",
      expect.objectContaining({
        onSuccess: expect.any(Function),
        onError: expect.any(Function),
      }),
    );
  });

  // ── Knowledge & Tools expand/collapse ─────────────────────
  it("renders knowledge & tools section", () => {
    render(<TestWrapper />);
    expect(screen.getByText("admin:hcp.knowledgeAndTools")).toBeInTheDocument();
  });

  it("expands knowledge & tools section when header is clicked", async () => {
    const user = userEvent.setup();
    render(<TestWrapper />);
    expect(
      screen.queryByText("admin:hcp.toolsPlaceholder"),
    ).not.toBeInTheDocument();

    await user.click(screen.getByText("admin:hcp.knowledgeAndTools"));
    expect(
      screen.getByText("admin:hcp.toolsPlaceholder"),
    ).toBeInTheDocument();
  });

  it("collapses knowledge & tools section when header is clicked twice", async () => {
    const user = userEvent.setup();
    render(<TestWrapper />);
    const header = screen.getByText("admin:hcp.knowledgeAndTools");

    await user.click(header);
    expect(
      screen.getByText("admin:hcp.toolsPlaceholder"),
    ).toBeInTheDocument();

    await user.click(header);
    expect(
      screen.queryByText("admin:hcp.toolsPlaceholder"),
    ).not.toBeInTheDocument();
  });

  // ── Instructions section props ────────────────────────────
  it("passes form and profileId to InstructionsSection", () => {
    render(
      <TestWrapper isNew={false} profile={{ id: "hcp-1", name: "Dr. Test" }} />,
    );
    expect(capturedInstructionsProps).toBeTruthy();
    expect(capturedInstructionsProps!.profileId).toBe("hcp-1");
    expect(capturedInstructionsProps!.isNew).toBe(false);
  });
});
