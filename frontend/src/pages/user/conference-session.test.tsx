import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, act, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import ConferenceSession from "./conference-session";
import type { ConferenceSSECallbacks } from "@/hooks/use-conference-sse";

const mockNavigate = vi.fn();
const mockSendMessage = vi.fn();
const mockMutateAsync = vi.fn().mockResolvedValue(undefined);
const mockStartRecording = vi.fn();
const mockStopRecording = vi.fn();
const mockSpeak = vi.fn();
const mockStopSpeaking = vi.fn();
const mockSessionRecorderStart = vi.fn().mockResolvedValue(true);
const mockSessionRecorderStopAndUpload = vi.fn().mockResolvedValue({ success: true });
const mockSessionRecorderCancel = vi.fn().mockResolvedValue(undefined);
const mockToastError = vi.hoisted(() => vi.fn());
const mockAvatarStreamConnect = vi.fn().mockResolvedValue(undefined);
const mockAvatarStreamDisconnect = vi.fn();
const mockAvatarHandleServerSdp = vi.fn().mockResolvedValue(undefined);
const mockVoiceLiveConnect = vi.fn().mockResolvedValue({
  avatarEnabled: true,
  model: "gpt-4o",
  mode: "model",
  iceServers: [],
});
const mockVoiceLiveDisconnect = vi.fn().mockResolvedValue(undefined);
const mockVoiceLiveSend = vi.fn();
const mockAvatarSdpCallbackRef = { current: null as ((serverSdp: string) => void) | null };
const mockGetHcpProfile = vi.hoisted(() =>
  vi.fn((id = "hp-1") =>
    Promise.resolve({
      id,
      name: id === "hp-2" ? "Dr. Zhang Wei" : "Dr. Smith",
      voice_name: "zh-CN-XiaoxiaoNeural",
      voice_live_instance: {
        id: id === "hp-2" ? "vli-2" : "vli-1",
        name: id === "hp-2" ? "中文男声 2" : "中文男声 1",
        voice_live_model: "gpt-4o",
        enabled: true,
        voice_name: id === "hp-2" ? "zh-CN-YunxiNeural" : "zh-CN-YunjianNeural",
        avatar_character: "lisa",
        avatar_style: "casual-sitting",
        avatar_enabled: true,
      },
      voice_live_enabled: true,
      avatar_enabled: true,
      avatar_character: "lisa",
      avatar_style: "casual-sitting",
    }),
  ),
);

let capturedCallbacks: ConferenceSSECallbacks = {};
let mockRecordingState = "idle";
let mockSpeechError: string | null = null;
let mockSessionData: Record<string, unknown> | undefined;
let mockScenarioAudienceHcps: Record<string, unknown>[] | undefined;
let mockSearchParams = new URLSearchParams("id=cs-1");
let mockIsSpeaking = false;
let mockSessionRecorderIsRecording = false;
let capturedSpeechOptions: Record<string, unknown> = {};
let capturedTextToSpeechOptions: Record<string, unknown> = {};
let capturedVoiceLiveOptions: Record<string, unknown> = {};

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { changeLanguage: vi.fn(), language: "en" },
  }),
}));

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>(
    "react-router-dom",
  );
  return {
    ...actual,
    useNavigate: () => mockNavigate,
    useSearchParams: () => [mockSearchParams, vi.fn()],
  };
});

vi.mock("@/hooks/use-conference", () => ({
  useConferenceSession: () => ({
    data: mockSessionData,
    isLoading: false,
  }),
  useAudienceHcps: () => ({
    data: mockScenarioAudienceHcps,
    isLoading: false,
  }),
  useEndConferenceSession: () => ({
    mutateAsync: mockMutateAsync,
    isPending: false,
  }),
}));

vi.mock("@/hooks/use-conference-sse", () => ({
  useConferenceSSE: (
    _sessionId: string,
    callbacks: ConferenceSSECallbacks,
  ) => {
    capturedCallbacks = callbacks;
    return {
      sendMessage: mockSendMessage,
      isStreaming: false,
      streamedText: "",
      abort: vi.fn(),
    };
  },
}));

vi.mock("@/hooks/use-speech", () => ({
  useStreamingSpeechInput: (
    _onTranscribed: unknown,
    _language: string,
    options: Record<string, unknown>,
  ) => {
    capturedSpeechOptions = options;
    return {
      startRecording: mockStartRecording,
      stopRecording: mockStopRecording,
      recordingState: mockRecordingState,
      error: mockSpeechError,
    };
  },
  useTextToSpeech: (
    _language: string,
    _voice: string | undefined,
    options: Record<string, unknown>,
  ) => {
    capturedTextToSpeechOptions = options;
    return {
      speak: mockSpeak,
      stop: mockStopSpeaking,
      isSpeaking: mockIsSpeaking,
    };
  },
}));

vi.mock("@/hooks/use-session-recorder", () => ({
  useSessionRecorder: () => ({
    isRecording: mockSessionRecorderIsRecording,
    startRecording: mockSessionRecorderStart,
    stopAndUpload: mockSessionRecorderStopAndUpload,
    cancel: mockSessionRecorderCancel,
  }),
}));

vi.mock("@/api/hcp-profiles", () => ({
  getHcpProfile: mockGetHcpProfile,
}));

vi.mock("@/hooks/use-avatar-stream", () => ({
  useAvatarStream: () => ({
    connect: mockAvatarStreamConnect,
    disconnect: mockAvatarStreamDisconnect,
    handleServerSdp: mockAvatarHandleServerSdp,
    isConnected: true,
  }),
}));

vi.mock("@/hooks/use-voice-live", () => ({
  useVoiceLive: (options: Record<string, unknown>) => {
    capturedVoiceLiveOptions = options;
    return {
      connect: mockVoiceLiveConnect,
      disconnect: mockVoiceLiveDisconnect,
      send: mockVoiceLiveSend,
      sendTextMessage: vi.fn(),
      sendAudio: vi.fn(),
      toggleMute: vi.fn(),
      isMuted: false,
      connectionState: "connected",
      audioState: "idle",
      avatarSdpCallbackRef: mockAvatarSdpCallbackRef,
    };
  },
}));

vi.mock("sonner", () => ({
  toast: {
    error: mockToastError,
  },
}));

vi.mock("@/contexts/config-context", () => ({
  useConfig: () => ({
    avatar_enabled: false,
    voice_enabled: false,
    realtime_voice_enabled: false,
    conference_enabled: true,
    voice_live_enabled: false,
    default_voice_mode: "text_only",
    region: "global",
  }),
}));

