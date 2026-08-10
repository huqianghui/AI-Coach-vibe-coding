import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { VoiceSessionHeader } from "./voice-session-header";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { changeLanguage: vi.fn(), language: "en" },
  }),
}));

vi.mock("@/components/coach/session-timer", () => ({
  SessionTimer: ({ startedAt }: { startedAt: string | null }) => (
    <div data-testid="session-timer">{startedAt ?? "no-time"}</div>
  ),
}));

vi.mock("./connection-status", () => ({
  ConnectionStatus: ({ state }: { state: string }) => (
    <div data-testid="connection-status">{state}</div>
  ),
}));

vi.mock("./mode-status-indicator", () => ({
  ModeStatusIndicator: ({
    currentMode,
    connectionState,
  }: {
    currentMode: string;
    initialMode: string;
    connectionState: string;
  }) => (
    <div data-testid="mode-status-indicator">
      {currentMode}-{connectionState}
    </div>
  ),
}));

describe("VoiceSessionHeader", () => {
  const defaultProps = {
    scenarioTitle: "Drug Efficacy Discussion",
    currentMode: "voice_pipeline" as const,
    initialMode: "voice_pipeline" as const,
    connectionState: "connected" as const,
    onEndSession: vi.fn(),
    startedAt: "2026-03-27T08:00:00Z",
  };

  it("renders scenario title text", () => {
    render(<VoiceSessionHeader {...defaultProps} />);
    expect(screen.getByText("Drug Efficacy Discussion")).toBeInTheDocument();
  });

  it("renders ModeStatusIndicator with correct mode", () => {
    render(
      <VoiceSessionHeader
        {...defaultProps}
        currentMode="digital_human_pipeline"
      />,
    );
    expect(screen.getByTestId("mode-status-indicator")).toHaveTextContent(
      "digital_human_pipeline-connected",
    );
  });

  it("renders ConnectionStatus component with correct state", () => {
    render(
      <VoiceSessionHeader {...defaultProps} connectionState="connecting" />,
    );
    const status = screen.getByTestId("connection-status");
    expect(status).toHaveTextContent("connecting");
  });

  it("renders End Session button with destructive styling", () => {
    render(<VoiceSessionHeader {...defaultProps} />);
    const endBtn = screen.getByTestId("end-session-btn");
    expect(endBtn).toBeInTheDocument();
    expect(endBtn).toHaveTextContent("endSession");
  });

  it("calls onEndSession when End Session button is clicked", async () => {
    const onEndSession = vi.fn();
    render(
      <VoiceSessionHeader {...defaultProps} onEndSession={onEndSession} />,
    );
    const endBtn = screen.getByTestId("end-session-btn");
    await userEvent.click(endBtn);
    expect(onEndSession).toHaveBeenCalledTimes(1);
  });

  it("renders view toggle button when onToggleView is provided", () => {
    const onToggleView = vi.fn();
    render(
      <VoiceSessionHeader {...defaultProps} onToggleView={onToggleView} />,
    );
    const toggleBtn = screen.getByLabelText("fullScreen");
    expect(toggleBtn).toBeInTheDocument();
  });

  it("does not render view toggle button when onToggleView is not provided", () => {
    render(<VoiceSessionHeader {...defaultProps} />);
    expect(screen.queryByLabelText("fullScreen")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("embeddedView")).not.toBeInTheDocument();
  });

  it("renders SessionTimer component", () => {
    render(<VoiceSessionHeader {...defaultProps} />);
    expect(screen.getByTestId("session-timer")).toBeInTheDocument();
  });

  it("applies full-screen styling when isFullScreen is true", () => {
    const { container } = render(
      <VoiceSessionHeader
        {...defaultProps}
        isFullScreen={true}
        onToggleView={vi.fn()}
      />,
    );
    const header = container.querySelector("header");
    expect(header?.className).toContain("bg-black/50");
  });

  it("switches to another available mode while disabling the current mode", async () => {
    const onModeChange = vi.fn();
    render(
      <VoiceSessionHeader
        {...defaultProps}
        currentMode="voice_realtime_model"
        initialMode="voice_realtime_model"
        availableModes={["text", "voice_realtime_model", "digital_human_realtime_model"]}
        onModeChange={onModeChange}
      />,
    );

    await userEvent.click(screen.getByTestId("mode-switch-trigger"));

    expect(
      screen.getByRole("menuitemradio", { name: "mode.voice_realtime_model" }),
    ).toHaveAttribute("aria-disabled", "true");
    await userEvent.click(
      screen.getByRole("menuitemradio", { name: "mode.digital_human_realtime_model" }),
    );
    expect(onModeChange).toHaveBeenCalledWith("digital_human_realtime_model");
  });

  it("keeps the static indicator when only one mode is available", () => {
    render(
      <VoiceSessionHeader
        {...defaultProps}
        availableModes={["voice_realtime_model"]}
        onModeChange={vi.fn()}
      />,
    );

    expect(screen.queryByTestId("mode-switch-trigger")).not.toBeInTheDocument();
    expect(screen.getByTestId("mode-status-indicator")).toBeInTheDocument();
  });

  it("hides connection status in text mode", () => {
    render(
      <VoiceSessionHeader
        {...defaultProps}
        currentMode="text"
        initialMode="text"
      />,
    );

    expect(screen.queryByTestId("connection-status")).not.toBeInTheDocument();
  });
});
