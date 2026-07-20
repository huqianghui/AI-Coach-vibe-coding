import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ScenarioTable } from "./scenario-table";
import type { Scenario } from "@/types/scenario";

const mockNavigate = vi.fn();
vi.mock("react-router-dom", () => ({
  useNavigate: () => mockNavigate,
}));

const i18nKeys: Record<string, string> = {
  "scenarios.table.name": "Name",
  "scenarios.table.tags": "Tags",
  "scenarios.table.hcp": "HCP",
  "scenarios.table.mode": "Mode",
  "scenarios.table.difficulty": "Difficulty",
  "scenarios.table.status": "Status",
  "scenarios.table.actions": "Actions",
  "scenarios.table.edit": "Edit",
  "scenarios.table.activate": "Activate",
  "scenarios.table.archive": "Archive",
  "scenarios.table.clone": "Clone",
  "scenarios.table.delete": "Delete",
  "scenarios.table.previous": "Previous",
  "scenarios.table.next": "Next",
  "scenarios.emptyTitle": "No scenarios found",
};

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      if (key === "scenarios.table.pageInfo" && opts) {
        return `Page ${opts.page} of ${opts.total}`;
      }
      return i18nKeys[key] ?? key;
    },
    i18n: { changeLanguage: vi.fn(), language: "en" },
  }),
}));

const makeScenario = (overrides: Partial<Scenario> = {}): Scenario => ({
  id: "sc-1",
  name: "Test Scenario",
  description: "A test",
  tags: ["product:DrugA", "area:Oncology"],
  mode: "f2f",
  difficulty: "easy",
  status: "active",
  hcp_profile_id: "hcp-1",
  hcp_profile: {
    id: "hcp-1",
    name: "Dr. Test",
    specialty: "Oncology",
    avatar_url: "",
    personality_type: "friendly",
    voice_live_instance_id: null,
    voice_live_instance: null,
  },
  key_messages: [],
  rubric_id: "rubric-1",
  pass_threshold: 70,
  created_by: "admin",
  created_at: "2024-01-01",
  updated_at: "2024-01-01",
  skill_id: "skill-1",
  skill_version_id: null,
  ...overrides,
});

