import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { HcpProfile } from "@/types/hcp";

// ---- Mocks ----

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en-US" },
  }),
}));

const mockGetAgentPortalUrl = vi.fn();
vi.mock("@/api/hcp-profiles", () => ({
  getAgentPortalUrl: (...args: unknown[]) => mockGetAgentPortalUrl(...args),
}));

// Import after mocks
import { AgentStatusSection } from "./agent-status-section";

function makeProfile(overrides: Partial<HcpProfile> = {}): HcpProfile {
  return {
    id: "hcp-1",
    name: "Dr. Test",
    specialty: "Oncology",
    hospital: "Test Hospital",
    title: "Doctor",
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
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-02T00:00:00Z",
    agent_id: "agent-abc",
    agent_version: "v1",
    agent_sync_status: "synced",
    agent_sync_error: "",
    voice_live_instance_id: null,
    voice_live_enabled: false,
    voice_live_model: "gpt-4o",
    voice_name: "",
    voice_type: "",
    voice_temperature: 0.9,
    voice_custom: false,
    avatar_character: "",
    avatar_style: "",
    avatar_customized: false,
    turn_detection_type: "server_vad",
    noise_suppression: false,
    echo_cancellation: false,
    eou_detection: false,
    recognition_language: "auto",
    agent_instructions_override: "",
    knowledge_config_count: 0,
    ...overrides,
  };
}

