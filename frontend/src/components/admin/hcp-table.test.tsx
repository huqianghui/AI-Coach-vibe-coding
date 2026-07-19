import { describe, it, expect, vi, beforeEach } from "vitest";
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

vi.mock("@/components/admin/voice-live-model-select", () => ({
  VOICE_LIVE_MODEL_OPTIONS: [
    { value: "gpt-4o", i18nKey: "modelGpt4o", tier: "pro" },
    { value: "gpt-realtime", i18nKey: "modelGptRealtime", tier: "pro" },
  ],
}));

vi.mock("@/components/shared/empty-state", () => ({
  EmptyState: ({ title, body }: { title: string; body: string }) => (
    <div data-testid="empty-state">
      <span>{title}</span>
      <span>{body}</span>
    </div>
  ),
}));

// Import after mocks
import { HcpTable } from "./hcp-table";

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
    updated_at: "2026-01-01T00:00:00Z",
    agent_id: "agent-1",
    agent_version: "v1",
    agent_sync_status: "synced",
    agent_sync_error: "",
    voice_live_instance_id: null,
    voice_live_instance: null,
    agent_instructions_override: "",
    knowledge_config_count: 0,
    ...overrides,
  };
}

describe("HcpTable", () => {
  const defaultHandlers = {
    onEdit: vi.fn(),
    onDelete: vi.fn(),
    onRetrySync: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  // ── Column Headers ──────────────────────────────────────────
  it("renders all column headers", () => {
    render(
      <HcpTable profiles={[]} isLoading={false} {...defaultHandlers} />,
    );
    expect(screen.getByText("hcp.name")).toBeInTheDocument();
    expect(screen.getByText("hcp.specialty")).toBeInTheDocument();
    expect(screen.getByText("hcp.personalityType")).toBeInTheDocument();
    expect(screen.getByText("hcp.communicationStyleCol")).toBeInTheDocument();
    expect(screen.getByText("hcp.agentStatus")).toBeInTheDocument();
    expect(screen.getByText("hcp.knowledgeBaseCol")).toBeInTheDocument();
    expect(screen.getByText("hcp.voiceAvatarCol")).toBeInTheDocument();
    expect(screen.getByText("hcp.actions")).toBeInTheDocument();
  });

  // ── Loading State ──────────────────────────────────────────
  it("renders skeleton rows when loading", () => {
    const { container } = render(
      <HcpTable profiles={[]} isLoading={true} {...defaultHandlers} />,
    );
    // 5 skeleton rows are rendered
    const rows = container.querySelectorAll("tbody tr");
    expect(rows.length).toBe(5);
  });

  // ── Empty State ────────────────────────────────────────────
  it("renders empty state when no profiles and not loading", () => {
    render(
      <HcpTable profiles={[]} isLoading={false} {...defaultHandlers} />,
    );
    expect(screen.getByTestId("empty-state")).toBeInTheDocument();
    expect(screen.getByText("hcp.emptyTitle")).toBeInTheDocument();
    expect(screen.getByText("hcp.emptyBody")).toBeInTheDocument();
  });

  // ── Profile Rows ──────────────────────────────────────────
  it("renders profile data in rows", () => {
    const profiles = [
      makeProfile({
        id: "hcp-1",
        name: "Dr. Alpha",
        specialty: "Hematology",
        personality_type: "skeptical",
        communication_style: 30,
      }),
    ];
    render(
      <HcpTable profiles={profiles} isLoading={false} {...defaultHandlers} />,
    );
    expect(screen.getByText("Dr. Alpha")).toBeInTheDocument();
    expect(screen.getByText("Hematology")).toBeInTheDocument();
    expect(screen.getByText("skeptical")).toBeInTheDocument();
    // Communication style shows value + (Direct/Indirect)
    expect(screen.getByText("(Direct)")).toBeInTheDocument();
  });

  it("shows Indirect for communication_style >= 50", () => {
    const profiles = [
      makeProfile({ communication_style: 70 }),
    ];
    render(
      <HcpTable profiles={profiles} isLoading={false} {...defaultHandlers} />,
    );
    expect(screen.getByText("(Indirect)")).toBeInTheDocument();
  });

  it("shows avatar initials from name", () => {
    const profiles = [
      makeProfile({ name: "John Smith" }),
    ];
    render(
      <HcpTable profiles={profiles} isLoading={false} {...defaultHandlers} />,
    );
    expect(screen.getByText("JS")).toBeInTheDocument();
  });

  // ── Agent Status Badge ────────────────────────────────────
  it("shows agent synced badge", () => {
    const profiles = [
      makeProfile({ agent_sync_status: "synced" }),
    ];
    render(
      <HcpTable profiles={profiles} isLoading={false} {...defaultHandlers} />,
    );
    expect(screen.getByText("hcp.agentSynced")).toBeInTheDocument();
  });

  it("shows agent failed badge", () => {
    const profiles = [
      makeProfile({ agent_sync_status: "failed" }),
    ];
    render(
      <HcpTable profiles={profiles} isLoading={false} {...defaultHandlers} />,
    );
    expect(screen.getByText("hcp.agentFailed")).toBeInTheDocument();
  });

  it("shows agent pending badge", () => {
    const profiles = [
      makeProfile({ agent_sync_status: "pending" }),
    ];
    render(
      <HcpTable profiles={profiles} isLoading={false} {...defaultHandlers} />,
    );
    expect(screen.getByText("hcp.agentPending")).toBeInTheDocument();
  });

  it("shows agent none badge", () => {
    const profiles = [
      makeProfile({ agent_sync_status: "none", agent_id: "" }),
    ];
    render(
      <HcpTable profiles={profiles} isLoading={false} {...defaultHandlers} />,
    );
    expect(screen.getByText("hcp.agentNone")).toBeInTheDocument();
  });

  // ── Voice/Avatar Column ───────────────────────────────────
  it("shows voice badges when a VL instance is assigned with voice_name set", () => {
    const profiles = [
      makeProfile({
        voice_live_instance_id: "vl-1",
        voice_live_instance: {
          id: "vl-1",
          name: "Test Instance",
          voice_live_model: "gpt-4o",
          enabled: false,
          voice_name: "en-US-AvaNeural",
          avatar_character: "lisa",
          avatar_style: "casual",
        },
      }),
    ];
    render(
      <HcpTable profiles={profiles} isLoading={false} {...defaultHandlers} />,
    );
    expect(screen.getByText("Ava")).toBeInTheDocument(); // getVoiceLabel
    expect(screen.getByText(/lisa-casual/)).toBeInTheDocument();
  });

  it("shows 'not configured' when no VL instance is assigned", () => {
    const profiles = [
      makeProfile({ voice_live_instance_id: null, voice_live_instance: null }),
    ];
    render(
      <HcpTable profiles={profiles} isLoading={false} {...defaultHandlers} />,
    );
    expect(screen.getByText("hcp.notConfigured")).toBeInTheDocument();
  });

  it("shows VL model badge when the assigned instance is enabled", () => {
    const profiles = [
      makeProfile({
        voice_live_instance_id: "vl-1",
        voice_live_instance: {
          id: "vl-1",
          name: "Test Instance",
          voice_live_model: "gpt-4o",
          enabled: true,
          voice_name: "en-US-AvaNeural",
          avatar_character: "lisa",
          avatar_style: "casual",
        },
      }),
    ];
    render(
      <HcpTable profiles={profiles} isLoading={false} {...defaultHandlers} />,
    );
    // Model label from VOICE_LIVE_MODEL_OPTIONS
    expect(screen.getByText("hcp.modelGpt4o")).toBeInTheDocument();
  });

  // ── Action Buttons ────────────────────────────────────────
  it("calls onEdit when edit button is clicked", async () => {
    const user = userEvent.setup();
    const onEdit = vi.fn();
    const profile = makeProfile();
    render(
      <HcpTable
        profiles={[profile]}
        isLoading={false}
        onEdit={onEdit}
        onDelete={vi.fn()}
        onRetrySync={vi.fn()}
      />,
    );
    // Find the edit button via tooltip text
    const editButtons = screen.getAllByRole("button");
    const editButton = editButtons.find((btn) =>
      btn.querySelector("svg"), // The Edit icon button
    );
    expect(editButton).toBeTruthy();
    // Use the first icon button (Edit)
    await user.click(editButtons[2]!); // After header sort buttons (0,1), first action = 2
    expect(onEdit).toHaveBeenCalledWith(profile);
  });

  it("calls onDelete when delete button is clicked", async () => {
    const user = userEvent.setup();
    const onDelete = vi.fn();
    const profile = makeProfile({ agent_sync_status: "synced" });
    render(
      <HcpTable
        profiles={[profile]}
        isLoading={false}
        onEdit={vi.fn()}
        onDelete={onDelete}
        onRetrySync={vi.fn()}
      />,
    );
    // For synced status, there's edit + delete (no retry)
    const allButtons = screen.getAllByRole("button");
    // Last action button should be delete
    const deleteBtn = allButtons[allButtons.length - 1]!;
    await user.click(deleteBtn);
    expect(onDelete).toHaveBeenCalledWith(profile.id);
  });

  it("shows retry sync button for failed status", () => {
    const profiles = [
      makeProfile({ agent_sync_status: "failed" }),
    ];
    render(
      <HcpTable profiles={profiles} isLoading={false} {...defaultHandlers} />,
    );
    // There should be 3 action buttons: edit, retry, delete
    const allButtons = screen.getAllByRole("button");
    // header sort buttons(2) + action buttons(3) = 5
    expect(allButtons.length).toBe(5);
  });

  it("shows retry sync button for none status without agent_id", () => {
    const profiles = [
      makeProfile({ agent_sync_status: "none", agent_id: "" }),
    ];
    render(
      <HcpTable profiles={profiles} isLoading={false} {...defaultHandlers} />,
    );
    // edit + retry + delete = 3 action buttons
    const allButtons = screen.getAllByRole("button");
    expect(allButtons.length).toBe(5); // 2 sort + 3 actions
  });

  it("does not show retry sync button for synced profiles with agent_id", () => {
    const profiles = [
      makeProfile({ agent_sync_status: "synced", agent_id: "agent-1" }),
    ];
    render(
      <HcpTable profiles={profiles} isLoading={false} {...defaultHandlers} />,
    );
    // edit + delete = 2 action buttons
    const allButtons = screen.getAllByRole("button");
    expect(allButtons.length).toBe(4); // 2 sort + 2 actions
  });

  // ── Sorting ───────────────────────────────────────────────
  it("sorts by name ascending by default", () => {
    const profiles = [
      makeProfile({ id: "2", name: "Dr. Zeta" }),
      makeProfile({ id: "1", name: "Dr. Alpha" }),
    ];
    const { container } = render(
      <HcpTable profiles={profiles} isLoading={false} {...defaultHandlers} />,
    );
    const cells = container.querySelectorAll("tbody td:first-child");
    expect(cells[0]?.textContent).toContain("Dr. Alpha");
    expect(cells[1]?.textContent).toContain("Dr. Zeta");
  });

  it("toggles sort direction when clicking name header", async () => {
    const user = userEvent.setup();
    const profiles = [
      makeProfile({ id: "1", name: "Dr. Alpha" }),
      makeProfile({ id: "2", name: "Dr. Zeta" }),
    ];
    const { container } = render(
      <HcpTable profiles={profiles} isLoading={false} {...defaultHandlers} />,
    );

    // Click name header to toggle to desc
    await user.click(screen.getByText("hcp.name"));

    const cells = container.querySelectorAll("tbody td:first-child");
    expect(cells[0]?.textContent).toContain("Dr. Zeta");
    expect(cells[1]?.textContent).toContain("Dr. Alpha");
  });

  it("sorts by specialty when specialty header is clicked", async () => {
    const user = userEvent.setup();
    const profiles = [
      makeProfile({ id: "1", name: "Dr. Z", specialty: "Hematology" }),
      makeProfile({ id: "2", name: "Dr. A", specialty: "Cardiology" }),
    ];
    const { container } = render(
      <HcpTable profiles={profiles} isLoading={false} {...defaultHandlers} />,
    );

    await user.click(screen.getByText("hcp.specialty"));

    const cells = container.querySelectorAll("tbody td:nth-child(2)");
    expect(cells[0]?.textContent).toContain("Cardiology");
    expect(cells[1]?.textContent).toContain("Hematology");
  });

  // ── Pagination ────────────────────────────────────────────
  it("does not show pagination for 10 or fewer profiles", () => {
    const profiles = Array.from({ length: 5 }, (_, i) =>
      makeProfile({ id: `hcp-${i}`, name: `Dr. ${i}` }),
    );
    render(
      <HcpTable profiles={profiles} isLoading={false} {...defaultHandlers} />,
    );
    expect(screen.queryByText("Previous")).not.toBeInTheDocument();
    expect(screen.queryByText("Next")).not.toBeInTheDocument();
  });

  it("shows pagination for more than 10 profiles", () => {
    const profiles = Array.from({ length: 15 }, (_, i) =>
      makeProfile({ id: `hcp-${i}`, name: `Dr. ${String(i).padStart(2, "0")}` }),
    );
    render(
      <HcpTable profiles={profiles} isLoading={false} {...defaultHandlers} />,
    );
    expect(screen.getByText("Page 1 of 2")).toBeInTheDocument();
    expect(screen.getByText("Previous")).toBeInTheDocument();
    expect(screen.getByText("Next")).toBeInTheDocument();
  });

  it("navigates to next page when Next button is clicked", async () => {
    const user = userEvent.setup();
    const profiles = Array.from({ length: 15 }, (_, i) =>
      makeProfile({ id: `hcp-${i}`, name: `Dr. ${String(i).padStart(2, "0")}` }),
    );
    render(
      <HcpTable profiles={profiles} isLoading={false} {...defaultHandlers} />,
    );

    await user.click(screen.getByText("Next"));
    expect(screen.getByText("Page 2 of 2")).toBeInTheDocument();
  });

  it("navigates back when Previous button is clicked", async () => {
    const user = userEvent.setup();
    const profiles = Array.from({ length: 15 }, (_, i) =>
      makeProfile({ id: `hcp-${i}`, name: `Dr. ${String(i).padStart(2, "0")}` }),
    );
    render(
      <HcpTable profiles={profiles} isLoading={false} {...defaultHandlers} />,
    );

    await user.click(screen.getByText("Next"));
    expect(screen.getByText("Page 2 of 2")).toBeInTheDocument();

    await user.click(screen.getByText("Previous"));
    expect(screen.getByText("Page 1 of 2")).toBeInTheDocument();
  });

  it("disables Previous on first page", () => {
    const profiles = Array.from({ length: 15 }, (_, i) =>
      makeProfile({ id: `hcp-${i}`, name: `Dr. ${i}` }),
    );
    render(
      <HcpTable profiles={profiles} isLoading={false} {...defaultHandlers} />,
    );
    expect(screen.getByText("Previous")).toBeDisabled();
  });

  it("disables Next on last page", async () => {
    const user = userEvent.setup();
    const profiles = Array.from({ length: 15 }, (_, i) =>
      makeProfile({ id: `hcp-${i}`, name: `Dr. ${i}` }),
    );
    render(
      <HcpTable profiles={profiles} isLoading={false} {...defaultHandlers} />,
    );

    await user.click(screen.getByText("Next"));
    expect(screen.getByText("Next")).toBeDisabled();
  });

  // ── Double-click to edit ──────────────────────────────────
  it("calls onEdit on row double-click", async () => {
    const user = userEvent.setup();
    const onEdit = vi.fn();
    const profile = makeProfile();
    const { container } = render(
      <HcpTable
        profiles={[profile]}
        isLoading={false}
        onEdit={onEdit}
        onDelete={vi.fn()}
        onRetrySync={vi.fn()}
      />,
    );

    const row = container.querySelector("tbody tr")!;
    await user.dblClick(row);
    expect(onEdit).toHaveBeenCalledWith(profile);
  });
});
