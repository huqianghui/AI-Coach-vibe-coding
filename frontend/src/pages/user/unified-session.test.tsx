import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { toast } from "sonner";
import UnifiedSession from "./unified-session";
import type { SessionMessageStreamCallbacks } from "@/api/sessions";
import type { TranscriptSegment } from "@/types/voice-live";

// Mock hooks
const mockSession = {
  id: "session-1",
  scenario_id: "scenario-1",
  status: "in_progress",
  mode: "voice_realtime_model",
  key_messages_status: JSON.stringify([
    { message: "Key point 1", delivered: false, detected_at: null },
    { message: "Key point 2", delivered: false, detected_at: null },
  ]),
};

const mockScenario = {
  id: "scenario-1",
  name: "Test Scenario",
  description: "Test description",
  mode: "f2f" as const,
  difficulty: "medium" as const,
  status: "active" as const,
  hcp_profile_id: "hcp-1",
  hcp_profile: {
    id: "hcp-1",
    name: "Dr. Zhang",
    specialty: "Oncology",
    personality_type: "friendly",
    avatar_character: "lisa",
    avatar_style: "casual-sitting",
    voice_live_enabled: true,
    avatar_enabled: true,
  },
  key_messages: ["Key point 1", "Key point 2"],
  skill_id: "skill-1",
  skill_version_id: null,
  rubric_id: "rubric-1",
  pass_threshold: 70,
  created_by: "admin",
  created_at: "2026-01-01",
  updated_at: "2026-01-01",
};

const mockSessionState = {
  data: mockSession,
  isLoading: false,
  isError: false,
};
const mockScenarioState = {
  data: mockScenario,
  isLoading: false,
  isError: false,
};

vi.mock("react-i18next", () => ({
  useTranslation: (ns?: string) => ({
    t: (key: string) => `${ns}:${key}`,
    i18n: { language: "zh-CN" },
  }),
}));

vi.mock("sonner", () => ({
  toast: { error: vi.fn(), warning: vi.fn() },
}));

vi.mock("@/hooks/use-session", () => ({
  useSession: () => mockSessionState,
  useEndSession: () => ({
    mutateAsync: vi.fn().mockResolvedValue({}),
  }),
}));

vi.mock("@/hooks/use-scenarios", () => ({
  useScenario: () => mockScenarioState,
}));

const mockVoiceLive = {
  connectionState: "disconnected" as const,
  audioState: "idle" as const,
  isMuted: false,
  toggleMute: vi.fn(),
  sendTextMessage: vi.fn().mockResolvedValue(undefined),
  sendAudio: vi.fn(),
  send: vi.fn(),
  connect: vi.fn(),
  disconnect: vi.fn().mockResolvedValue(undefined),
  avatarSdpCallbackRef: { current: null },
};

const mockStartSession = vi.fn().mockResolvedValue({
  avatarEnabled: true,
  model: "gpt-4o-realtime",
  mode: "model",
});
const mockStopSession = vi.fn().mockResolvedValue(undefined);
const mockStreamSessionMessage = vi.fn().mockResolvedValue(undefined);
let voiceLiveOptions: {
  onTranscript: (segment: TranscriptSegment) => void;
  onConnectionStateChange: (state: string) => void;
  onError: (error: unknown) => void;
};

vi.mock("@/hooks/use-voice-live", () => ({
  useVoiceLive: (options: typeof voiceLiveOptions) => {
    voiceLiveOptions = options;
    return mockVoiceLive;
  },
}));

vi.mock("@/hooks/use-avatar-stream", () => ({
  useAvatarStream: () => ({
    isConnected: false,
    connect: vi.fn(),
    handleServerSdp: vi.fn(),
    disconnect: vi.fn(),
  }),
}));

vi.mock("@/hooks/use-audio-handler", () => ({
  useAudioHandler: () => ({
    initialize: vi.fn().mockResolvedValue(undefined),
    startRecording: vi.fn(),
    cleanup: vi.fn(),
    streamRef: { current: null },
  }),
}));