vi.mock("@/components/ui", () => ({
  Dialog: ({
    children,
    open,
  }: {
    children: React.ReactNode;
    open: boolean;
  }) => (open ? <div data-testid="dialog">{children}</div> : null),
  DialogContent: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  DialogDescription: ({ children }: { children: React.ReactNode }) => (
    <p>{children}</p>
  ),
  DialogFooter: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  DialogHeader: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  DialogTitle: ({ children }: { children: React.ReactNode }) => (
    <h2>{children}</h2>
  ),
  Button: ({
    children,
    onClick,
  }: {
    children: React.ReactNode;
    onClick?: () => void;
    variant?: string;
  }) => <button onClick={onClick}>{children}</button>,
}));

// Capture props passed to child components for verification
let capturedConferenceHeaderProps: Record<string, unknown> = {};
let capturedTopicGuideProps: Record<string, unknown> = {};
let capturedConferenceStageProps: Record<string, unknown> = {};
let capturedTranscriptionPanelProps: Record<string, unknown> = {};
let capturedAudiencePanelProps: Record<string, unknown> = {};
let capturedQuestionQueueProps: Record<string, unknown> = {};

vi.mock("@/components/conference", () => ({
  ConferenceHeader: (props: Record<string, unknown>) => {
    capturedConferenceHeaderProps = props;
    return (
      <div data-testid="conference-header">
        <button onClick={props.onEndSession as () => void}>End</button>
      </div>
    );
  },
  TopicGuide: (props: Record<string, unknown>) => {
    capturedTopicGuideProps = props;
    return (
      <div data-testid="topic-guide">
        {props.scenarioName as string}
        <button onClick={props.onToggle as () => void}>ToggleLeft</button>
      </div>
    );
  },
  ConferenceStage: (props: Record<string, unknown>) => {
    capturedConferenceStageProps = props;
    return (
      <div data-testid="conference-stage">
        <button
          onClick={() =>
            (props.onSendMessage as (text: string) => void)("Hello HCP")
          }
        >
          Send
        </button>
        <button onClick={props.onMicClick as () => void}>Mic</button>
      </div>
    );
  },
  TranscriptionPanel: (props: Record<string, unknown>) => {
    capturedTranscriptionPanelProps = props;
    return (
      <div data-testid="transcription-panel">
        <button onClick={props.onToggle as () => void}>ToggleRight</button>
      </div>
    );
  },
  AudiencePanel: (props: Record<string, unknown>) => {
    capturedAudiencePanelProps = props;
    return <div data-testid="audience-panel" />;
  },
  QuestionQueue: (props: Record<string, unknown>) => {
    capturedQuestionQueueProps = props;
    return (
      <div data-testid="question-queue">
        <button
          onClick={() =>
            (props.onRespondTo as (hcpId: string) => void)("hp-1")
          }
        >
          Respond
        </button>
      </div>
    );
  },
}));

