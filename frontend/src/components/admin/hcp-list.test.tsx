import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HcpList } from "./hcp-list";
import type { HcpProfile } from "@/types/hcp";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { changeLanguage: vi.fn(), language: "en" },
  }),
}));

vi.mock("@/components/shared/empty-state", () => ({
  EmptyState: ({ title }: { title: string }) => <div data-testid="empty-state">{title}</div>,
}));

const mockProfiles: HcpProfile[] = [
  {
    id: "1",
    name: "Dr. Alice Wang",
    specialty: "Oncology",
    hospital: "City Hospital",
    title: "Chief Physician",
    avatar_url: "",
    personality_type: "friendly",
    emotional_state: 50,
    communication_style: 70,
    expertise_areas: [],
    prescribing_habits: "",
    concerns: "",
    objections: [],
    probe_topics: [],
    difficulty: "easy",
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
  {
    id: "2",
    name: "Dr. Bob Chen",
    specialty: "Cardiology",
    hospital: "Central Hospital",
    title: "Attending",
    avatar_url: "",
    personality_type: "skeptical",
    emotional_state: 60,
    communication_style: 40,
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
];

describe("HcpList", () => {
  const defaultProps = {
    profiles: mockProfiles,
    selectedId: undefined,
    onSelect: vi.fn(),
    onCreateNew: vi.fn(),
    searchQuery: "",
    onSearchChange: vi.fn(),
  };

  it("renders profile names", () => {
    render(<HcpList {...defaultProps} />);
    expect(screen.getByText("Dr. Alice Wang")).toBeInTheDocument();
    expect(screen.getByText("Dr. Bob Chen")).toBeInTheDocument();
  });

  it("renders search input", () => {
    render(<HcpList {...defaultProps} />);
    expect(screen.getByPlaceholderText("hcp.searchPlaceholder")).toBeInTheDocument();
  });

  it("calls onSelect when a profile is clicked", async () => {
    const onSelect = vi.fn();
    render(<HcpList {...defaultProps} onSelect={onSelect} />);
    await userEvent.click(screen.getByText("Dr. Alice Wang"));
    expect(onSelect).toHaveBeenCalledWith("1");
  });

  it("renders empty state when no profiles", () => {
    render(<HcpList {...defaultProps} profiles={[]} />);
    expect(screen.getByTestId("empty-state")).toBeInTheDocument();
  });

  it("renders create button", async () => {
    const onCreateNew = vi.fn();
    render(<HcpList {...defaultProps} onCreateNew={onCreateNew} />);
    const createBtn = screen.getByText("hcp.createButton");
    await userEvent.click(createBtn);
    expect(onCreateNew).toHaveBeenCalledOnce();
  });
});