vi.mock("@/hooks/use-audio-player", () => ({
  useAudioPlayer: () => ({
    playAudio: vi.fn(),
    stopAudio: vi.fn(),
  }),
}));

vi.mock("@/hooks/use-voice-session-lifecycle", () => ({
  useVoiceSessionLifecycle: () => ({
    startSession: mockStartSession,
    stopSession: mockStopSession,
    isBusy: false,
  }),
}));

vi.mock("@/hooks/use-config", () => ({
  useFeatureFlags: () => ({
    data: {
      features: {
        voice_live_enabled: true,
        avatar_enabled: true,
      },
    },
  }),
}));

vi.mock("@/api/sessions", () => ({
  streamSessionMessage: (...args: unknown[]) => mockStreamSessionMessage(...args),
}));

vi.mock("@/api/voice-live", () => ({
  persistTranscriptMessage: vi.fn().mockResolvedValue(undefined),
}));

vi.mock("@/lib/voice-logger", () => ({
  createVoiceLogger: () => ({
    info: vi.fn(),
    error: vi.fn(),
    warn: vi.fn(),
  }),
  getEventSummary: () => ({}),
}));

vi.mock("@/components/voice/voice-session-header", () => ({
  VoiceSessionHeader: ({
    scenarioTitle,
    currentMode,
    availableModes,
    onEndSession,
    onModeChange,
  }: {
    scenarioTitle: string;
    currentMode: string;
    availableModes?: string[];
    onEndSession: () => void;
    onModeChange: (mode: "text" | "voice_realtime_model" | "digital_human_realtime_model") => void;
  }) => (
    <header data-testid="voice-session-header">
      <span>{scenarioTitle}</span>
      <span data-testid="current-mode">{currentMode}</span>
      <span data-testid="available-modes">{availableModes?.join(",")}</span>
      <button data-testid="end-session-btn" onClick={onEndSession}>End</button>
      <button data-testid="switch-text" onClick={() => onModeChange("text")}>Text</button>
      <button data-testid="switch-voice" onClick={() => onModeChange("voice_realtime_model")}>Voice</button>
      <button data-testid="switch-avatar" onClick={() => onModeChange("digital_human_realtime_model")}>Avatar</button>
    </header>
  ),
}));

vi.mock("@/components/voice/avatar-view", () => ({
  AvatarView: ({
    hcpName,
    isDigitalHumanMode,
  }: {
    hcpName: string;
    isDigitalHumanMode: boolean;
  }) => (
    <div data-testid="avatar-view" data-digital-human={String(isDigitalHumanMode)}>
      {hcpName}
    </div>
  ),
}));

vi.mock("@/components/voice/voice-transcript", () => ({
  VoiceTranscript: ({ transcripts }: { transcripts: unknown[] }) => (
    <div data-testid="voice-transcript">{transcripts.length} segments</div>
  ),
}));

vi.mock("@/components/voice/voice-controls", () => ({
  VoiceControls: ({
    onEndSession,
    onToggleKeyboard,
  }: {
    onEndSession?: () => void;
    onToggleKeyboard?: () => void;
  }) => (
    <div data-testid="voice-controls">
      <button data-testid="end-call-btn" onClick={onEndSession}>End Call</button>
      <button data-testid="toggle-keyboard" onClick={onToggleKeyboard}>Keyboard</button>
    </div>
  ),
}));

vi.mock("@/components/coach/scenario-panel", () => ({
  ScenarioPanel: ({
    scenario,
    keyMessagesStatus,
    isCollapsed,
    onToggle,
  }: {
    scenario: { name: string };
    keyMessagesStatus: Array<{ message: string; delivered: boolean }>;
    isCollapsed: boolean;
    onToggle: () => void;
  }) => (
    <div data-testid="scenario-panel">
      {scenario.name}:{String(isCollapsed)}:{keyMessagesStatus.map((item) => `${item.message}-${item.delivered}`).join(",")}
      <button data-testid="toggle-scenario" onClick={onToggle}>Toggle scenario</button>
    </div>
  ),
}));

