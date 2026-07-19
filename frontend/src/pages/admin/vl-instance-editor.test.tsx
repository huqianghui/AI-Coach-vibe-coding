import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { toast } from "sonner";
import VlInstanceEditorPage from "./vl-instance-editor";
import type { VoiceLiveInstance } from "@/types/voice-live";
import type { HcpProfile } from "@/types/hcp";

/* ── Mocks ────────────────────────────────────────────────────────────── */

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      (opts?.defaultValue as string) ?? key,
    i18n: { changeLanguage: vi.fn(), language: "en" },
  }),
}));

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

const mockCreateMutate = vi.fn();
const mockUpdateMutate = vi.fn();
const mockAssignMutate = vi.fn();

let mockInstanceReturn: {
  data: VoiceLiveInstance | undefined;
  isLoading: boolean;
};

let mockHcpReturn: {
  data: { items: HcpProfile[] } | undefined;
};

vi.mock("@/hooks/use-voice-live-instances", () => ({
  useVoiceLiveInstance: () => mockInstanceReturn,
  useCreateVoiceLiveInstance: () => ({
    mutate: mockCreateMutate,
    isPending: false,
  }),
  useUpdateVoiceLiveInstance: () => ({
    mutate: mockUpdateMutate,
    isPending: false,
  }),
  useAssignVoiceLiveInstance: () => ({
    mutate: mockAssignMutate,
    isPending: false,
  }),
}));

vi.mock("@/hooks/use-hcp-profiles", () => ({
  useHcpProfiles: () => mockHcpReturn,
}));

// Mock VoiceLiveModelSelect
vi.mock("@/components/admin/voice-live-model-select", () => ({
  VoiceLiveModelSelect: (props: { value: string }) => (
    <div data-testid="model-select">{props.value}</div>
  ),
}));

// Mock VoiceTestPlayground — capture ALL props so tests can verify correct routing
let capturedPlaygroundProps: Record<string, unknown> | null = null;
// Suppress TS6133 for variable used only for internal capture (not yet asserted)
void capturedPlaygroundProps;
vi.mock("@/components/voice/voice-test-playground", () => ({
  VoiceTestPlayground: (props: {
    hcpProfileId?: string;
    vlInstanceId?: string;
    systemPrompt?: string;
    language?: string;
    avatarCharacter?: string;
    avatarStyle?: string;
    avatarEnabled?: boolean;
    hcpName?: string;
    disabled: boolean;
    disabledMessage?: string;
    title: string;
    headerExtra?: React.ReactNode;
    className?: string;
  }) => {
    capturedPlaygroundProps = { ...props };
    return (
      <div
        data-testid="voice-playground"
        data-disabled={props.disabled}
        data-vl-instance-id={props.vlInstanceId ?? ""}
        data-hcp-profile-id={props.hcpProfileId ?? ""}
        data-system-prompt={props.systemPrompt ?? ""}
        data-avatar-enabled={String(props.avatarEnabled ?? false)}
        data-avatar-character={props.avatarCharacter ?? ""}
        data-avatar-style={props.avatarStyle ?? ""}
        data-hcp-name={props.hcpName ?? ""}
      >
        {props.title}
        {props.disabledMessage && (
          <span data-testid="disabled-msg">{props.disabledMessage}</span>
        )}
        {props.headerExtra}
      </div>
    );
  },
}));

// Mock avatar-characters data
vi.mock("@/data/avatar-characters", () => ({
  AVATAR_CHARACTERS: [
    {
      id: "lisa",
      displayName: "Lisa",
      styles: ["casual-sitting", "professional"],
      defaultStyle: "casual-sitting",
      gender: "female",
      isPhotoAvatar: false,
      gradientClasses: "from-blue-400 to-blue-600",
      thumbnailUrl: "https://cdn/lisa.png",
    },
    {
      id: "photo1",
      displayName: "Photo Character",
      styles: [],
      defaultStyle: "",
      gender: "female",
      isPhotoAvatar: true,
      gradientClasses: "from-pink-400 to-pink-600",
      thumbnailUrl: "https://cdn/photo1.png",
    },
  ],
  getAvatarInitials: (name: string) =>
    name
      .split(" ")
      .map((n: string) => n[0])
      .join("")
      .toUpperCase(),
}));