describe("AgentStatusSection", () => {
  const defaultProps = {
    isNew: false,
    onRetrySync: vi.fn(),
    retrySyncPending: false,
  };

  it("renders AI Foundry Agent title", () => {
    render(
      <AgentStatusSection
        profile={makeProfile()}
        {...defaultProps}
      />,
    );
    expect(screen.getByText("AI Foundry Agent")).toBeInTheDocument();
  });

  it("shows 'Agent Synced' status when synced", () => {
    render(
      <AgentStatusSection
        profile={makeProfile({ agent_sync_status: "synced" })}
        {...defaultProps}
      />,
    );
    expect(screen.getByText("Agent Synced")).toBeInTheDocument();
  });

  it("shows 'Sync Pending' status when pending", () => {
    render(
      <AgentStatusSection
        profile={makeProfile({ agent_sync_status: "pending" })}
        {...defaultProps}
      />,
    );
    expect(screen.getByText("Sync Pending")).toBeInTheDocument();
  });

  it("shows 'Sync Failed' status when failed", () => {
    render(
      <AgentStatusSection
        profile={makeProfile({ agent_sync_status: "failed" })}
        {...defaultProps}
      />,
    );
    expect(screen.getByText("Sync Failed")).toBeInTheDocument();
  });

  it("shows 'No Agent' status when none", () => {
    render(
      <AgentStatusSection
        profile={makeProfile({ agent_sync_status: "none", agent_id: "" })}
        {...defaultProps}
      />,
    );
    expect(screen.getByText("No Agent")).toBeInTheDocument();
  });

  it("shows agent ID when profile has one", () => {
    render(
      <AgentStatusSection
        profile={makeProfile({ agent_id: "agent-xyz-123" })}
        {...defaultProps}
      />,
    );
    expect(screen.getByText("agent-xyz-123")).toBeInTheDocument();
    expect(screen.getByText("Agent ID")).toBeInTheDocument();
  });

  it("does not show agent ID when profile has no agent_id", () => {
    render(
      <AgentStatusSection
        profile={makeProfile({ agent_id: "" })}
        {...defaultProps}
      />,
    );
    expect(screen.queryByText("Agent ID")).not.toBeInTheDocument();
  });

  it("shows error message when status is failed with sync error", () => {
    render(
      <AgentStatusSection
        profile={makeProfile({
          agent_sync_status: "failed",
          agent_sync_error: "Connection timeout",
        })}
        {...defaultProps}
      />,
    );
    expect(screen.getByText("Connection timeout")).toBeInTheDocument();
    expect(screen.getByText("Error")).toBeInTheDocument();
  });

  it("does not show error message when status is not failed", () => {
    render(
      <AgentStatusSection
        profile={makeProfile({
          agent_sync_status: "synced",
          agent_sync_error: "old error",
        })}
        {...defaultProps}
      />,
    );
    expect(screen.queryByText("old error")).not.toBeInTheDocument();
  });

  it("shows retry button when status is failed and not new", () => {
    const onRetrySync = vi.fn();
    render(
      <AgentStatusSection
        profile={makeProfile({ agent_sync_status: "failed" })}
        isNew={false}
        onRetrySync={onRetrySync}
        retrySyncPending={false}
      />,
    );
    const retryButton = screen.getByText("admin:hcp.retrySync");
    expect(retryButton).toBeInTheDocument();
  });

  it("shows retry button when status is none and not new", () => {
    render(
      <AgentStatusSection
        profile={makeProfile({ agent_sync_status: "none", agent_id: "" })}
        isNew={false}
        onRetrySync={vi.fn()}
        retrySyncPending={false}
      />,
    );
    expect(screen.getByText("admin:hcp.retrySync")).toBeInTheDocument();
  });

  it("shows force re-sync button when status is synced", () => {
    render(
      <AgentStatusSection
        profile={makeProfile({ agent_sync_status: "synced" })}
        {...defaultProps}
      />,
    );
    expect(screen.queryByText("admin:hcp.retrySync")).not.toBeInTheDocument();
    expect(screen.getByText("Force re-sync")).toBeInTheDocument();
  });

  it("does not show retry button when status is pending", () => {
    render(
      <AgentStatusSection
        profile={makeProfile({ agent_sync_status: "pending" })}
        {...defaultProps}
      />,
    );
    expect(screen.queryByText("admin:hcp.retrySync")).not.toBeInTheDocument();
    expect(screen.queryByText("Force re-sync")).not.toBeInTheDocument();
  });

  it("does not show retry button when isNew is true", () => {
    render(
      <AgentStatusSection
        profile={makeProfile({ agent_sync_status: "failed" })}
        isNew={true}
        onRetrySync={vi.fn()}
        retrySyncPending={false}
      />,
    );
    expect(screen.queryByText("admin:hcp.retrySync")).not.toBeInTheDocument();
  });

  it("shows 'Syncing...' when retrySyncPending is true", () => {
    render(
      <AgentStatusSection
        profile={makeProfile({ agent_sync_status: "failed" })}
        isNew={false}
        onRetrySync={vi.fn()}
        retrySyncPending={true}
      />,
    );
    expect(screen.getByText("Syncing...")).toBeInTheDocument();
  });

  it("calls onRetrySync when retry button is clicked", async () => {
    const user = userEvent.setup();
    const onRetrySync = vi.fn();
    render(
      <AgentStatusSection
        profile={makeProfile({ agent_sync_status: "failed" })}
        isNew={false}
        onRetrySync={onRetrySync}
        retrySyncPending={false}
      />,
    );
    await user.click(screen.getByText("admin:hcp.retrySync"));
    expect(onRetrySync).toHaveBeenCalledOnce();
  });

  it("shows 'View in Azure Portal' button when agent_id exists", () => {
    render(
      <AgentStatusSection
        profile={makeProfile({ agent_id: "agent-123" })}
        {...defaultProps}
      />,
    );
    expect(screen.getByText("View in Azure Portal")).toBeInTheDocument();
  });

  it("does not show 'View in Azure Portal' when agent_id is empty", () => {
    render(
      <AgentStatusSection
        profile={makeProfile({ agent_id: "" })}
        {...defaultProps}
      />,
    );
    expect(screen.queryByText("View in Azure Portal")).not.toBeInTheDocument();
  });

  it("shows info message for new profiles", () => {
    render(
      <AgentStatusSection
        profile={undefined}
        isNew={true}
        onRetrySync={vi.fn()}
        retrySyncPending={false}
      />,
    );
    expect(
      screen.getByText(/AI Foundry Agent will be automatically created/),
    ).toBeInTheDocument();
  });

  it("shows metadata (Created / Last Updated) for existing profiles", () => {
    render(
      <AgentStatusSection
        profile={makeProfile()}
        isNew={false}
        onRetrySync={vi.fn()}
        retrySyncPending={false}
      />,
    );
    expect(screen.getByText("Created")).toBeInTheDocument();
    expect(screen.getByText("Last Updated")).toBeInTheDocument();
  });

  it("does not show metadata when isNew is true", () => {
    render(
      <AgentStatusSection
        profile={undefined}
        isNew={true}
        onRetrySync={vi.fn()}
        retrySyncPending={false}
      />,
    );
    expect(screen.queryByText("Created")).not.toBeInTheDocument();
    expect(screen.queryByText("Last Updated")).not.toBeInTheDocument();
  });

  it("shows 'No Agent' when profile is undefined", () => {
    render(
      <AgentStatusSection
        profile={undefined}
        {...defaultProps}
      />,
    );
    expect(screen.getByText("No Agent")).toBeInTheDocument();
  });
});
