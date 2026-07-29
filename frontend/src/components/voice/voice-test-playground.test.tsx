import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { VoiceTestPlaygroundProps, SessionState } from "./voice-test-playground";

// --- Mocks ---

vi.mock("react-i18next", () => ({
  useTranslation: (ns?: string | string[]) => ({
    t: (key: string) =>
      key.includes(":")
        ? key
        : `${Array.isArray(ns) ? ns[0] : (ns ?? "")}${ns ? ":" : ""}${key}`,
    i18n: { changeLanguage: vi.fn(), language: "en" },
  }),
}));

vi.mock("sonner", () => ({
  toast: { error: vi.fn() },
}));

vi.mock("@/components/ui/button", () => ({
  Button: ({
    children,
    onClick,
    disabled,
    ...rest
  }: {
    children: React.ReactNode;
    onClick?: () => void;
    disabled?: boolean;
    size?: string;
    className?: string;
  }) => (
    <button onClick={onClick} disabled={disabled} data-size={rest.size}>
      {children}
    </button>
  ),
}));

vi.mock("@/components/voice/avatar-view", () => ({
  AvatarView: (props: Record<string, unknown>) => (
    <div
      data-testid="avatar-view"
      data-hcp-name={String(props["hcpName"] ?? "")}
      data-is-connecting={String(props["isConnecting"])}
      data-is-avatar-connected={String(props["isAvatarConnected"] ?? false)}
      data-is-session-active={String(props["isSessionActive"] ?? "")}
      data-avatar-character={String(props["avatarCharacter"] ?? "")}
    />
  ),
}));

vi.mock("@/components/voice/voice-controls", () => ({
  VoiceControls: (props: Record<string, unknown>) => (
    <div data-testid="voice-controls">
      <button data-testid="end-session" onClick={props["onEndSession"] as () => void}>
        End
      </button>
      <button
        data-testid="toggle-keyboard"
        onClick={props["onToggleKeyboard"] as () => void}
      >
        Keyboard
      </button>
    </div>
  ),
}));

const mockConnect = vi.fn().mockResolvedValue({ avatarEnabled: false, mode: "model", iceServers: [] });
const mockDisconnect = vi.fn().mockResolvedValue(undefined);
const mockSend = vi.fn();
const mockSendAudio = vi.fn();
const mockToggleMute = vi.fn();
const mockSendTextMessage = vi.fn();
const mockAvatarSdpCallbackRef = { current: null as unknown };

vi.mock("@/hooks/use-voice-live", () => ({
  useVoiceLive: () => ({
    connect: mockConnect,
    disconnect: mockDisconnect,
    toggleMute: mockToggleMute,
    sendTextMessage: mockSendTextMessage,
    sendAudio: mockSendAudio,
    send: mockSend,
    isMuted: false,
    connectionState: "disconnected",
    audioState: "idle",
    avatarSdpCallbackRef: mockAvatarSdpCallbackRef,
  }),
}));

const mockAvatarConnect = vi.fn().mockResolvedValue(undefined);
const mockAvatarDisconnect = vi.fn();
vi.mock("@/hooks/use-avatar-stream", () => ({
  useAvatarStream: () => ({
    connect: mockAvatarConnect,
    disconnect: mockAvatarDisconnect,
    handleServerSdp: vi.fn(),
    isConnected: false,
  }),
}));

const mockInitialize = vi.fn().mockResolvedValue({});
const mockStartRecording = vi.fn();
const mockCleanup = vi.fn();
vi.mock("@/hooks/use-audio-handler", () => ({
  useAudioHandler: () => ({
    initialize: mockInitialize,
    startRecording: mockStartRecording,
    stopRecording: vi.fn(),
    cleanup: mockCleanup,
    isRecording: false,
    analyserRef: { current: null },
  }),
}));

vi.mock("@/hooks/use-volume-level", () => ({
  useVolumeLevel: () => 0,
}));

const mockPlayAudio = vi.fn();
const mockStopAudio = vi.fn();
vi.mock("@/hooks/use-audio-player", () => ({
  useAudioPlayer: () => ({
    playAudio: mockPlayAudio,
    stopAudio: mockStopAudio,
    analyserRef: { current: null },
  }),
}));

// Dynamic import after mocks are set up
import { VoiceTestPlayground } from "./voice-test-playground";
import { toast } from "sonner";

const defaultProps: VoiceTestPlaygroundProps = {
  avatarEnabled: false,
  hcpName: "Dr. Smith",
};