describe("ScenarioTable", () => {
  const defaultProps = {
    scenarios: [makeScenario()],
    onDelete: vi.fn(),
    onClone: vi.fn(),
    onTransition: vi.fn(),
  };

  beforeEach(() => {
    mockNavigate.mockClear();
  });

  it("renders scenario name in table", () => {
    render(<ScenarioTable {...defaultProps} />);
    expect(screen.getByText("Test Scenario")).toBeInTheDocument();
  });

  it("renders tags as badges", () => {
    render(<ScenarioTable {...defaultProps} />);
    expect(screen.getByText("DrugA")).toBeInTheDocument();
    expect(screen.getByText("Oncology")).toBeInTheDocument();
  });

  it("renders dash when no tags", () => {
    const noTagsScenario = makeScenario({ tags: [] });
    render(<ScenarioTable {...defaultProps} scenarios={[noTagsScenario]} />);
    expect(screen.getByText("-")).toBeInTheDocument();
  });

  it("renders empty state when no scenarios", () => {
    render(<ScenarioTable {...defaultProps} scenarios={[]} />);
    expect(screen.getByText("No scenarios found")).toBeInTheDocument();
  });

  it("renders column headers", () => {
    render(<ScenarioTable {...defaultProps} />);
    expect(screen.getByText("Name")).toBeInTheDocument();
    expect(screen.getByText("Tags")).toBeInTheDocument();
    expect(screen.getByText("HCP")).toBeInTheDocument();
    expect(screen.getByText("Mode")).toBeInTheDocument();
    expect(screen.getByText("Difficulty")).toBeInTheDocument();
    expect(screen.getByText("Status")).toBeInTheDocument();
  });

  it("toggles sort direction when clicking column header", async () => {
    render(<ScenarioTable {...defaultProps} />);
    const nameHeader = screen.getByText("Name");
    await userEvent.click(nameHeader);
    await userEvent.click(nameHeader);
  });

  it("sorts by difficulty when Difficulty header clicked", async () => {
    render(<ScenarioTable {...defaultProps} />);
    await userEvent.click(screen.getByText("Difficulty"));
    expect(screen.getByText("easy")).toBeInTheDocument();
  });

  it("renders HCP avatar fallback", () => {
    render(<ScenarioTable {...defaultProps} />);
    expect(screen.getByText("DT")).toBeInTheDocument();
  });

  it("renders dash for scenario without hcp_profile", () => {
    const noHcpScenario = makeScenario({ hcp_profile: undefined });
    render(<ScenarioTable {...defaultProps} scenarios={[noHcpScenario]} />);
    expect(screen.getAllByText("-").length).toBeGreaterThan(0);
  });

  it("renders mode badge", () => {
    render(<ScenarioTable {...defaultProps} />);
    expect(screen.getByText("f2f")).toBeInTheDocument();
  });

  it("renders status badge", () => {
    render(<ScenarioTable {...defaultProps} />);
    expect(screen.getByText("active")).toBeInTheDocument();
  });

  it("applies opacity to archived scenarios", () => {
    const archivedScenario = makeScenario({ status: "archived" });
    render(<ScenarioTable {...defaultProps} scenarios={[archivedScenario]} />);
    expect(screen.getByText("archived")).toBeInTheDocument();
  });

  it("shows pagination when more than 10 scenarios", () => {
    const manyScenarios = Array.from({ length: 15 }, (_, i) =>
      makeScenario({ id: `sc-${i}`, name: `Scenario ${i}` })
    );
    render(<ScenarioTable {...defaultProps} scenarios={manyScenarios} />);
    expect(screen.getByText(/Page 1 of 2/)).toBeInTheDocument();
  });

  it("navigates to next page", async () => {
    const manyScenarios = Array.from({ length: 15 }, (_, i) =>
      makeScenario({ id: `sc-${i}`, name: `Scenario ${i}` })
    );
    render(<ScenarioTable {...defaultProps} scenarios={manyScenarios} />);
    await userEvent.click(screen.getByText("Next"));
    expect(screen.getByText(/Page 2 of 2/)).toBeInTheDocument();
  });

  it("calls onClone via dropdown menu", async () => {
    const onClone = vi.fn();
    render(<ScenarioTable {...defaultProps} onClone={onClone} />);
    const menuButton = screen.getByRole("button", { name: "" });
    await userEvent.click(menuButton);
    await userEvent.click(screen.getByText("Clone"));
    expect(onClone).toHaveBeenCalledWith("sc-1");
  });

  it("calls onDelete via dropdown menu", async () => {
    const onDelete = vi.fn();
    render(<ScenarioTable {...defaultProps} onDelete={onDelete} />);
    const menuButton = screen.getByRole("button", { name: "" });
    await userEvent.click(menuButton);
    await userEvent.click(screen.getByText("Delete"));
    expect(onDelete).toHaveBeenCalledWith("sc-1");
  });

  it("navigates to scenario editor on Edit click", async () => {
    render(<ScenarioTable {...defaultProps} />);
    const menuButton = screen.getByRole("button", { name: "" });
    await userEvent.click(menuButton);
    await userEvent.click(screen.getByText("Edit"));
    expect(mockNavigate).toHaveBeenCalledWith("/admin/scenarios/sc-1");
  });

  it("shows Activate action for draft scenarios", async () => {
    const draftScenario = makeScenario({ status: "draft" });
    render(<ScenarioTable {...defaultProps} scenarios={[draftScenario]} />);
    const menuButton = screen.getByRole("button", { name: "" });
    await userEvent.click(menuButton);
    expect(screen.getByText("Activate")).toBeInTheDocument();
  });

  it("shows Archive action for active scenarios", async () => {
    render(<ScenarioTable {...defaultProps} />);
    const menuButton = screen.getByRole("button", { name: "" });
    await userEvent.click(menuButton);
    expect(screen.getByText("Archive")).toBeInTheDocument();
  });

  it("calls onTransition for Activate action", async () => {
    const onTransition = vi.fn();
    const draftScenario = makeScenario({ status: "draft" });
    render(<ScenarioTable {...defaultProps} scenarios={[draftScenario]} onTransition={onTransition} />);
    const menuButton = screen.getByRole("button", { name: "" });
    await userEvent.click(menuButton);
    await userEvent.click(screen.getByText("Activate"));
    expect(onTransition).toHaveBeenCalledWith("sc-1", "active");
  });

  it("navigates to scenario editor on double-click", () => {
    render(<ScenarioTable {...defaultProps} />);
    const row = screen.getByText("Test Scenario").closest("tr")!;
    fireEvent.doubleClick(row);
    expect(mockNavigate).toHaveBeenCalledWith("/admin/scenarios/sc-1");
  });

  it("does not navigate on double-click for archived scenarios", () => {
    const archivedScenario = makeScenario({ status: "archived" });
    render(<ScenarioTable {...defaultProps} scenarios={[archivedScenario]} />);
    const row = screen.getByText("Test Scenario").closest("tr")!;
    fireEvent.doubleClick(row);
    expect(mockNavigate).not.toHaveBeenCalled();
  });
});