/* ── Helpers ───────────────────────────────────────────────────────────── */

const MOCK_INSTANCE: VoiceLiveInstance = {
  id: "vl-1",
  name: "Test VL Instance",
  description: "Test instance desc",
  voice_live_model: "gpt-4o",
  enabled: true,
  voice_name: "en-US-AvaNeural",
  voice_type: "azure-standard",
  voice_temperature: 0.9,
  voice_custom: false,
  avatar_character: "lisa",
  avatar_style: "casual-sitting",
  avatar_customized: false,
  turn_detection_type: "server_vad",
  noise_suppression: false,
  echo_cancellation: false,
  eou_detection: false,
  recognition_language: "auto",
  response_temperature: 0.8,
  proactive_engagement: true,
  auto_detect_language: true,
  playback_speed: 1.0,
  custom_lexicon_enabled: false,
  custom_lexicon_url: "",
  avatar_enabled: true,
  model_instruction: "Be helpful",
  hcp_count: 1,
  created_by: "admin",
  created_at: "2026-01-01",
  updated_at: "2026-01-01",
};

const MOCK_HCP: HcpProfile = {
  id: "hcp-1",
  name: "Dr. Smith",
  specialty: "Oncology",
  hospital: "GH",
  title: "Prof",
  avatar_url: "",
  personality_type: "friendly",
  emotional_state: 50,
  communication_style: 50,
  expertise_areas: [],
  prescribing_habits: "",
  concerns: "",
  objections: [],
  probe_topics: [],
  difficulty: "medium",
  is_active: true,
  created_by: "admin",
  created_at: "2026-01-01",
  updated_at: "2026-01-01",
  agent_id: "",
  agent_version: "",
  agent_sync_status: "none",
  agent_sync_error: "",
  voice_live_instance_id: "vl-1",
  agent_instructions_override: "",
  knowledge_config_count: 0,
};