describe("VoiceTestPlayground", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockConnect.mockResolvedValue({ avatarEnabled: false, mode: "model", iceServers: [] });
    mockInitialize.mockResolvedValue({});
    mockDisconnect.mockResolvedValue(undefined);
  });

  // --- Idle state rendering ---

  it("renders with default idle state showing start button", () => {
    render(<VoiceTestPlayground {...defaultProps} />);
    const startBtn = screen.getByRole("button", { name: /playgroundStart/i });
    expect(startBtn).toBeInTheDocument();
  });

  it("renders the title from props", () => {
    render(<VoiceTestPlayground {...defaultProps} title="Custom Title" />);
    expect(screen.getByText("Custom Title")).toBeInTheDocument();
  });

  it("renders the default title from i18n key when no title prop", () => {
    render(<VoiceTestPlayground {...defaultProps} />);
    expect(screen.getByText("admin:hcp.playgroundTitle")).toBeInTheDocument();
  });

  it("renders headerExtra content", () => {
    render(
      <VoiceTestPlayground
        {...defaultProps}
        headerExtra={<span data-testid="extra">Extra</span>}
      />,
    );
    expect(screen.getByTestId("extra")).toBeInTheDocument();
  });

  it("shows disabled message when disabled with disabledMessage", () => {
    render(
      <VoiceTestPlayground
        {...defaultProps}
        disabled={true}
        disabledMessage="Not ready"
      />,
    );
    expect(screen.getByText("Not ready")).toBeInTheDocument();
  });

  it("does not show disabled message when not disabled", () => {
    render(
      <VoiceTestPlayground {...defaultProps} disabledMessage="Not ready" />,
    );
    expect(screen.queryByText("Not ready")).not.toBeInTheDocument();
  });

  it("start button is disabled when disabled prop is true", () => {
    render(<VoiceTestPlayground {...defaultProps} disabled={true} />);
    const startBtn = screen.getByRole("button", { name: /playgroundStart/i });
    expect(startBtn).toBeDisabled();
  });

  it("renders AvatarView with correct props", () => {
    render(<VoiceTestPlayground {...defaultProps} hcpName="Dr. Wang" />);
    const avatarView = screen.getByTestId("avatar-view");
    expect(avatarView).toHaveAttribute("data-hcp-name", "Dr. Wang");
    expect(avatarView).toHaveAttribute("data-is-connecting", "false");
  });

  it("applies className prop to root element", () => {
    const { container } = render(
      <VoiceTestPlayground {...defaultProps} className="my-custom-class" />,
    );
    expect(container.firstElementChild?.classList.contains("my-custom-class")).toBe(
      true,
    );
  });

  // --- Start test ---

  it("clicking start initializes audio and connects voice live", async () => {
    render(<VoiceTestPlayground {...defaultProps} />);
    const startBtn = screen.getByRole("button", { name: /playgroundStart/i });

    await act(async () => {
      fireEvent.click(startBtn);
    });

    expect(mockInitialize).toHaveBeenCalled();
    expect(mockConnect).toHaveBeenCalled();
  });

  it("passes hcpProfileId and vlInstanceId to voiceLive.connect", async () => {
    render(
      <VoiceTestPlayground
        {...defaultProps}
        hcpProfileId="hcp-1"
        vlInstanceId="vl-1"
        systemPrompt="Hello"
      />,
    );

    await act(async () => {
      fireEvent.click(
        screen.getByRole("button", { name: /playgroundStart/i }),
      );
    });

    expect(mockConnect).toHaveBeenCalledWith({
      enableAvatar: undefined,
      hcpProfileId: "hcp-1",
      sessionId: undefined,
      systemPrompt: "Hello",
      vlInstanceId: "vl-1",
    });
  });

  it("shows voice controls after successful connection", async () => {
    render(<VoiceTestPlayground {...defaultProps} />);

    await act(async () => {
      fireEvent.click(
        screen.getByRole("button", { name: /playgroundStart/i }),
      );
    });

    expect(screen.getByTestId("voice-controls")).toBeInTheDocument();
  });

  it("starts recording after connection", async () => {
    render(<VoiceTestPlayground {...defaultProps} />);

    await act(async () => {
      fireEvent.click(
        screen.getByRole("button", { name: /playgroundStart/i }),
      );
    });

    expect(mockStartRecording).toHaveBeenCalled();
  });

  it("calls onSessionStateChange callback on state changes", async () => {
    const onStateChange = vi.fn();
    render(
      <VoiceTestPlayground
        {...defaultProps}
        onSessionStateChange={onStateChange}
      />,
    );

    await act(async () => {
      fireEvent.click(
        screen.getByRole("button", { name: /playgroundStart/i }),
      );
    });

    // The useEffect fires with the final committed state; since mocks resolve
    // synchronously, "connecting" may be batched away. We verify that the
    // callback was called and the final state is "connected".
    const calls = (onStateChange.mock.calls as [SessionState][]).map(
      (c) => c[0],
    );
    expect(calls).toContain("connected");
  });

  it("handles mic permission denied error gracefully", async () => {
    const domError = new DOMException("Not allowed", "NotAllowedError");
    mockInitialize.mockRejectedValueOnce(domError);

    render(<VoiceTestPlayground {...defaultProps} />);

    await act(async () => {
      fireEvent.click(
        screen.getByRole("button", { name: /playgroundStart/i }),
      );
    });

    expect(toast.error).toHaveBeenCalledWith("admin:hcp.permissionDeniedMic");
  });

  it("shows generic error toast when connection fails", async () => {
    mockConnect.mockRejectedValueOnce(new Error("Connection failed"));

    render(<VoiceTestPlayground {...defaultProps} />);

    await act(async () => {
      fireEvent.click(
        screen.getByRole("button", { name: /playgroundStart/i }),
      );
    });

    expect(toast.error).toHaveBeenCalledWith(
      expect.stringContaining("Connection failed"),
    );
  });

  // --- Avatar mode ---

  it("connects avatar when result.avatarEnabled is true", async () => {
    mockConnect.mockResolvedValueOnce({
      avatarEnabled: true,
      mode: "model",
      iceServers: [{ urls: "stun:test" }],
    });

    render(<VoiceTestPlayground {...defaultProps} avatarEnabled={true} />);

    await act(async () => {
      fireEvent.click(
        screen.getByRole("button", { name: /playgroundStart/i }),
      );
    });

    expect(mockAvatarConnect).toHaveBeenCalledWith(
      [{ urls: "stun:test" }],
      expect.any(Function),
    );
  });

  // --- Stop test ---

  it("clicking end session disconnects and cleans up", async () => {
    render(<VoiceTestPlayground {...defaultProps} />);

    // Start session first
    await act(async () => {
      fireEvent.click(
        screen.getByRole("button", { name: /playgroundStart/i }),
      );
    });

    // Now end session
    await act(async () => {
      fireEvent.click(screen.getByTestId("end-session"));
    });

    expect(mockDisconnect).toHaveBeenCalled();
    expect(mockAvatarDisconnect).toHaveBeenCalled();
    expect(mockCleanup).toHaveBeenCalled();
    expect(mockStopAudio).toHaveBeenCalled();
  });

  // --- Keyboard input ---

  it("toggles keyboard panel visibility", async () => {
    const user = userEvent.setup();
    render(<VoiceTestPlayground {...defaultProps} />);

    // Start session
    await act(async () => {
      fireEvent.click(
        screen.getByRole("button", { name: /playgroundStart/i }),
      );
    });

    // Initially no text input visible
    expect(screen.queryByPlaceholderText("Type a message...")).not.toBeInTheDocument();

    // Toggle keyboard
    await user.click(screen.getByTestId("toggle-keyboard"));
    expect(screen.getByPlaceholderText("Type a message...")).toBeInTheDocument();

    // Toggle off
    await user.click(screen.getByTestId("toggle-keyboard"));
    expect(screen.queryByPlaceholderText("Type a message...")).not.toBeInTheDocument();
  });

  it("sends text message on Enter key and clears input", async () => {
    const user = userEvent.setup();
    render(<VoiceTestPlayground {...defaultProps} />);

    // Start session
    await act(async () => {
      fireEvent.click(
        screen.getByRole("button", { name: /playgroundStart/i }),
      );
    });

    // Open keyboard
    await user.click(screen.getByTestId("toggle-keyboard"));

    const input = screen.getByPlaceholderText("Type a message...");
    await user.type(input, "Hello doctor{Enter}");

    expect(mockSendTextMessage).toHaveBeenCalledWith("Hello doctor");
  });

  it("sends text message on Send button click", async () => {
    const user = userEvent.setup();
    render(<VoiceTestPlayground {...defaultProps} />);

    // Start session
    await act(async () => {
      fireEvent.click(
        screen.getByRole("button", { name: /playgroundStart/i }),
      );
    });

    // Open keyboard
    await user.click(screen.getByTestId("toggle-keyboard"));

    const input = screen.getByPlaceholderText("Type a message...");
    await user.type(input, "Test message");

    // Click Send
    const sendBtn = screen.getByRole("button", { name: /send/i });
    await user.click(sendBtn);

    expect(mockSendTextMessage).toHaveBeenCalledWith("Test message");
  });

  it("does not send empty text on Enter", async () => {
    const user = userEvent.setup();
    render(<VoiceTestPlayground {...defaultProps} />);

    // Start session
    await act(async () => {
      fireEvent.click(
        screen.getByRole("button", { name: /playgroundStart/i }),
      );
    });

    // Open keyboard
    await user.click(screen.getByTestId("toggle-keyboard"));

    const input = screen.getByPlaceholderText("Type a message...");
    await user.type(input, "{Enter}");

    expect(mockSendTextMessage).not.toHaveBeenCalled();
  });

  // --- Avatar vs session state separation ---

  it("passes avatarStream.isConnected as isAvatarConnected (not sessionState)", () => {
    render(<VoiceTestPlayground {...defaultProps} />);
    const avatarView = screen.getByTestId("avatar-view");
    // In idle state, avatarStream.isConnected is false (from mock)
    expect(avatarView).toHaveAttribute("data-is-avatar-connected", "false");
  });

  it("passes sessionState as isSessionActive after connection", async () => {
    render(<VoiceTestPlayground {...defaultProps} />);

    await act(async () => {
      fireEvent.click(
        screen.getByRole("button", { name: /playgroundStart/i }),
      );
    });

    const avatarView = screen.getByTestId("avatar-view");
    // Session is connected, so isSessionActive should be "true"
    expect(avatarView).toHaveAttribute("data-is-session-active", "true");
    // But avatar stream mock returns isConnected=false, so isAvatarConnected stays false
    expect(avatarView).toHaveAttribute("data-is-avatar-connected", "false");
  });

  it("clears avatarCharacter when avatarEnabled is false", () => {
    render(
      <VoiceTestPlayground
        {...defaultProps}
        avatarEnabled={false}
        avatarCharacter="lisa"
      />,
    );
    const avatarView = screen.getByTestId("avatar-view");
    expect(avatarView).toHaveAttribute("data-avatar-character", "");
  });

  it("passes avatarCharacter when avatarEnabled is true", () => {
    render(
      <VoiceTestPlayground
        {...defaultProps}
        avatarEnabled={true}
        avatarCharacter="lisa"
      />,
    );
    const avatarView = screen.getByTestId("avatar-view");
    expect(avatarView).toHaveAttribute("data-avatar-character", "lisa");
  });

  // --- Mode badge ---

  it("does not show mode badge before connection", () => {
    render(<VoiceTestPlayground {...defaultProps} />);
    expect(screen.queryByTestId("mode-badge")).not.toBeInTheDocument();
  });

  it("shows Model Mode badge after connecting in model mode", async () => {
    mockConnect.mockResolvedValueOnce({ avatarEnabled: false, mode: "model", iceServers: [] });
    render(<VoiceTestPlayground {...defaultProps} />);

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /playgroundStart/i }));
    });

    const badge = screen.getByTestId("mode-badge");
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveTextContent("admin:hcp.modelMode");
  });

  it("shows Agent Mode badge after connecting in agent mode", async () => {
    mockConnect.mockResolvedValueOnce({ avatarEnabled: false, mode: "agent", iceServers: [] });
    render(<VoiceTestPlayground {...defaultProps} />);

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /playgroundStart/i }));
    });

    const badge = screen.getByTestId("mode-badge");
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveTextContent("admin:hcp.agentMode");
  });

  it("clears mode badge after stopping session", async () => {
    render(<VoiceTestPlayground {...defaultProps} />);

    // Start session
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /playgroundStart/i }));
    });

    expect(screen.getByTestId("mode-badge")).toBeInTheDocument();

    // Stop session
    await act(async () => {
      fireEvent.click(screen.getByTestId("end-session"));
    });

    expect(screen.queryByTestId("mode-badge")).not.toBeInTheDocument();
  });

  // --- Cleanup on unmount ---

  it("cleans up on unmount", async () => {
    const { unmount } = render(<VoiceTestPlayground {...defaultProps} />);

    // unmount triggers async stopVoiceSession() via useEffect cleanup;
    // wrap in act and flush microtasks so the async chain completes.
    await act(async () => {
      unmount();
    });

    // Disconnect is called in cleanup effect (via stopVoiceSession → lifecycle hook)
    expect(mockDisconnect).toHaveBeenCalled();
    expect(mockAvatarDisconnect).toHaveBeenCalled();
    expect(mockCleanup).toHaveBeenCalled();
    expect(mockStopAudio).toHaveBeenCalled();
  });
});