function renderConferenceSession() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/user/conference?id=cs-1"]}>
        <ConferenceSession />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ConferenceSession", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockSearchParams = new URLSearchParams("id=cs-1");
    mockRecordingState = "idle";
    mockSpeechError = null;
    mockIsSpeaking = false;
    mockSessionRecorderIsRecording = false;
    capturedCallbacks = {};
    capturedSpeechOptions = {};
    capturedTextToSpeechOptions = {};
    capturedVoiceLiveOptions = {};
    mockAvatarSdpCallbackRef.current = null;
    mockSessionData = {
      id: "cs-1",
      status: "in_progress",
      subState: "presenting",
      presentationTopic: "Drug Efficacy",
      audienceConfig: JSON.stringify([
        {
          id: "hcp-1",
          hcpProfileId: "hp-1",
          hcpName: "Dr. Smith",
          hcpSpecialty: "Oncology",
          roleInConference: "audience",
          voiceId: "v1",
          voiceLiveEnabled: true,
          avatarEnabled: true,
          avatarCharacter: "lisa",
          avatarStyle: "casual-sitting",
          sortOrder: 0,
          status: "listening",
        },
      ]),
      keyMessagesStatus: JSON.stringify([
        { message: "Key message 1", delivered: false },
      ]),
      createdAt: new Date().toISOString(),
    };
    mockScenarioAudienceHcps = undefined;
  });

  // ── Basic rendering ──
  it("renders the conference header", () => {
    renderConferenceSession();
    expect(screen.getByTestId("conference-header")).toBeInTheDocument();
  });

  it("renders the topic guide with scenario name", () => {
    renderConferenceSession();
    expect(screen.getByTestId("topic-guide")).toBeInTheDocument();
    expect(screen.getByText("Drug Efficacy")).toBeInTheDocument();
  });

  it("renders the conference stage", () => {
    renderConferenceSession();
    expect(screen.getByTestId("conference-stage")).toBeInTheDocument();
  });

  it("defaults to text input mode without an inputMode query param", () => {
    renderConferenceSession();
    expect(capturedConferenceStageProps.inputMode).toBe("text");
  });

  it("initializes audio input mode from the inputMode query param", () => {
    mockSearchParams = new URLSearchParams("id=cs-1&inputMode=audio");
    renderConferenceSession();
    expect(capturedConferenceStageProps.inputMode).toBe("audio");
  });

  it("automatically starts listening when the session opens in audio mode", async () => {
    mockSearchParams = new URLSearchParams("id=cs-1&inputMode=audio");
    renderConferenceSession();

    await waitFor(() => {
      expect(mockStartRecording).toHaveBeenCalled();
    });
  });

  it("does not automatically start listening in text mode", () => {
    renderConferenceSession();
    expect(mockStartRecording).not.toHaveBeenCalled();
  });

  it("does not automatically start listening for completed sessions", () => {
    mockSearchParams = new URLSearchParams("id=cs-1&inputMode=audio");
    mockSessionData = {
      ...mockSessionData,
      status: "completed",
    };

    renderConferenceSession();

    expect(mockStartRecording).not.toHaveBeenCalled();
  });

  it("renders the transcription panel", () => {
    renderConferenceSession();
    expect(screen.getByTestId("transcription-panel")).toBeInTheDocument();
  });

  it("renders the audience panel", () => {
    renderConferenceSession();
    expect(screen.getByTestId("audience-panel")).toBeInTheDocument();
  });

  it("renders the question queue", () => {
    renderConferenceSession();
    expect(screen.getByTestId("question-queue")).toBeInTheDocument();
  });

  // ── End session dialog ──
  it("shows end session dialog when End button is clicked", async () => {
    const user = userEvent.setup();
    renderConferenceSession();

    const endButton = screen.getByText("End");
    await user.click(endButton);

    expect(screen.getByTestId("dialog")).toBeInTheDocument();
    const endPresentationEls = screen.getAllByText("endPresentation");
    expect(endPresentationEls.length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("endConfirm")).toBeInTheDocument();
  });

  it("closes the dialog when continuePresenting is clicked", async () => {
    const user = userEvent.setup();
    renderConferenceSession();

    await user.click(screen.getByText("End"));
    expect(screen.getByTestId("dialog")).toBeInTheDocument();

    await user.click(screen.getByText("continuePresenting"));
    expect(screen.queryByTestId("dialog")).not.toBeInTheDocument();
  });

  it("navigates on confirm end session", async () => {
    const user = userEvent.setup();
    renderConferenceSession();

    await user.click(screen.getByText("End"));
    expect(screen.getByTestId("dialog")).toBeInTheDocument();

    const endButtons = screen.getAllByText("endPresentation");
    const confirmBtn = endButtons[endButtons.length - 1];
    if (confirmBtn) {
      await user.click(confirmBtn);
    }
    expect(mockMutateAsync).toHaveBeenCalledWith("cs-1");
    expect(mockNavigate).toHaveBeenCalledWith("/user/scoring/cs-1");
  });

  it("uploads recorded audio before ending an audio-mode conference", async () => {
    mockSearchParams = new URLSearchParams("id=cs-1&inputMode=audio");
    mockSessionRecorderIsRecording = true;
    const user = userEvent.setup();
    renderConferenceSession();

    await user.click(screen.getByText("End"));
    const endButtons = screen.getAllByText("endPresentation");
    const confirmBtn = endButtons[endButtons.length - 1];
    if (confirmBtn) {
      await user.click(confirmBtn);
    }

    expect(mockStopSpeaking).toHaveBeenCalled();
    expect(mockSessionRecorderStopAndUpload).toHaveBeenCalledWith("cs-1");
    expect(mockMutateAsync).toHaveBeenCalledWith("cs-1");
    expect(mockNavigate).toHaveBeenCalledWith("/user/scoring/cs-1");
  });

  it("restores audio input mode from persisted session mode", async () => {
    mockSessionData = {
      ...mockSessionData,
      mode: "voice_realtime_model",
    };
    renderConferenceSession();

    await waitFor(() => {
      expect(capturedConferenceStageProps.inputMode).toBe("audio");
    });
  });

  it("uses the real avatar session for conference digital human HCP speech", async () => {
    mockSearchParams = new URLSearchParams("id=cs-1&inputMode=audio");
    mockSessionData = {
      ...mockSessionData,
      mode: "digital_human_realtime_model",
      audienceConfig: JSON.stringify([
        {
          id: "aud-1",
          hcp_profile_id: "hp-1",
          name: "Dr. Smith",
          specialty: "Oncology",
          role: "audience",
          voice_id: "v1",
          voice_live_enabled: true,
          avatar_enabled: true,
          avatar_character: "lisa",
          avatar_style: "casual-sitting",
          sort_order: 0,
        },
      ]),
    };

    renderConferenceSession();

    expect(mockVoiceLiveConnect).not.toHaveBeenCalled();

    await act(async () => {
      await (capturedConferenceStageProps.onAvatarConnectClick as () => Promise<void>)();
    });

    await waitFor(() => {
      expect(mockVoiceLiveConnect).toHaveBeenCalledWith(
        "hp-1",
        "",
        undefined,
        true,
      );
      expect(mockAvatarStreamConnect).toHaveBeenCalled();
      expect(capturedConferenceStageProps.digitalHumanEnabled).toBe(true);
      expect(capturedConferenceStageProps.avatarCharacter).toBe("lisa");
      expect(capturedConferenceStageProps.avatarStyle).toBe("casual-sitting");
      expect(capturedConferenceStageProps.isAvatarConnected).toBe(true);
    });

    act(() => {
      capturedCallbacks.onSpeakerText?.({
        speaker_id: "hp-1",
        speaker_name: "Dr. Smith",
        content: "欢迎参加本次会议。",
      });
    });

    await waitFor(() => {
      expect(mockSpeak).not.toHaveBeenCalled();
      expect(mockVoiceLiveSend).toHaveBeenCalledWith(
        expect.objectContaining({ type: "conversation.item.create" }),
      );
      expect(mockVoiceLiveSend).toHaveBeenCalledWith(
        expect.objectContaining({ type: "response.create" }),
      );
    });

    act(() => {
      (capturedVoiceLiveOptions.onResponseDone as () => void)?.();
    });
  });

  it("uses the connected digital human for moderator speech", async () => {
    mockSearchParams = new URLSearchParams("id=cs-1&inputMode=audio");
    mockSessionData = {
      ...mockSessionData,
      mode: "digital_human_realtime_model",
      audienceConfig: JSON.stringify([
        {
          id: "aud-1",
          hcp_profile_id: "hp-1",
          name: "Dr. Moderator",
          specialty: "Oncology",
          role: "moderator",
          voice_id: "v1",
          voice_live_enabled: true,
          avatar_enabled: true,
          avatar_character: "harry",
          avatar_style: "business",
          sort_order: 0,
        },
        {
          id: "aud-2",
          hcp_profile_id: "hp-2",
          name: "Dr. Panelist",
          specialty: "Hematology",
          role: "audience",
          voice_id: "v2",
          voice_live_enabled: true,
          avatar_enabled: true,
          avatar_character: "lori",
          avatar_style: "formal",
          sort_order: 1,
        },
      ]),
    };

    renderConferenceSession();

    await act(async () => {
      await (capturedConferenceStageProps.onAvatarConnectClick as () => Promise<void>)();
    });

    await waitFor(() => {
      expect(mockVoiceLiveConnect).toHaveBeenCalledWith("hp-1", "", undefined, true);
      expect(capturedConferenceStageProps.avatarCharacter).toBe("harry");
      expect(capturedConferenceStageProps.avatarStyle).toBe("business");
      expect(capturedConferenceStageProps.isAvatarConnected).toBe(true);
    });

    act(() => {
      capturedCallbacks.onSpeakerText?.({
        speaker_id: "hp-1",
        speaker_name: "Dr. Moderator",
        content: "欢迎参加本次会议。",
      });
    });

    await waitFor(() => {
      expect(mockSpeak).not.toHaveBeenCalled();
      expect(mockVoiceLiveSend).toHaveBeenCalledWith(
        expect.objectContaining({ type: "conversation.item.create" }),
      );
      expect(mockVoiceLiveSend).toHaveBeenCalledWith(
        expect.objectContaining({ type: "response.create" }),
      );
    });

    act(() => {
      (capturedVoiceLiveOptions.onResponseDone as () => void)?.();
    });
  });

  it("prefers the moderator when connecting the conference avatar before any speech", async () => {
    mockSearchParams = new URLSearchParams("id=cs-1&inputMode=audio");
    mockSessionData = {
      ...mockSessionData,
      mode: "digital_human_realtime_model",
      audienceConfig: JSON.stringify([
        {
          id: "aud-1",
          hcp_profile_id: "hp-panelist",
          name: "Dr. Panelist",
          specialty: "Hematology",
          role: "audience",
          voice_id: "v1",
          voice_live_enabled: true,
          avatar_enabled: true,
          avatar_character: "lori",
          avatar_style: "formal",
          sort_order: 0,
        },
        {
          id: "aud-2",
          hcp_profile_id: "hp-moderator",
          name: "Dr. Moderator",
          specialty: "Oncology",
          role: "moderator",
          voice_id: "v2",
          voice_live_enabled: true,
          avatar_enabled: true,
          avatar_character: "harry",
          avatar_style: "business",
          sort_order: 1,
        },
      ]),
    };

    renderConferenceSession();

    await waitFor(() => {
      expect(capturedConferenceStageProps.avatarHcpName).toBe("Dr. Moderator");
      expect(capturedConferenceStageProps.avatarCharacter).toBe("harry");
      expect(capturedConferenceStageProps.avatarStyle).toBe("business");
    });

    await act(async () => {
      await (capturedConferenceStageProps.onAvatarConnectClick as () => Promise<void>)();
    });

    await waitFor(() => {
      expect(mockVoiceLiveConnect).toHaveBeenCalledWith(
        "hp-moderator",
        "",
        undefined,
        true,
      );
      expect(mockVoiceLiveConnect).not.toHaveBeenCalledWith(
        "hp-panelist",
        "",
        undefined,
        true,
      );
    });
  });

  it("processes speaking HCP avatars in queued conference order", async () => {
    mockSearchParams = new URLSearchParams("id=cs-1&inputMode=audio");
    mockSessionData = {
      ...mockSessionData,
      mode: "digital_human_realtime_model",
      audienceConfig: JSON.stringify([
        {
          id: "aud-1",
          hcp_profile_id: "hp-1",
          name: "Dr. Zhang Wei",
          specialty: "Oncology",
          role: "moderator",
          voice_id: "v1",
          voice_live_enabled: true,
          avatar_enabled: true,
          avatar_character: "lisa",
          avatar_style: "casual-sitting",
          sort_order: 0,
        },
        {
          id: "aud-2",
          hcp_profile_id: "hp-2",
          name: "Dr. Chen Jun",
          specialty: "Hematology",
          role: "audience",
          voice_id: "v2",
          voice_live_enabled: true,
          avatar_enabled: true,
          avatar_character: "lori",
          avatar_style: "formal",
          sort_order: 1,
        },
      ]),
    };

    renderConferenceSession();

    await act(async () => {
      await (capturedConferenceStageProps.onAvatarConnectClick as () => Promise<void>)();
    });

    await waitFor(() => {
      expect(mockVoiceLiveConnect).toHaveBeenCalledWith("hp-1", "", undefined, true);
      expect(capturedConferenceStageProps.isAvatarConnected).toBe(true);
    });

    act(() => {
      capturedCallbacks.onSpeakerText?.({
        speaker_id: "hp-2",
        speaker_name: "Dr. Chen Jun",
        content: "请问治疗数据如何？",
      });
    });

    await waitFor(() => {
      expect(mockVoiceLiveDisconnect).toHaveBeenCalled();
      expect(mockAvatarStreamDisconnect).toHaveBeenCalled();
      expect(mockVoiceLiveConnect).toHaveBeenCalledWith("hp-2", "", undefined, true);
      expect(mockVoiceLiveSend).toHaveBeenCalledWith(
        expect.objectContaining({ type: "response.create" }),
      );
    });

    const callsBeforeFirstSpeechDone = mockVoiceLiveConnect.mock.calls.length;

    act(() => {
      capturedCallbacks.onSpeakerText?.({
        speaker_id: "hp-1",
        speaker_name: "Dr. Zhang Wei",
        content: "我来总结一下。",
      });
    });

    expect(mockVoiceLiveConnect).toHaveBeenCalledTimes(callsBeforeFirstSpeechDone);

    act(() => {
      (capturedVoiceLiveOptions.onResponseDone as () => void)?.();
    });

    await waitFor(() => {
      expect(mockVoiceLiveConnect).toHaveBeenCalledWith("hp-1", "", undefined, true);
    });

    act(() => {
      (capturedVoiceLiveOptions.onResponseDone as () => void)?.();
    });
  });

  it("shows connecting status while switching to a later HCP avatar", async () => {
    let resolveDisconnect: (() => void) | undefined;
    mockSearchParams = new URLSearchParams("id=cs-1&inputMode=audio");
    mockSessionData = {
      ...mockSessionData,
      mode: "digital_human_realtime_model",
      audienceConfig: JSON.stringify([
        {
          id: "aud-1",
          hcp_profile_id: "hp-1",
          name: "Dr. Zhang Wei",
          role: "moderator",
          voice_live_enabled: true,
          avatar_enabled: true,
        },
        {
          id: "aud-2",
          hcp_profile_id: "hp-2",
          name: "Dr. Chen Jun",
          role: "audience",
          voice_live_enabled: true,
          avatar_enabled: true,
        },
      ]),
    };

    renderConferenceSession();

    await act(async () => {
      await (capturedConferenceStageProps.onAvatarConnectClick as () => Promise<void>)();
    });

    mockVoiceLiveDisconnect.mockImplementationOnce(
      () =>
        new Promise<void>((resolve) => {
          resolveDisconnect = resolve;
        }),
    );

    act(() => {
      capturedCallbacks.onSpeakerText?.({
        speaker_id: "hp-2",
        speaker_name: "Dr. Chen Jun",
        content: "请问治疗数据如何？",
      });
    });

    await waitFor(() => {
      expect(mockVoiceLiveDisconnect).toHaveBeenCalled();
      expect(capturedConferenceStageProps.isAvatarConnected).toBe(false);
      expect(capturedConferenceStageProps.isAvatarConnecting).toBe(true);
    });

    await act(async () => {
      resolveDisconnect?.();
    });

    await waitFor(() => {
      expect(mockVoiceLiveConnect).toHaveBeenCalledWith("hp-2", "", undefined, true);
      expect(capturedConferenceStageProps.isAvatarConnected).toBe(true);
      expect(capturedConferenceStageProps.isAvatarConnecting).toBe(false);
    });

    act(() => {
      (capturedVoiceLiveOptions.onResponseDone as () => void)?.();
    });
  });

  it("queues HCP speech until the avatar stream is connected", async () => {
    let resolveAvatarConnect: (() => void) | undefined;
    mockAvatarStreamConnect.mockImplementationOnce(
      () => new Promise<void>((resolve) => {
        resolveAvatarConnect = resolve;
      }),
    );
    mockSearchParams = new URLSearchParams("id=cs-1&inputMode=audio");
    mockSessionData = {
      ...mockSessionData,
      mode: "digital_human_realtime_model",
    };

    renderConferenceSession();

    expect(mockVoiceLiveConnect).not.toHaveBeenCalled();

    void (capturedConferenceStageProps.onAvatarConnectClick as () => Promise<void>)();

    await waitFor(() => {
      expect(mockVoiceLiveConnect).toHaveBeenCalled();
      expect(mockAvatarStreamConnect).toHaveBeenCalled();
    });

    act(() => {
      capturedCallbacks.onSpeakerText?.({
        speaker_id: "hp-1",
        speaker_name: "Dr. Smith",
        content: "请开始会议。",
      });
    });

    expect(mockSpeak).not.toHaveBeenCalled();
    expect(mockVoiceLiveSend).not.toHaveBeenCalledWith(
      expect.objectContaining({ type: "response.create" }),
    );

    await act(async () => {
      resolveAvatarConnect?.();
    });

    await waitFor(() => {
      expect(mockVoiceLiveSend).toHaveBeenCalledWith(
        expect.objectContaining({ type: "response.create" }),
      );
    });

    act(() => {
      (capturedVoiceLiveOptions.onResponseDone as () => void)?.();
    });
  });

  it("hydrates avatar settings from the HCP profile for legacy conference snapshots", async () => {
    mockSearchParams = new URLSearchParams("id=cs-1&inputMode=audio");
    mockSessionData = {
      ...mockSessionData,
      mode: "digital_human_realtime_model",
      audienceConfig: JSON.stringify([
        {
          id: "aud-1",
          hcp_profile_id: "hp-1",
          name: "Dr. Smith",
          specialty: "Oncology",
          role: "audience",
          voice_id: "v1",
          sort_order: 0,
        },
      ]),
    };

    renderConferenceSession();

    expect(capturedConferenceStageProps.avatarCharacter).toBe("lori");
    expect(capturedConferenceStageProps.avatarStyle).toBe("casual");

    await waitFor(() => {
      expect(mockGetHcpProfile).toHaveBeenCalledWith("hp-1");
      expect(capturedConferenceStageProps.avatarCharacter).toBe("lisa");
      expect(capturedConferenceStageProps.avatarStyle).toBe("casual-sitting");
    });
  });

  it("falls back to scenario audience when the session snapshot has no HCP profile id", async () => {
    mockSearchParams = new URLSearchParams("id=cs-1&inputMode=audio");
    mockSessionData = {
      ...mockSessionData,
      scenarioId: "sc-1",
      mode: "digital_human_realtime_model",
      audienceConfig: "[]",
    };
    mockScenarioAudienceHcps = [
      {
        id: "aud-1",
        scenarioId: "sc-1",
        hcpProfileId: "hp-1",
        hcpName: "Dr. Smith",
        hcpSpecialty: "Oncology",
        roleInConference: "audience",
        voiceId: "v1",
        sortOrder: 0,
        status: "listening",
      },
    ];

    renderConferenceSession();

    await waitFor(() => {
      expect(capturedConferenceStageProps.avatarHcpName).toBe("Dr. Smith");
    });

    await act(async () => {
      await (capturedConferenceStageProps.onAvatarConnectClick as () => Promise<void>)();
    });

    expect(mockVoiceLiveConnect).toHaveBeenCalledWith("hp-1", "", undefined, true);
  });

  it("shows speech errors when transcription fails", async () => {
    mockSpeechError = "VOICE_NOT_ENABLED";

    renderConferenceSession();

    await waitFor(() => {
      expect(mockToastError).toHaveBeenCalledWith("VOICE_NOT_ENABLED");
    });
  });

  it("handles end session mutation failure gracefully", async () => {
    mockMutateAsync.mockRejectedValueOnce(new Error("Network error"));
    const user = userEvent.setup();
    renderConferenceSession();

    await user.click(screen.getByText("End"));
    const endButtons = screen.getAllByText("endPresentation");
    const confirmBtn = endButtons[endButtons.length - 1];
    if (confirmBtn) {
      await user.click(confirmBtn);
    }
    // Should not navigate on failure
    expect(mockNavigate).not.toHaveBeenCalled();
    expect(mockToastError).toHaveBeenCalledWith("error.endFailed");
  });

  // ── conference input routing ──
  it("requests moderator start once when session loads", async () => {
    renderConferenceSession();

    await waitFor(() => {
      expect(mockSendMessage).toHaveBeenCalledWith("start", "");
    });
  });

  it("waits for manual avatar connection before starting a digital human conference", async () => {
    mockSearchParams = new URLSearchParams("id=cs-1&inputMode=audio");
    mockSessionData = {
      ...mockSessionData,
      mode: "digital_human_realtime_model",
    };

    renderConferenceSession();

    expect(mockSendMessage).not.toHaveBeenCalledWith("start", "");
    expect(mockVoiceLiveConnect).not.toHaveBeenCalled();

    await act(async () => {
      await (capturedConferenceStageProps.onAvatarConnectClick as () => Promise<void>)();
    });

    await waitFor(() => {
      expect(mockVoiceLiveConnect).toHaveBeenCalled();
      expect(mockSendMessage).toHaveBeenCalledWith("start", "");
    });
  });

  it("releases avatar resources when manual digital human connection fails", async () => {
    mockSearchParams = new URLSearchParams("id=cs-1&inputMode=audio");
    mockSessionData = {
      ...mockSessionData,
      mode: "digital_human_realtime_model",
    };
    mockAvatarStreamConnect.mockRejectedValueOnce(
      new Error("Avatar SDP answer timeout"),
    );

    renderConferenceSession();

    await act(async () => {
      await (capturedConferenceStageProps.onAvatarConnectClick as () => Promise<void>)();
    });

    expect(mockAvatarStreamDisconnect).toHaveBeenCalled();
    expect(mockVoiceLiveDisconnect).toHaveBeenCalled();
    expect(mockToastError).toHaveBeenCalledWith(
      "数字人连接失败：Avatar SDP answer timeout",
    );
  });

  it("adds user message and calls sendMessage when presenting", async () => {
    const user = userEvent.setup();
    renderConferenceSession();
    mockSendMessage.mockClear();

    await user.click(screen.getByText("Send"));
    expect(mockSendMessage).toHaveBeenCalledWith("present", "Hello HCP");
  });

  it("routes stage input to respond when a queued HCP is waiting", async () => {
    const user = userEvent.setup();
    renderConferenceSession();
    mockSendMessage.mockClear();

    act(() => {
      capturedCallbacks.onQueueUpdate?.([
        {
          hcpProfileId: "hp-1",
          hcpName: "Dr. Smith",
          question: "What about side effects?",
          relevanceScore: 0.9,
          status: "waiting",
        },
      ]);
    });

    await user.click(screen.getByText("Send"));
    expect(mockSendMessage).toHaveBeenCalledWith("respond", "Hello HCP", "hp-1");
  });

  // ── SSE callback: onSpeakerText ──
  it("adds HCP message to state via onSpeakerText callback", () => {
    renderConferenceSession();

    act(() => {
      capturedCallbacks.onSpeakerText?.({
        speaker_id: "hcp-1",
        speaker_name: "Dr. Smith",
        content: "Thanks for your presentation",
      });
    });

    // Verify the messages were passed to ConferenceStage
    const msgs = capturedConferenceStageProps.messages as Array<{
      sender: string;
      text: string;
      speakerName: string;
    }>;
    expect(msgs).toHaveLength(1);
    expect(msgs[0]?.sender).toBe("hcp");
    expect(msgs[0]?.text).toBe("Thanks for your presentation");
    expect(msgs[0]?.speakerName).toBe("Dr. Smith");
  });

  it("updates currentSpeaker via onSpeakerText callback", () => {
    renderConferenceSession();

    act(() => {
      capturedCallbacks.onSpeakerText?.({
        speaker_id: "hcp-1",
        speaker_name: "Dr. Smith",
        content: "Hello",
      });
    });

    expect(capturedConferenceStageProps.currentSpeaker).toBe("Dr. Smith");
  });

  it("speaks full HCP text in audio mode", () => {
    mockSearchParams = new URLSearchParams("id=cs-1&inputMode=audio");
    renderConferenceSession();

    act(() => {
      capturedCallbacks.onSpeakerText?.({
        speaker_id: "hcp-1",
        speaker_name: "Dr. Smith",
        content: "第一句问题。第二句补充说明？",
      });
    });

    expect(mockSpeak).toHaveBeenCalledWith("第一句问题。第二句补充说明？", "v1");
    expect(mockSpeak).toHaveBeenCalledTimes(1);
  });

  it("uses each assigned Voice Live voice for conference speech in audio mode", async () => {
    mockSearchParams = new URLSearchParams("id=cs-1&inputMode=audio");
    mockSessionData = {
      ...mockSessionData,
      audienceConfig: JSON.stringify([
        {
          id: "aud-1",
          hcp_profile_id: "hp-1",
          name: "Dr. Liu Yang",
          specialty: "Oncology",
          role: "moderator",
          voice_id: "legacy-voice-id-1",
          sort_order: 0,
        },
        {
          id: "aud-2",
          hcp_profile_id: "hp-2",
          name: "Dr. Zhang Wei",
          specialty: "Hematology",
          role: "audience",
          voice_id: "legacy-voice-id-2",
          sort_order: 1,
        },
      ]),
    };
    renderConferenceSession();

    await waitFor(() => {
      expect(mockGetHcpProfile).toHaveBeenCalledWith("hp-1");
      expect(mockGetHcpProfile).toHaveBeenCalledWith("hp-2");
    });

    act(() => {
      capturedCallbacks.onSpeakerText?.({
        speaker_id: "hp-1",
        speaker_name: "Dr. Liu Yang",
        content: "欢迎参加本次会议。",
      });
      capturedCallbacks.onSpeakerText?.({
        speaker_id: "hp-2",
        speaker_name: "Dr. Zhang Wei",
        content: "请问临床数据如何？",
      });
    });

    expect(mockSpeak).toHaveBeenNthCalledWith(
      1,
      "欢迎参加本次会议。",
      "zh-CN-YunjianNeural",
    );
    expect(mockSpeak).toHaveBeenNthCalledWith(
      2,
      "请问临床数据如何？",
      "zh-CN-YunxiNeural",
    );
  });

  it("enables queued TTS for conference voice playback", () => {
    renderConferenceSession();

    expect(capturedTextToSpeechOptions).toMatchObject({
      queue: true,
    });
  });

  // ── SSE callback: onQueueUpdate ──
  it("updates question queue via onQueueUpdate callback", () => {
    renderConferenceSession();

    const newQueue = [
      {
        hcpProfileId: "hp-1",
        hcpName: "Dr. Smith",
        question: "What about side effects?",
        relevanceScore: 0.9,
        status: "waiting" as const,
      },
    ];

    act(() => {
      capturedCallbacks.onQueueUpdate?.(newQueue);
    });

    const questions = capturedQuestionQueueProps.questions as typeof newQueue;
    expect(questions).toHaveLength(1);
    expect(questions[0]?.question).toBe("What about side effects?");
  });

  // ── SSE callback: onTurnChange ──
  it("updates current speaker and audience status via onTurnChange callback", () => {
    renderConferenceSession();

    act(() => {
      capturedCallbacks.onTurnChange?.({
        speaker_id: "hcp-1",
        speaker_name: "Dr. Smith",
        action: "asking",
      });
    });

    expect(capturedConferenceStageProps.currentSpeaker).toBe("Dr. Smith");
    const hcps = capturedAudiencePanelProps.hcps as Array<{
      id: string;
      status: string;
    }>;
    const smith = hcps.find((h) => h.id === "hcp-1");
    expect(smith?.status).toBe("speaking");
  });

  it("sets audience to listening when turn change action is listening", () => {
    renderConferenceSession();

    // First set to speaking
    act(() => {
      capturedCallbacks.onTurnChange?.({
        speaker_id: "hcp-1",
        speaker_name: "Dr. Smith",
        action: "asking",
      });
    });

    // Then set back to listening
    act(() => {
      capturedCallbacks.onTurnChange?.({
        speaker_id: "hcp-1",
        speaker_name: "Dr. Smith",
        action: "listening",
      });
    });

    const hcps = capturedAudiencePanelProps.hcps as Array<{
      id: string;
      status: string;
    }>;
    const smith = hcps.find((h) => h.id === "hcp-1");
    expect(smith?.status).toBe("listening");
  });

  // ── SSE callback: onSubState ──
  it("updates subState via onSubState callback", () => {
    renderConferenceSession();

    act(() => {
      capturedCallbacks.onSubState?.({
        sub_state: "qa",
        message: "Entering Q&A",
      });
    });

    expect(capturedConferenceHeaderProps.subState).toBe("qa");
  });

  // ── SSE callback: onTranscription ──
  it("adds transcript lines via onTranscription callback", () => {
    renderConferenceSession();

    act(() => {
      capturedCallbacks.onTranscription?.({
        speaker: "Dr. Smith",
        text: "First transcript line",
        timestamp: "2024-01-01T10:00:00Z",
      });
    });

    const lines = capturedTranscriptionPanelProps.lines as Array<{
      speaker: string;
      text: string;
    }>;
    expect(lines).toHaveLength(1);
    expect(lines[0]?.text).toBe("First transcript line");
  });

  it("appends multiple transcript lines", () => {
    renderConferenceSession();

    act(() => {
      capturedCallbacks.onTranscription?.({
        speaker: "MR",
        text: "Line 1",
        timestamp: "2024-01-01T10:00:00Z",
      });
    });

    act(() => {
      capturedCallbacks.onTranscription?.({
        speaker: "Dr. Smith",
        text: "Line 2",
        timestamp: "2024-01-01T10:01:00Z",
      });
    });

    const lines = capturedTranscriptionPanelProps.lines as Array<{
      speaker: string;
      text: string;
    }>;
    expect(lines).toHaveLength(2);
    expect(lines[0]?.speaker).toBe("MR");
    expect(lines[1]?.speaker).toBe("Dr. Smith");
  });

  // ── SSE callback: onKeyMessages ──
  it("updates key topics via onKeyMessages callback", () => {
    renderConferenceSession();

    const newTopics = [
      { message: "Efficacy data", delivered: true },
      { message: "Safety profile", delivered: false },
    ];

    act(() => {
      capturedCallbacks.onKeyMessages?.(newTopics);
    });

    const topics = capturedTopicGuideProps.topics as typeof newTopics;
    expect(topics).toHaveLength(2);
    expect(topics[0]?.delivered).toBe(true);
  });

  // ── SSE callback: onDone ──
  it("handles onDone callback without crashing", () => {
    renderConferenceSession();

    // onDone is a no-op but shouldn't throw
    act(() => {
      capturedCallbacks.onDone?.();
    });

    expect(screen.getByTestId("conference-stage")).toBeInTheDocument();
  });

  // ── SSE callback: onError ──
  it("handles onError callback", () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    renderConferenceSession();

    act(() => {
      capturedCallbacks.onError?.("Something went wrong");
    });

    expect(consoleSpy).toHaveBeenCalledWith(
      "Conference SSE error:",
      "Something went wrong",
    );
    consoleSpy.mockRestore();
  });

  // ── Respond to question ──
  it("responds to a question from the queue", async () => {
    const user = userEvent.setup();
    renderConferenceSession();
    mockSendMessage.mockClear();

    // First set up the question queue via SSE
    act(() => {
      capturedCallbacks.onQueueUpdate?.([
        {
          hcpProfileId: "hp-1",
          hcpName: "Dr. Smith",
          question: "What about side effects?",
          relevanceScore: 0.9,
          status: "waiting",
        },
      ]);
    });

    // Click respond
    await user.click(screen.getByText("Respond"));

    expect(mockSendMessage).toHaveBeenCalledWith("respond", "", "hp-1");
  });

  it("does not respond if no matching waiting question in queue", async () => {
    const user = userEvent.setup();
    renderConferenceSession();
    mockSendMessage.mockClear();

    // Queue with already active question
    act(() => {
      capturedCallbacks.onQueueUpdate?.([
        {
          hcpProfileId: "hp-1",
          hcpName: "Dr. Smith",
          question: "Side effects?",
          relevanceScore: 0.9,
          status: "active",
        },
      ]);
    });

    await user.click(screen.getByText("Respond"));
    expect(mockSendMessage).not.toHaveBeenCalled();
  });

  // ── Toggle panels ──
  it("toggles left panel (topic guide)", async () => {
    const user = userEvent.setup();
    renderConferenceSession();

    // Initially not collapsed
    expect(capturedTopicGuideProps.isCollapsed).toBe(false);

    await user.click(screen.getByText("ToggleLeft"));
    expect(capturedTopicGuideProps.isCollapsed).toBe(true);

    await user.click(screen.getByText("ToggleLeft"));
    expect(capturedTopicGuideProps.isCollapsed).toBe(false);
  });

  it("toggles right panel (transcription)", async () => {
    const user = userEvent.setup();
    renderConferenceSession();

    expect(capturedTranscriptionPanelProps.isCollapsed).toBe(false);

    await user.click(screen.getByText("ToggleRight"));
    expect(capturedTranscriptionPanelProps.isCollapsed).toBe(true);
  });

  // ── Input mode toggle ──
  it("toggles audio mode via conference stage input controls", () => {
    renderConferenceSession();

    // Initially text mode
    expect(capturedConferenceStageProps.inputMode).toBe("text");

    act(() => {
      (
        capturedConferenceStageProps.onInputModeChange as (
          mode: "text" | "audio",
        ) => void
      )("audio");
    });
    expect(capturedConferenceStageProps.inputMode).toBe("audio");
  });

  it("automatically starts listening after switching to audio mode", async () => {
    renderConferenceSession();
    mockStartRecording.mockClear();

    act(() => {
      (
        capturedConferenceStageProps.onInputModeChange as (
          mode: "text" | "audio",
        ) => void
      )("audio");
    });

    await waitFor(() => {
      expect(mockStartRecording).toHaveBeenCalled();
    });
  });

  it("uses longer silence detection settings for conference speech", () => {
    renderConferenceSession();

    expect(capturedSpeechOptions).toMatchObject({
      autoStopOnSilence: true,
      silenceMs: 2000,
      minSpeechMs: 700,
      noSpeechTimeoutMs: 20000,
    });
  });

  it("stops listening when switching back to text mode", async () => {
    mockSearchParams = new URLSearchParams("id=cs-1&inputMode=audio");
    mockRecordingState = "recording";
    renderConferenceSession();
    mockStopRecording.mockClear();

    act(() => {
      (
        capturedConferenceStageProps.onInputModeChange as (
          mode: "text" | "audio",
        ) => void
      )("text");
    });

    await waitFor(() => {
      expect(mockStopRecording).toHaveBeenCalled();
    });
  });

  // ── Session initialization: audience config ──
  it("initializes audience from session audienceConfig", () => {
    renderConferenceSession();

    const hcps = capturedAudiencePanelProps.hcps as Array<{
      id: string;
      hcpName: string;
      status: string;
    }>;
    expect(hcps).toHaveLength(1);
    expect(hcps[0]?.hcpName).toBe("Dr. Smith");
    expect(hcps[0]?.status).toBe("listening");
  });

  it("handles invalid audienceConfig JSON gracefully", () => {
    mockSessionData = {
      ...mockSessionData,
      audienceConfig: "not-valid-json",
    };
    // Should not throw
    renderConferenceSession();
    expect(screen.getByTestId("audience-panel")).toBeInTheDocument();
  });

  // ── Session initialization: subState ──
  it("initializes subState from session", () => {
    renderConferenceSession();
    expect(capturedConferenceHeaderProps.subState).toBe("presenting");
  });

  // ── Session initialization: key messages ──
  it("initializes key topics from session keyMessagesStatus", () => {
    renderConferenceSession();

    const topics = capturedTopicGuideProps.topics as Array<{
      message: string;
      delivered: boolean;
    }>;
    expect(topics).toHaveLength(1);
    expect(topics[0]?.message).toBe("Key message 1");
    expect(topics[0]?.delivered).toBe(false);
  });

  it("handles invalid keyMessagesStatus JSON gracefully", () => {
    mockSessionData = {
      ...mockSessionData,
      keyMessagesStatus: "{bad json",
    };
    renderConferenceSession();
    expect(screen.getByTestId("topic-guide")).toBeInTheDocument();
  });

  // ── Session with no audienceConfig / no keyMessagesStatus ──
  it("handles null audienceConfig", () => {
    mockSessionData = {
      ...mockSessionData,
      audienceConfig: null,
    };
    renderConferenceSession();
    const hcps = capturedAudiencePanelProps.hcps as Array<unknown>;
    expect(hcps).toHaveLength(0);
  });

  it("handles null keyMessagesStatus", () => {
    mockSessionData = {
      ...mockSessionData,
      keyMessagesStatus: null,
    };
    renderConferenceSession();
    const topics = capturedTopicGuideProps.topics as Array<unknown>;
    expect(topics).toHaveLength(0);
  });

  // ── Session with no session data (undefined) ──
  it("renders with undefined session data", () => {
    mockSessionData = undefined;
    renderConferenceSession();
    expect(screen.getByTestId("conference-stage")).toBeInTheDocument();
    // scenarioName falls back to ""
    expect(capturedTopicGuideProps.scenarioName).toBe("");
  });

  // ── Session timer ──
  it("starts session timer and updates sessionTime", () => {
    vi.useFakeTimers();
    renderConferenceSession();

    // Initially or very shortly after: "00:00"
    expect(capturedConferenceHeaderProps.sessionTime).toBeDefined();

    // Advance 65 seconds
    act(() => {
      vi.advanceTimersByTime(65000);
    });

    expect(capturedConferenceHeaderProps.sessionTime).toBe("01:05");
    vi.useRealTimers();
  });

  it("uses session createdAt for timer start time", () => {
    vi.useFakeTimers();
    const fiveMinutesAgo = new Date(Date.now() - 5 * 60 * 1000).toISOString();
    mockSessionData = {
      ...mockSessionData,
      createdAt: fiveMinutesAgo,
    };
    renderConferenceSession();

    // After 1 tick (1 second) should show ~5:01
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    const time = capturedConferenceHeaderProps.sessionTime as string;
    expect(time).toMatch(/^05:0/);
    vi.useRealTimers();
  });

  // ── Audience status default ──
  it("sets default status to listening when audience hcp has no status", () => {
    mockSessionData = {
      ...mockSessionData,
      audienceConfig: JSON.stringify([
        {
          id: "hcp-2",
          hcpProfileId: "hp-2",
          hcpName: "Dr. Lee",
          hcpSpecialty: "Cardiology",
          roleInConference: "audience",
          voiceId: "v2",
          sortOrder: 1,
          // status omitted
        },
      ]),
    };
    renderConferenceSession();

    const hcps = capturedAudiencePanelProps.hcps as Array<{
      status: string;
    }>;
    expect(hcps[0]?.status).toBe("listening");
  });

  // ── Speaker color mapping ──
  it("assigns speaker colors correctly via speakerMap", () => {
    renderConferenceSession();

    const speakerMap = capturedTranscriptionPanelProps.speakerMap as Map<
      string,
      number
    >;
    // MR is always index 0
    expect(speakerMap.get("MR")).toBe(0);
    // HCP audience is mapped
    expect(speakerMap.get("hcp-1")).toBeDefined();
    expect(speakerMap.get("Dr. Smith")).toBeDefined();
  });

  // ── Completed session ──
  it("passes disabled=true when session is completed", () => {
    mockSessionData = {
      ...mockSessionData,
      status: "completed",
    };
    renderConferenceSession();
    expect(capturedConferenceStageProps.disabled).toBe(true);
  });

  it("passes disabled=false when session is in_progress", () => {
    renderConferenceSession();
    expect(capturedConferenceStageProps.disabled).toBe(false);
  });

  // ── Mic click handling ──
  it("delegates mic click to conference stage", async () => {
    const user = userEvent.setup();
    renderConferenceSession();

    await user.click(screen.getByText("Mic"));
    // When idle, it calls startRecording
    expect(mockStartRecording).toHaveBeenCalled();
  });

  // ── Turn change matching by hcpProfileId ──
  it("matches turn change by hcpProfileId", () => {
    renderConferenceSession();

    act(() => {
      capturedCallbacks.onTurnChange?.({
        speaker_id: "hp-1", // matches hcpProfileId, not id
        speaker_name: "Dr. Smith",
        action: "asking",
      });
    });

    const hcps = capturedAudiencePanelProps.hcps as Array<{
      id: string;
      status: string;
    }>;
    const smith = hcps.find((h) => h.id === "hcp-1");
    expect(smith?.status).toBe("speaking");
  });

  // ── onText callback (no-op) ──
  it("handles onText callback without crashing", () => {
    renderConferenceSession();
    act(() => {
      capturedCallbacks.onText?.("some streamed chunk");
    });
    expect(screen.getByTestId("conference-stage")).toBeInTheDocument();
  });
});