vi.mock("@/components/coach/hints-panel", () => ({
  HintsPanel: ({
    hints,
    keyMessagesStatus,
    isCollapsed,
    onToggle,
  }: {
    hints: Array<{ message: string }>;
    keyMessagesStatus: Array<{ delivered: boolean }>;
    isCollapsed: boolean;
    onToggle: () => void;
  }) => (
    <div data-testid="hints-panel">
      {hints.length} hints:{hints.map((hint) => hint.message).join(",")}:{keyMessagesStatus.filter((item) => item.delivered).length} delivered:{String(isCollapsed)}
      <button data-testid="toggle-hints" onClick={onToggle}>Toggle hints</button>
    </div>
  ),
}));

function renderWithProviders(searchParams = "?id=session-1") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/user/training/session${searchParams}`]}>
        <Routes>
          <Route path="/user/training/session" element={<UnifiedSession />} />
          <Route path="/user/training" element={<div data-testid="training-page" />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("UnifiedSession", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockSession.mode = "voice_realtime_model";
    mockSessionState.data = mockSession;
    mockSessionState.isLoading = false;
    mockSessionState.isError = false;
    mockScenarioState.data = mockScenario;
    mockScenarioState.isLoading = false;
    mockScenarioState.isError = false;
    mockScenario.hcp_profile.voice_live_enabled = true;
    mockScenario.hcp_profile.avatar_enabled = true;
    mockStartSession.mockResolvedValue({
      avatarEnabled: true,
      model: "gpt-4o-realtime",
      mode: "model",
    });
    mockStreamSessionMessage.mockResolvedValue(undefined);
  });

  it("renders the voice session header with scenario title", () => {
    renderWithProviders();
    expect(screen.getByTestId("voice-session-header")).toBeInTheDocument();
    expect(screen.getAllByText("Test Scenario").length).toBeGreaterThanOrEqual(1);
  });

  it("renders the avatar view with HCP name", () => {
    renderWithProviders();
    expect(screen.getByTestId("avatar-view")).toBeInTheDocument();
    expect(screen.getByText("Dr. Zhang")).toBeInTheDocument();
  });

  it("renders the scenario panel for training context", () => {
    renderWithProviders();
    expect(screen.getByTestId("scenario-panel")).toBeInTheDocument();
  });

  it("renders the hints panel", () => {
    renderWithProviders();
    expect(screen.getByTestId("hints-panel")).toBeInTheDocument();
  });

  it("renders voice controls", () => {
    renderWithProviders();
    expect(screen.getByTestId("voice-controls")).toBeInTheDocument();
  });

  it("renders start session button before session starts", () => {
    renderWithProviders();
    expect(screen.getByTestId("start-session-btn")).toBeInTheDocument();
  });

  it("offers only the persisted server-owned mode in the session header", () => {
    renderWithProviders();
    expect(screen.getByTestId("available-modes")).toHaveTextContent(
      "voice_realtime_model",
    );
  });

  it("does not advertise voice or avatar switching for a text session", () => {
    mockSession.mode = "text";
    renderWithProviders();
    expect(screen.getByTestId("available-modes")).toHaveTextContent("text");
  });

  it("fails closed for voice mode without starting a transport", async () => {
    mockSession.mode = "voice_realtime_model";
    renderWithProviders();

    fireEvent.click(screen.getByTestId("start-session-btn"));

    await waitFor(() => expect(screen.getByTestId("transport-unavailable")).toBeVisible());
    expect(mockStartSession).not.toHaveBeenCalled();
  });

  it("rejects a client-only text to voice switch", async () => {
    mockSession.mode = "text";
    renderWithProviders();

    fireEvent.click(screen.getByTestId("switch-voice"));

    await waitFor(() => {
      expect(mockStartSession).not.toHaveBeenCalled();
      expect(screen.getByTestId("current-mode")).toHaveTextContent("text");
    });
  });

  it("rejects a client-only voice to digital-human switch", async () => {
    renderWithProviders();

    fireEvent.click(screen.getByTestId("switch-avatar"));

    await waitFor(() => {
      expect(mockStartSession).not.toHaveBeenCalled();
      expect(screen.getByTestId("current-mode")).toHaveTextContent("voice_realtime_model");
    });
  });

  it("treats selecting the current mode as a no-op without an error toast", () => {
    renderWithProviders();

    fireEvent.click(screen.getByTestId("switch-voice"));

    expect(toast.error).not.toHaveBeenCalled();
    expect(screen.getByTestId("current-mode")).toHaveTextContent("voice_realtime_model");
  });

  it("fails closed for digital human mode and keeps the requested mode", async () => {
    mockSession.mode = "digital_human_realtime_model";
    renderWithProviders();

    expect(screen.getByTestId("transport-unavailable")).toBeVisible();
    expect(screen.getByTestId("current-mode")).toHaveTextContent(
      "digital_human_realtime_model",
    );
    expect(mockStartSession).not.toHaveBeenCalled();
  });

  it("hides start button after acknowledging unavailable transport", async () => {
    renderWithProviders();
    fireEvent.click(screen.getByTestId("start-session-btn"));
    await waitFor(() => {
      expect(screen.queryByTestId("start-session-btn")).not.toBeInTheDocument();
    });
  });

  it("renders text input area for MR to type messages", () => {
    renderWithProviders();
    expect(screen.getByTestId("text-input")).toBeInTheDocument();
    expect(screen.getByTestId("send-btn")).toBeInTheDocument();
  });

  it("shows end session confirmation dialog", async () => {
    renderWithProviders();
    fireEvent.click(screen.getByTestId("end-session-btn"));
    await waitFor(() => {
      expect(screen.getByText("session:endSessionConfirm")).toBeInTheDocument();
    });
  });

  it("renders the session error fallback and navigates back to training", async () => {
    mockSessionState.isError = true;
    renderWithProviders();

    expect(screen.getByText("session:error.loadFailed")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "common:back" }));

    await waitFor(() => expect(screen.getByTestId("training-page")).toBeVisible());
  });

  it("renders the same fail-closed fallback when scenario loading fails", () => {
    mockScenarioState.isError = true;
    renderWithProviders();

    expect(screen.getByText("session:error.loadFailed")).toBeVisible();
    expect(screen.queryByTestId("voice-session-header")).not.toBeInTheDocument();
  });

  it("renders loading while session data is pending or absent", () => {
    mockSessionState.isLoading = true;
    renderWithProviders();

    expect(screen.getByText("session:loading")).toBeVisible();
  });

  it("renders loading while the session scenario is pending", () => {
    mockScenarioState.isLoading = true;
    renderWithProviders();

    expect(screen.getByText("session:loading")).toBeVisible();
  });

  it("does not submit empty text", () => {
    renderWithProviders();
    const sendBtn = screen.getByTestId("send-btn");
    expect(sendBtn).toBeDisabled();
  });

  it("fails closed by disabling text submission in a voice session", () => {
    renderWithProviders();
    const input = screen.getByTestId("text-input");

    expect(input).toBeDisabled();
    fireEvent.change(input, { target: { value: "must not send" } });
    fireEvent.keyDown(input, { key: "Enter" });

    expect(mockStreamSessionMessage).not.toHaveBeenCalled();
  });

  it("hides and restores the keyboard through voice controls", () => {
    renderWithProviders();

    fireEvent.click(screen.getByTestId("toggle-keyboard"));
    expect(screen.queryByTestId("text-input")).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId("toggle-keyboard"));
    expect(screen.getByTestId("text-input")).toBeVisible();
  });

  it("handles text input and clears on submit", async () => {
    mockSession.mode = "text";
    renderWithProviders();
    const input = screen.getByTestId("text-input") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "Hello doctor" } });
    expect(input.value).toBe("Hello doctor");

    const sendBtn = screen.getByTestId("send-btn");
    fireEvent.click(sendBtn);

    await waitFor(() => {
      expect(input.value).toBe("");
    });
    expect(mockStreamSessionMessage).toHaveBeenCalledWith(
      "session-1",
      "Hello doctor",
      expect.any(Object),
      expect.any(AbortSignal),
    );
  });

  it("submits text on Enter key", async () => {
    mockSession.mode = "text";
    renderWithProviders();
    const input = screen.getByTestId("text-input") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "Test message" } });
    fireEvent.keyDown(input, { key: "Enter" });

    await waitFor(() => {
      expect(input.value).toBe("");
    });
  });

  it("disables duplicate sends while the server turn is in progress", async () => {
    mockSession.mode = "text";
    mockStreamSessionMessage.mockImplementation(
      async (_id, _message, callbacks: SessionMessageStreamCallbacks) => {
        callbacks.onState({ code: "SESSION_TURN_IN_PROGRESS", status: "in_progress" });
        await new Promise(() => undefined);
      },
    );
    renderWithProviders();
    fireEvent.change(screen.getByTestId("text-input"), { target: { value: "Hello" } });
    fireEvent.click(screen.getByTestId("send-btn"));

    await waitFor(() => expect(screen.getByTestId("send-btn")).toBeDisabled());
    fireEvent.click(screen.getByTestId("send-btn"));
    expect(mockStreamSessionMessage).toHaveBeenCalledTimes(1);
  });

  it("resumes a disconnected server turn without duplicating the user message", async () => {
    mockSession.mode = "text";
    mockStreamSessionMessage
      .mockRejectedValueOnce(new TypeError("network disconnected"))
      .mockImplementationOnce(
        async (_id, _message, callbacks: SessionMessageStreamCallbacks) => {
          callbacks.onState({ code: "SESSION_TURN_RESUMED", status: "in_progress" });
          callbacks.onText("Winner");
          callbacks.onDone();
        },
      );
    renderWithProviders();
    fireEvent.change(screen.getByTestId("text-input"), { target: { value: "Hello" } });
    fireEvent.click(screen.getByTestId("send-btn"));

    await waitFor(() => expect(screen.getByTestId("resume-turn-btn")).toBeVisible());
    fireEvent.click(screen.getByTestId("resume-turn-btn"));

    await waitFor(() => expect(mockStreamSessionMessage).toHaveBeenCalledTimes(2));
    expect(screen.getByTestId("voice-transcript")).toHaveTextContent("2 segments");
    expect(mockStreamSessionMessage.mock.calls[1]![1]).toBe("Hello");
  });

  it("does not duplicate an assistant bubble when a winner is replayed", async () => {
    mockSession.mode = "text";
    mockStreamSessionMessage.mockImplementation(
      async (_id, _message, callbacks: SessionMessageStreamCallbacks) => {
        callbacks.onState({ code: "SESSION_TURN_RESUMED", status: "in_progress" });
        callbacks.onText("Committed winner");
        callbacks.onDone();
        callbacks.onText("Committed winner");
        callbacks.onDone();
      },
    );
    renderWithProviders();
    fireEvent.change(screen.getByTestId("text-input"), { target: { value: "Hello" } });
    fireEvent.click(screen.getByTestId("send-btn"));

    await waitFor(() => expect(screen.getByTestId("turn-status")).toHaveTextContent("succeeded"));
    expect(screen.getByTestId("voice-transcript")).toHaveTextContent("2 segments");
  });

  it("applies streamed hints and authoritative key-message status", async () => {
    mockSession.mode = "text";
    mockStreamSessionMessage.mockImplementation(
      async (_id, _message, callbacks: SessionMessageStreamCallbacks) => {
        callbacks.onHint({ content: "Ask an open question" });
        callbacks.onKeyMessages([
          { message: "Key point 1", delivered: true, detected_at: "2026-01-01" },
        ]);
        callbacks.onDone();
      },
    );
    renderWithProviders();
    fireEvent.change(screen.getByTestId("text-input"), { target: { value: "Hello" } });
    fireEvent.click(screen.getByTestId("send-btn"));

    await waitFor(() => {
      expect(screen.getByTestId("hints-panel")).toHaveTextContent("Ask an open question");
      expect(screen.getByTestId("hints-panel")).toHaveTextContent("1 delivered");
      expect(screen.getByTestId("scenario-panel")).toHaveTextContent("Key point 1-true");
    });
  });

  it("renders a terminal stream error and reports it to the user", async () => {
    mockSession.mode = "text";
    mockStreamSessionMessage.mockImplementation(
      async (_id, _message, callbacks: SessionMessageStreamCallbacks) => {
        callbacks.onError({ code: "TURN_FAILED", message: "Coach unavailable" });
      },
    );
    renderWithProviders();
    fireEvent.change(screen.getByTestId("text-input"), { target: { value: "Hello" } });
    fireEvent.click(screen.getByTestId("send-btn"));

    await waitFor(() => {
      expect(screen.getByTestId("turn-status")).toHaveTextContent("failed_terminal");
      expect(screen.getByText("Coach unavailable")).toBeVisible();
      expect(toast.error).toHaveBeenCalledWith("Coach unavailable");
    });
  });

  it.each([
    ["SESSION_TURN_RECONCILING", "reconciling"],
    ["SESSION_TURN_FAILED", "failed_terminal"],
    ["SESSION_TURN_ACCEPTED", "accepted"],
  ] as const)("maps %s stream state to %s", async (code, expectedStatus) => {
    mockSession.mode = "text";
    mockStreamSessionMessage.mockImplementation(
      async (_id, _message, callbacks: SessionMessageStreamCallbacks) => {
        callbacks.onState({ code, status: "in_progress" });
      },
    );
    renderWithProviders();
    fireEvent.change(screen.getByTestId("text-input"), { target: { value: "Hello" } });
    fireEvent.click(screen.getByTestId("send-btn"));

    await waitFor(() => {
      expect(screen.getByTestId("turn-status")).toHaveTextContent(expectedStatus);
    });
  });

  it("ignores an aborted text stream instead of showing a disconnect error", async () => {
    mockSession.mode = "text";
    mockStreamSessionMessage.mockRejectedValue(new DOMException("aborted", "AbortError"));
    renderWithProviders();
    fireEvent.change(screen.getByTestId("text-input"), { target: { value: "Hello" } });
    fireEvent.click(screen.getByTestId("send-btn"));

    await waitFor(() => expect(mockStreamSessionMessage).toHaveBeenCalledOnce());
    expect(screen.queryByText("voice:turn.disconnected")).not.toBeInTheDocument();
  });

  it("handles voice connection errors but ignores non-error state changes", () => {
    renderWithProviders();

    voiceLiveOptions.onConnectionStateChange("connected");
    expect(toast.error).not.toHaveBeenCalled();
    voiceLiveOptions.onConnectionStateChange("error");
    expect(toast.error).toHaveBeenCalledWith("voice:error.connectionFailed");
    expect(() => voiceLiveOptions.onError(new Error("socket failed"))).not.toThrow();
  });

  it("merges partial voice transcript chunks and replaces them with the final segment", async () => {
    renderWithProviders();

    voiceLiveOptions.onTranscript({
      id: "voice-1",
      role: "assistant",
      content: "Hello ",
      isFinal: false,
      timestamp: 1,
    });
    voiceLiveOptions.onTranscript({
      id: "voice-1",
      role: "assistant",
      content: "doctor",
      isFinal: false,
      timestamp: 2,
    });
    voiceLiveOptions.onTranscript({
      id: "voice-1",
      role: "assistant",
      content: "Hello doctor",
      isFinal: true,
      timestamp: 3,
    });

    await waitFor(() => expect(screen.getByTestId("voice-transcript")).toHaveTextContent("1 segments"));
  });

  it("toggles both collapsible coaching panels", () => {
    renderWithProviders();

    fireEvent.click(screen.getByTestId("toggle-scenario"));
    fireEvent.click(screen.getByTestId("toggle-hints"));

    expect(screen.getByTestId("scenario-panel")).toHaveTextContent("true");
    expect(screen.getByTestId("hints-panel")).toHaveTextContent("true");
  });
});