function renderEditor(path = "/admin/voice-live/new") {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route
            path="/admin/voice-live/new"
            element={<VlInstanceEditorPage />}
          />
          <Route
            path="/admin/voice-live/:id/edit"
            element={<VlInstanceEditorPage />}
          />
          <Route path="/admin/voice-live" element={<div>list-page</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/* ── Tests ─────────────────────────────────────────────────────────────── */

describe("VlInstanceEditorPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    capturedPlaygroundProps = null;
    mockInstanceReturn = { data: undefined, isLoading: false };
    mockHcpReturn = { data: { items: [] } };
  });

  /* ---- Create mode ---- */

  it("renders create title when no id param", () => {
    renderEditor("/admin/voice-live/new");
    expect(
      screen.getByText("voiceLive.vlDialogCreateTitle"),
    ).toBeInTheDocument();
  });

  it("renders instance name input", () => {
    renderEditor("/admin/voice-live/new");
    expect(
      screen.getByPlaceholderText("voiceLive.instanceNamePlaceholder"),
    ).toBeInTheDocument();
  });

  it("renders generative model section", () => {
    renderEditor("/admin/voice-live/new");
    expect(
      screen.getByText("voiceLive.playgroundSection.generativeModel"),
    ).toBeInTheDocument();
  });

  it("renders speech input section", () => {
    renderEditor("/admin/voice-live/new");
    expect(
      screen.getByText("voiceLive.playgroundSection.speechInput"),
    ).toBeInTheDocument();
  });

  it("renders speech output section", () => {
    renderEditor("/admin/voice-live/new");
    expect(
      screen.getByText("voiceLive.playgroundSection.speechOutput"),
    ).toBeInTheDocument();
  });

  it("renders avatar section", () => {
    renderEditor("/admin/voice-live/new");
    expect(
      screen.getByText("voiceLive.playgroundSection.avatar"),
    ).toBeInTheDocument();
  });

  it("renders model select with default gpt-4o", () => {
    renderEditor("/admin/voice-live/new");
    expect(screen.getByTestId("model-select")).toHaveTextContent("gpt-4o");
  });

  it("renders response instruction textarea", () => {
    renderEditor("/admin/voice-live/new");
    expect(
      screen.getByText("voiceLive.playgroundSection.responseInstruction"),
    ).toBeInTheDocument();
  });

  it("renders enabled switch", () => {
    renderEditor("/admin/voice-live/new");
    expect(screen.getByText("voiceLive.instanceEnabled")).toBeInTheDocument();
  });

  it("renders apply changes and reset buttons", () => {
    renderEditor("/admin/voice-live/new");
    expect(
      screen.getByText("voiceLive.playgroundSection.applyChanges"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("voiceLive.playgroundSection.reset"),
    ).toBeInTheDocument();
  });

  it("renders voice test playground", () => {
    renderEditor("/admin/voice-live/new");
    expect(screen.getByTestId("voice-playground")).toBeInTheDocument();
  });

  it("disables playground in create mode", () => {
    renderEditor("/admin/voice-live/new");
    expect(screen.getByTestId("voice-playground")).toHaveAttribute(
      "data-disabled",
      "true",
    );
  });

  it("shows disabled message in create mode", () => {
    renderEditor("/admin/voice-live/new");
    expect(screen.getByTestId("disabled-msg")).toHaveTextContent(
      "voiceLive.playgroundSection.testPlaceholder",
    );
  });

  it("does not show assign button in create mode", () => {
    renderEditor("/admin/voice-live/new");
    expect(
      screen.queryByText("voiceLive.playgroundSection.assignToHcp"),
    ).not.toBeInTheDocument();
  });

  it("disables save button when name is empty", () => {
    renderEditor("/admin/voice-live/new");
    const applyBtn = screen
      .getByText("voiceLive.playgroundSection.applyChanges")
      .closest("button")!;
    expect(applyBtn).toBeDisabled();
  });

  /* ---- Create save ---- */

  it("does not call createMutation when name is empty and save is clicked", async () => {
    renderEditor("/admin/voice-live/new");
    const applyBtn = screen
      .getByText("voiceLive.playgroundSection.applyChanges")
      .closest("button")!;
    // Button is disabled, clicking has no effect
    await userEvent.click(applyBtn);
    expect(mockCreateMutate).not.toHaveBeenCalled();
  });

  it("calls createMutation when name is filled and save is clicked", async () => {
    renderEditor("/admin/voice-live/new");

    // Fill name
    const nameInput = screen.getByPlaceholderText(
      "voiceLive.instanceNamePlaceholder",
    );
    await userEvent.type(nameInput, "My Instance");

    const applyBtn = screen
      .getByText("voiceLive.playgroundSection.applyChanges")
      .closest("button")!;
    await userEvent.click(applyBtn);

    expect(mockCreateMutate).toHaveBeenCalledWith(
      expect.objectContaining({ name: "My Instance" }),
      expect.objectContaining({
        onSuccess: expect.any(Function),
      }),
    );
  });

  /* ---- Edit mode — loading ---- */

  it("shows loading skeleton in edit mode when loading", () => {
    mockInstanceReturn = { data: undefined, isLoading: true };
    renderEditor("/admin/voice-live/vl-1/edit");
    // Should not show the title
    expect(
      screen.queryByText("voiceLive.vlDialogEditTitle"),
    ).not.toBeInTheDocument();
  });

  /* ---- Edit mode — loaded ---- */

  it("renders edit title in edit mode", () => {
    mockInstanceReturn = { data: MOCK_INSTANCE, isLoading: false };
    renderEditor("/admin/voice-live/vl-1/edit");
    expect(
      screen.getByText("voiceLive.vlDialogEditTitle"),
    ).toBeInTheDocument();
  });

  it("populates name from instance data", () => {
    mockInstanceReturn = { data: MOCK_INSTANCE, isLoading: false };
    renderEditor("/admin/voice-live/vl-1/edit");
    const nameInput = screen.getByPlaceholderText(
      "voiceLive.instanceNamePlaceholder",
    );
    expect(nameInput).toHaveValue("Test VL Instance");
  });

  it("enables playground in edit mode", () => {
    mockInstanceReturn = { data: MOCK_INSTANCE, isLoading: false };
    renderEditor("/admin/voice-live/vl-1/edit");
    expect(screen.getByTestId("voice-playground")).toHaveAttribute(
      "data-disabled",
      "false",
    );
  });

  it("shows assign button in edit mode", () => {
    mockInstanceReturn = { data: MOCK_INSTANCE, isLoading: false };
    renderEditor("/admin/voice-live/vl-1/edit");
    expect(
      screen.getByText("voiceLive.playgroundSection.assignToHcp"),
    ).toBeInTheDocument();
  });

  /* ---- Edit save ---- */

  it("calls updateMutation when saving in edit mode", async () => {
    mockInstanceReturn = { data: MOCK_INSTANCE, isLoading: false };
    renderEditor("/admin/voice-live/vl-1/edit");

    const applyBtn = screen
      .getByText("voiceLive.playgroundSection.applyChanges")
      .closest("button")!;
    await userEvent.click(applyBtn);

    expect(mockUpdateMutate).toHaveBeenCalledWith(
      expect.objectContaining({ id: "vl-1" }),
      expect.objectContaining({
        onSuccess: expect.any(Function),
      }),
    );
  });

  it("shows success toast on update success", async () => {
    mockInstanceReturn = { data: MOCK_INSTANCE, isLoading: false };
    renderEditor("/admin/voice-live/vl-1/edit");

    const applyBtn = screen
      .getByText("voiceLive.playgroundSection.applyChanges")
      .closest("button")!;
    await userEvent.click(applyBtn);

    const call = mockUpdateMutate.mock.calls[0]!;
    const callbacks = call[1] as { onSuccess: () => void };
    callbacks.onSuccess();

    expect(toast.success).toHaveBeenCalledWith("voiceLive.instanceUpdated");
  });

  /* ---- Reset ---- */

  it("resets form to defaults in create mode when reset clicked", async () => {
    renderEditor("/admin/voice-live/new");

    // Type a name first
    const nameInput = screen.getByPlaceholderText(
      "voiceLive.instanceNamePlaceholder",
    );
    await userEvent.type(nameInput, "Something");

    // Click reset
    const resetBtn = screen
      .getByText("voiceLive.playgroundSection.reset")
      .closest("button")!;
    await userEvent.click(resetBtn);

    expect(nameInput).toHaveValue("");
  });

  /* ---- Advanced toggle sections ---- */

  it("shows response advanced settings when toggled", async () => {
    renderEditor("/admin/voice-live/new");

    // There are multiple "Advanced Settings" toggles
    const advToggles = screen.getAllByText(
      "voiceLive.playgroundSection.advancedSettings",
    );
    expect(advToggles.length).toBe(3);

    // Click the first (response advanced)
    await userEvent.click(advToggles[0]!);

    expect(
      screen.getByText("voiceLive.playgroundSection.responseTemperature"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("voiceLive.playgroundSection.proactiveEngagement"),
    ).toBeInTheDocument();
  });

  it("shows input advanced settings when toggled", async () => {
    renderEditor("/admin/voice-live/new");

    const advToggles = screen.getAllByText(
      "voiceLive.playgroundSection.advancedSettings",
    );
    // Click the second (input advanced)
    await userEvent.click(advToggles[1]!);

    expect(
      screen.getByText("voiceLive.playgroundSection.turnDetection"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("voiceLive.playgroundSection.noiseSuppression"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("voiceLive.playgroundSection.echoCancellation"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("voiceLive.playgroundSection.eouDetection"),
    ).toBeInTheDocument();
  });

  it("shows output advanced settings when toggled", async () => {
    renderEditor("/admin/voice-live/new");

    const advToggles = screen.getAllByText(
      "voiceLive.playgroundSection.advancedSettings",
    );
    // Click the third (output advanced)
    await userEvent.click(advToggles[2]!);

    expect(
      screen.getByText("voiceLive.playgroundSection.voiceTemperature"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("voiceLive.playgroundSection.playbackSpeed"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("voiceLive.playgroundSection.customLexicon"),
    ).toBeInTheDocument();
  });

  /* ---- Avatar grid ---- */

  it("renders avatar grid with filter buttons", () => {
    renderEditor("/admin/voice-live/new");
    expect(
      screen.getByText("voiceLive.vlDialogFilterAll"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("voiceLive.vlDialogFilterPhoto"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("voiceLive.vlDialogFilterVideo"),
    ).toBeInTheDocument();
  });

  it("renders avatar thumbnails from mock data", () => {
    renderEditor("/admin/voice-live/new");
    // Our mock has lisa with 2 styles + 1 photo avatar = 3 items
    const imgs = screen.getAllByRole("img");
    expect(imgs.length).toBe(3);
  });

  it("filters avatars by photo filter", async () => {
    renderEditor("/admin/voice-live/new");
    await userEvent.click(
      screen.getByText("voiceLive.vlDialogFilterPhoto").closest("button")!,
    );
    // Only photo avatar should remain
    const imgs = screen.getAllByRole("img");
    expect(imgs.length).toBe(1);
  });

  it("filters avatars by video filter", async () => {
    renderEditor("/admin/voice-live/new");
    await userEvent.click(
      screen.getByText("voiceLive.vlDialogFilterVideo").closest("button")!,
    );
    // Only video avatars (lisa with 2 styles)
    const imgs = screen.getAllByRole("img");
    expect(imgs.length).toBe(2);
  });

  /* ---- Avatar enabled toggle ---- */

  it("hides avatar grid when avatar is disabled", async () => {
    renderEditor("/admin/voice-live/new");
    // Find the avatar enabled switch and toggle it off
    const enableLabel = screen.getByText(
      "voiceLive.playgroundSection.enableAvatar",
    );
    // The switch is nearby
    // Avatar enabled switch is one of several; the label text helps identify
    // Toggle the avatar switch (last switch in avatar section area)
    // We use the label's sibling approach - find the switch by searching near enableAvatar
    const avatarRow = enableLabel.closest("div")!;
    const avatarSwitch = avatarRow.querySelector('[role="switch"]')!;
    await userEvent.click(avatarSwitch);

    // Filter buttons should disappear
    expect(
      screen.queryByText("voiceLive.vlDialogFilterAll"),
    ).not.toBeInTheDocument();
  });

  /* ---- Language selector ---- */

  it("renders language selector", () => {
    renderEditor("/admin/voice-live/new");
    expect(
      screen.getByText("voiceLive.playgroundSection.language"),
    ).toBeInTheDocument();
  });

  /* ---- Auto-detect language switch ---- */

  it("renders auto-detect language switch", () => {
    renderEditor("/admin/voice-live/new");
    expect(
      screen.getByText("voiceLive.playgroundSection.autoDetectLanguage"),
    ).toBeInTheDocument();
  });

  /* ---- Voice selector ---- */

  it("renders voice selector", () => {
    renderEditor("/admin/voice-live/new");
    expect(
      screen.getByText("voiceLive.playgroundSection.voice"),
    ).toBeInTheDocument();
  });

  /* ---- Assign dialog ---- */

  it("opens assign dialog when assign button is clicked", async () => {
    mockInstanceReturn = { data: MOCK_INSTANCE, isLoading: false };
    mockHcpReturn = {
      data: {
        items: [
          { ...MOCK_HCP, id: "hcp-2", name: "Dr. Jones", voice_live_instance_id: null },
        ],
      },
    };
    renderEditor("/admin/voice-live/vl-1/edit");

    await userEvent.click(
      screen
        .getByText("voiceLive.playgroundSection.assignToHcp")
        .closest("button")!,
    );

    expect(
      screen.getByText("voiceLive.assignDialogTitle"),
    ).toBeInTheDocument();
  });

  it("shows assigned HCP count badge", () => {
    mockInstanceReturn = { data: MOCK_INSTANCE, isLoading: false };
    mockHcpReturn = { data: { items: [MOCK_HCP] } };
    renderEditor("/admin/voice-live/vl-1/edit");

    expect(screen.getByText("(1)")).toBeInTheDocument();
  });

  /* ── VoiceTestPlayground props — critical routing tests ──────────── */

  it("always passes vlInstanceId to playground in edit mode, never hcpProfileId", () => {
    mockInstanceReturn = { data: MOCK_INSTANCE, isLoading: false };
    mockHcpReturn = { data: { items: [MOCK_HCP] } };
    renderEditor("/admin/voice-live/vl-1/edit");

    const pg = screen.getByTestId("voice-playground");
    expect(pg).toHaveAttribute("data-vl-instance-id", "vl-1");
    expect(pg).toHaveAttribute("data-hcp-profile-id", "");
  });

  it("passes vlInstanceId even when multiple HCPs assigned (no hcpProfileId leak)", () => {
    mockInstanceReturn = { data: MOCK_INSTANCE, isLoading: false };
    const hcp2 = { ...MOCK_HCP, id: "hcp-2", name: "Dr. Jones", agent_id: "asst_jones", agent_sync_status: "synced" as const };
    mockHcpReturn = { data: { items: [MOCK_HCP, hcp2] } };
    renderEditor("/admin/voice-live/vl-1/edit");

    const pg = screen.getByTestId("voice-playground");
    expect(pg).toHaveAttribute("data-vl-instance-id", "vl-1");
    expect(pg).toHaveAttribute("data-hcp-profile-id", "");
  });

  it("passes model_instruction as systemPrompt", () => {
    mockInstanceReturn = { data: { ...MOCK_INSTANCE, model_instruction: "You are an English teacher" }, isLoading: false };
    renderEditor("/admin/voice-live/vl-1/edit");

    expect(screen.getByTestId("voice-playground")).toHaveAttribute(
      "data-system-prompt",
      "You are an English teacher",
    );
  });

  it("passes avatar props when avatar is enabled", () => {
    mockInstanceReturn = { data: MOCK_INSTANCE, isLoading: false };
    renderEditor("/admin/voice-live/vl-1/edit");

    const pg = screen.getByTestId("voice-playground");
    expect(pg).toHaveAttribute("data-avatar-enabled", "true");
    expect(pg).toHaveAttribute("data-avatar-character", "lisa");
    expect(pg).toHaveAttribute("data-avatar-style", "casual-sitting");
  });

  it("clears avatar character/style when avatar is disabled", () => {
    mockInstanceReturn = {
      data: { ...MOCK_INSTANCE, avatar_enabled: false },
      isLoading: false,
    };
    renderEditor("/admin/voice-live/vl-1/edit");

    const pg = screen.getByTestId("voice-playground");
    expect(pg).toHaveAttribute("data-avatar-enabled", "false");
    expect(pg).toHaveAttribute("data-avatar-character", "");
    expect(pg).toHaveAttribute("data-avatar-style", "");
  });

  it("uses first assigned HCP name for hcpName, falls back to instance name", () => {
    mockInstanceReturn = { data: MOCK_INSTANCE, isLoading: false };
    mockHcpReturn = { data: { items: [MOCK_HCP] } };
    renderEditor("/admin/voice-live/vl-1/edit");

    expect(screen.getByTestId("voice-playground")).toHaveAttribute(
      "data-hcp-name",
      "Dr. Smith",
    );
  });

  it("falls back to instance name for hcpName when no HCPs assigned", () => {
    mockInstanceReturn = { data: MOCK_INSTANCE, isLoading: false };
    mockHcpReturn = { data: { items: [] } };
    renderEditor("/admin/voice-live/vl-1/edit");

    expect(screen.getByTestId("voice-playground")).toHaveAttribute(
      "data-hcp-name",
      "Test VL Instance",
    );
  });

  it("does not pass vlInstanceId in create mode (undefined)", () => {
    renderEditor("/admin/voice-live/new");
    expect(screen.getByTestId("voice-playground")).toHaveAttribute(
      "data-vl-instance-id",
      "",
    );
  });
});
