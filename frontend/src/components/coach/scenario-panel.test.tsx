import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ScenarioPanel } from "./scenario-panel";
import type { Scenario } from "@/types/scenario";
import type { KeyMessageStatus } from "@/types/session";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { changeLanguage: vi.fn(), language: "en" },
  }),
}));

vi.mock("./key-messages", () => ({
  KeyMessages: ({ messages }: { messages: KeyMessageStatus[] }) => (
    <div data-testid="key-messages">{messages.length} messages</div>
  ),
}));

const mockScenario: Scenario = {
  id: "sc-1",
  name: "Oncology Visit",
  description: "Practice session",
  product: "DrugX",
  therapeutic_area: "Oncology",
  mode: "f2f",
  difficulty: "medium",
  status: "active",
  hcp_profile_id: "hcp-1",
  tags: ["product:DrugX", "area:Oncology"],
  hcp_profile: {
    id: "hcp-1",
    name: "Dr. Jane Doe",
    specialty: "Oncology",
    hospital: "General Hospital",
    title: "Senior Physician",
    avatar_url: "",
    personality_type: "analytical",
    emotional_state: 50,
    communication_style: 70,
    expertise_areas: [],
    prescribing_habits: "",
    concerns: "",
    objections: [],
    probe_topics: [],
    difficulty: "medium",
    is_active: true,
    created_by: "admin",
    created_at: "2024-01-01",
    updated_at: "2024-01-01",
    agent_id: "",
    agent_version: "",
    agent_sync_status: "none",
    agent_sync_error: "",
    agent_instructions_override: "",
    knowledge_config_count: 0,
    voice_live_instance_id: null,
  },
  key_messages: ["Efficacy", "Safety"],
  rubric_id: "rubric-1",
  pass_threshold: 70,
  created_by: "admin",
  created_at: "2024-01-01",
  updated_at: "2024-01-01",
  skill_id: null,
  skill_version_id: null,
};

const mockKeyMessages: KeyMessageStatus[] = [
  { message: "Efficacy data", delivered: true, detected_at: "2024-01-01" },
  { message: "Safety profile", delivered: false, detected_at: null },
];

describe("ScenarioPanel", () => {
  const defaultProps = {
    scenario: mockScenario,
    keyMessagesStatus: mockKeyMessages,
    isCollapsed: false,
    onToggle: vi.fn(),
  };

  it("renders scenario product and area when expanded", () => {
    render(<ScenarioPanel {...defaultProps} />);
    expect(screen.getByText("DrugX")).toBeInTheDocument();
    // "Oncology" appears in multiple places (therapeutic area + HCP specialty)
    const oncologyElements = screen.getAllByText("Oncology");
    expect(oncologyElements.length).toBeGreaterThan(0);
  });

  it("renders HCP profile info", () => {
    render(<ScenarioPanel {...defaultProps} />);
    expect(screen.getByText("Dr. Jane Doe")).toBeInTheDocument();
  });

  it("renders scoring criteria section", () => {
    render(<ScenarioPanel {...defaultProps} />);
    expect(screen.getByText("session.scoringCriteria")).toBeInTheDocument();
  });

  it("renders collapsed state with toggle button", () => {
    render(<ScenarioPanel {...defaultProps} isCollapsed />);
    expect(screen.queryByText("DrugX")).not.toBeInTheDocument();
    const expandButton = screen.getByLabelText("session.trainingPanel");
    expect(expandButton).toBeInTheDocument();
  });

  it("calls onToggle when collapse button is clicked", async () => {
    const onToggle = vi.fn();
    render(<ScenarioPanel {...defaultProps} onToggle={onToggle} />);
    // The expanded state has aria-expanded=true
    const collapseBtn = screen.getByRole("button", { expanded: true });
    await userEvent.click(collapseBtn);
    expect(onToggle).toHaveBeenCalledOnce();
  });
});
