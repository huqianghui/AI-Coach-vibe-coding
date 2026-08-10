import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ConferenceStage } from "./conference-stage";
import type { AudienceHcp } from "@/types/conference";

vi.mock("@/components/shared", () => ({
  ChatBubble: ({
    text,
    speakerName,
  }: {
    text: string;
    speakerName?: string;
  }) => (
    <div data-testid="chat-bubble">
      {speakerName && <span>{speakerName}</span>}
      <span>{text}</span>
    </div>
  ),
  ChatInput: ({ disabled }: { disabled?: boolean }) => (
    <div data-testid="chat-input" data-disabled={disabled} />
  ),
}));

vi.mock("@/components/voice/avatar-view", () => ({
  AvatarView: ({
    hcpName,
    avatarCharacter,
    videoFit,
  }: {
    hcpName: string;
    avatarCharacter?: string;
    videoFit?: string;
  }) => (
    <div
      data-testid="avatar-view"
      data-avatar-character={avatarCharacter}
      data-video-fit={videoFit}
    >
      {hcpName}
    </div>
  ),
}));

describe("ConferenceStage", () => {
  const makeAudienceHcp = (index: number): AudienceHcp => ({
    id: `audience-${index}`,
    scenarioId: "scenario-1",
    hcpProfileId: `hcp-${index}`,
    hcpName: `Dr. HCP ${index}`,
    hcpSpecialty: "Oncology",
    roleInConference: "audience",
    voiceId: "",
    sortOrder: index,
    status: "listening",
  });

  const defaultProps = {
    sessionId: "sess-1",
    onSendMessage: vi.fn(),
    isStreaming: false,
    streamedText: "",
    currentSpeaker: "Dr. Chen",
    avatarEnabled: true,
    featureAvatarEnabled: true,
  };

  it("renders avatar with speaker initials when avatarEnabled", () => {
    render(<ConferenceStage {...defaultProps} />);
    expect(screen.getByText("DC")).toBeInTheDocument();
  });

  it("renders current speaker name below avatar when avatarEnabled", () => {
    render(<ConferenceStage {...defaultProps} />);
    expect(screen.getByText("Dr. Chen")).toBeInTheDocument();
  });

  it("renders fallback text when avatar is disabled", () => {
    render(<ConferenceStage {...defaultProps} avatarEnabled={false} />);
    expect(screen.getByText("Dr. Chen")).toBeInTheDocument();
  });

  it("shows 'Conference Stage' when avatar disabled and no current speaker", () => {
    render(
      <ConferenceStage {...defaultProps} avatarEnabled={false} currentSpeaker="" />,
    );
    expect(screen.getByText("Conference Stage")).toBeInTheDocument();
  });

  it("renders chat messages", () => {
    const messages = [
      {
        id: "m1",
        sender: "hcp" as const,
        text: "Hello MR",
        timestamp: new Date(),
        speakerName: "Dr. Chen",
      },
      {
        id: "m2",
        sender: "mr" as const,
        text: "Good morning",
        timestamp: new Date(),
      },
    ];
    render(<ConferenceStage {...defaultProps} messages={messages} />);
    const bubbles = screen.getAllByTestId("chat-bubble");
    expect(bubbles).toHaveLength(2);
    expect(screen.getByText("Hello MR")).toBeInTheDocument();
    expect(screen.getByText("Good morning")).toBeInTheDocument();
  });

  it("shows streamed text when streaming", () => {
    render(
      <ConferenceStage
        {...defaultProps}
        isStreaming={true}
        streamedText="Partial response..."
      />,
    );
    expect(screen.getByText("Partial response...")).toBeInTheDocument();
  });

  it("shows typing indicator when streaming without text", () => {
    const { container } = render(
      <ConferenceStage {...defaultProps} isStreaming={true} streamedText="" />,
    );
    const bounceDots = container.querySelectorAll(".animate-bounce");
    expect(bounceDots.length).toBe(3);
  });

  it("does not show typing indicator when not streaming", () => {
    const { container } = render(
      <ConferenceStage {...defaultProps} isStreaming={false} streamedText="" />,
    );
    const bounceDots = container.querySelectorAll(".animate-bounce");
    expect(bounceDots.length).toBe(0);
  });

  it("renders ChatInput component", () => {
    render(<ConferenceStage {...defaultProps} />);
    expect(screen.getByTestId("chat-input")).toBeInTheDocument();
  });

  it("passes disabled prop to ChatInput", () => {
    render(<ConferenceStage {...defaultProps} disabled={true} />);
    expect(screen.getByTestId("chat-input")).toHaveAttribute(
      "data-disabled",
      "true",
    );
  });

  it("uses 'AI' as fallback initials when currentSpeaker is empty", () => {
    render(<ConferenceStage {...defaultProps} currentSpeaker="" avatarEnabled={true} />);
    expect(screen.getByText("AI")).toBeInTheDocument();
  });

  it("renders the real avatar view when digital human is enabled", () => {
    render(
      <ConferenceStage
        {...defaultProps}
        digitalHumanEnabled={true}
        avatarVideoRef={{ current: null }}
        isAvatarConnected={true}
        avatarCharacter="lisa"
        avatarStyle="casual-sitting"
      />,
    );

    expect(screen.getByTestId("avatar-view")).toHaveAttribute(
      "data-avatar-character",
      "lisa",
    );
    expect(screen.getByText("Dr. Chen")).toBeInTheDocument();
    expect(screen.getByTestId("avatar-view")).toHaveAttribute(
      "data-video-fit",
      "contain",
    );
  });

  it("renders all conference HCPs in the digital human stage", () => {
    const audienceHcps = [1, 2, 3, 4].map(makeAudienceHcp);

    render(
      <ConferenceStage
        {...defaultProps}
        digitalHumanEnabled={true}
        avatarVideoRef={{ current: null }}
        isAvatarConnected={true}
        audienceHcps={audienceHcps}
        currentSpeaker="Dr. HCP 2"
        currentSpeakerId="hcp-2"
      />,
    );

    expect(screen.getByTestId("audience-stage-hcp-1")).toBeInTheDocument();
    expect(screen.getByTestId("audience-stage-hcp-2")).toBeInTheDocument();
    expect(screen.getByTestId("audience-stage-hcp-3")).toBeInTheDocument();
    expect(screen.getByTestId("audience-stage-hcp-4")).toBeInTheDocument();
    expect(screen.getAllByTestId("avatar-view")).toHaveLength(4);
  });

  it("uses one row for three HCPs and two columns for four HCPs", () => {
    const { rerender, container } = render(
      <ConferenceStage
        {...defaultProps}
        digitalHumanEnabled={true}
        avatarVideoRef={{ current: null }}
        audienceHcps={[1, 2, 3].map(makeAudienceHcp)}
      />,
    );

    expect(container.querySelector(".grid-cols-3")).toBeInTheDocument();

    rerender(
      <ConferenceStage
        {...defaultProps}
        digitalHumanEnabled={true}
        avatarVideoRef={{ current: null }}
        audienceHcps={[1, 2, 3, 4].map(makeAudienceHcp)}
      />,
    );

    expect(container.querySelector(".grid-cols-2")).toBeInTheDocument();
  });

  it("uses dedicated gallery layouts for one and two HCPs", () => {
    const { rerender, container } = render(
      <ConferenceStage
        {...defaultProps}
        digitalHumanEnabled={true}
        avatarVideoRef={{ current: null }}
        audienceHcps={[makeAudienceHcp(1)]}
      />,
    );

    expect(container.querySelector(".grid-cols-1")).toBeInTheDocument();

    rerender(
      <ConferenceStage
        {...defaultProps}
        digitalHumanEnabled={true}
        avatarVideoRef={{ current: null }}
        audienceHcps={[makeAudienceHcp(1), makeAudienceHcp(2)]}
      />,
    );

    expect(container.querySelector(".grid-cols-2")).toBeInTheDocument();
  });

  it("shows every HCP as a digital human while only the current speaker is active", () => {
    const audienceHcps = [1, 2, 3].map(makeAudienceHcp);

    render(
      <ConferenceStage
        {...defaultProps}
        digitalHumanEnabled={true}
        avatarVideoRef={{ current: null }}
        isAvatarConnected={true}
        audienceHcps={audienceHcps}
        currentSpeaker="Dr. HCP 2"
        currentSpeakerId="hcp-2"
      />,
    );

    expect(screen.getAllByTestId("avatar-view")).toHaveLength(3);
    expect(screen.getByTestId("audience-stage-hcp-2")).toHaveAttribute(
      "data-active",
      "true",
    );
    expect(screen.getByTestId("audience-stage-hcp-1")).toHaveAttribute(
      "data-active",
      "false",
    );
    expect(screen.getByTestId("audience-stage-hcp-3")).toHaveAttribute(
      "data-active",
      "false",
    );
  });

  it("uses the selected avatar target as the active tile before any speaker starts", () => {
    const audienceHcps = [1, 2, 3].map(makeAudienceHcp);

    render(
      <ConferenceStage
        {...defaultProps}
        digitalHumanEnabled={true}
        avatarVideoRef={{ current: null }}
        audienceHcps={audienceHcps}
        currentSpeaker=""
        currentSpeakerId=""
        activeAvatarHcpId="hcp-2"
      />,
    );

    expect(screen.getByTestId("audience-stage-hcp-2")).toHaveAttribute(
      "data-active",
      "true",
    );
    expect(screen.getByTestId("audience-stage-hcp-1")).toHaveAttribute(
      "data-active",
      "false",
    );
    expect(screen.getByTestId("audience-stage-hcp-3")).toHaveAttribute(
      "data-active",
      "false",
    );
  });

  it("falls back to a usable avatar character when an HCP snapshot has blank avatar fields", () => {
    const audienceHcps = [
      {
        ...makeAudienceHcp(1),
        avatarCharacter: "",
        avatarStyle: "",
      },
    ];

    render(
      <ConferenceStage
        {...defaultProps}
        digitalHumanEnabled={true}
        avatarVideoRef={{ current: null }}
        audienceHcps={audienceHcps}
        currentSpeaker="Dr. HCP 1"
        currentSpeakerId="hcp-1"
      />,
    );

    expect(screen.getByTestId("avatar-view")).toHaveAttribute(
      "data-avatar-character",
      "lori",
    );
  });

  it("shows a manual connect button before the digital human is connected", async () => {
    const onConnect = vi.fn();
    render(
      <ConferenceStage
        {...defaultProps}
        digitalHumanEnabled={true}
        avatarVideoRef={{ current: null }}
        isAvatarConnected={false}
        onAvatarConnectClick={onConnect}
      />,
    );

    await userEvent.setup().click(screen.getByRole("button", { name: "连接数字人" }));

    expect(onConnect).toHaveBeenCalledTimes(1);
  });

  it("shows a disabled connecting status while the digital human is connecting", () => {
    render(
      <ConferenceStage
        {...defaultProps}
        digitalHumanEnabled={true}
        avatarVideoRef={{ current: null }}
        isAvatarConnected={false}
        isAvatarConnecting={true}
        onAvatarConnectClick={vi.fn()}
      />,
    );

    expect(screen.getByRole("button", { name: "数字人连接中" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: "连接数字人" })).not.toBeInTheDocument();
  });
});

