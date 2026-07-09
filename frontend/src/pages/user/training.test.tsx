import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

const mockNavigate = vi.fn();
const mockMutateAsync = vi.fn();
const mockConferenceMutateAsync = vi.fn();
const mockCreateGroupRunMutateAsync = vi.fn();
let scenarioData: unknown[] | undefined;
let scenarioGroupData: unknown[] | undefined;
let isLoading = false;


vi.mock("react-router-dom", async () => {
  const actual =
    await vi.importActual<typeof import("react-router-dom")>(
      "react-router-dom",
    );
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, string>) => {
      if (opts?.defaultValue) return opts.defaultValue;
      return key;
    },
    i18n: { changeLanguage: vi.fn(), language: "en" },
  }),
}));

vi.mock("@/hooks/use-scenarios", () => ({
  useActiveScenarios: () => ({
    data: scenarioData,
    isLoading,
  }),
}));

vi.mock("@/hooks/use-scenario-groups", () => ({
  useActiveScenarioGroups: () => ({
    data: scenarioGroupData,
    isLoading,
  }),
  useCreateScenarioGroupRun: () => ({
    mutateAsync: mockCreateGroupRunMutateAsync,
    isPending: false,
  }),
}));

vi.mock("@/hooks/use-session", () => ({
  useCreateSession: () => ({
    mutateAsync: mockMutateAsync,
    isPending: false,
  }),
}));

vi.mock("@/hooks/use-conference", () => ({
  useCreateConferenceSession: () => ({
    mutateAsync: mockConferenceMutateAsync,
    isPending: false,
  }),
}));

vi.mock("@/hooks/use-config", () => ({
  useFeatureFlags: () => ({
    data: {
      features: {
        voice_enabled: true,
        voice_live_enabled: true,
        avatar_enabled: true,
      },
    },
  }),
}));

vi.mock("@/components/shared", () => ({
  EmptyState: ({
    title,
    body,
  }: {
    title: string;
    body: string;
  }) => (
    <div data-testid="empty-state">
      <span>{title}</span>
      <span>{body}</span>
    </div>
  ),
}));

vi.mock("@/components/coach", () => ({
  ScenarioCard: ({
    scenario,
    onStart,
    availableModes,
    defaultMode,
  }: {
    scenario: { id: string; name: string };
    onStart: (id: string, mode: string) => void;
    availableModes?: string[];
    defaultMode?: string;
  }) => (
    <div data-testid="scenario-card">
      <span>{scenario.name}</span>
      <span data-testid={`modes-${scenario.id}`}>{availableModes?.join(",")}</span>
      <span data-testid={`default-mode-${scenario.id}`}>{defaultMode}</span>
      <button onClick={() => onStart(scenario.id, defaultMode ?? "text")}>Start</button>
      {availableModes?.map((mode) => (
        <button
          key={mode}
          data-testid={`start-${scenario.id}-${mode}`}
          onClick={() => onStart(scenario.id, mode)}
        >
          {mode}
        </button>
      ))}
    </div>
  ),
}));

function renderPage(initialEntry = "/user/training") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <ScenarioSelection />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

let ScenarioSelection: React.ComponentType;

beforeEach(async () => {
  vi.clearAllMocks();
  mockConferenceMutateAsync.mockReset();
  mockCreateGroupRunMutateAsync.mockReset();
  scenarioData = [];
  scenarioGroupData = [];
  isLoading = false;
  const mod = await import("./training");
  ScenarioSelection = mod.default;
});

describe("ScenarioSelection (Training) Page", () => {
  it("renders the page title", () => {
    renderPage();
    expect(screen.getByText("scenarioSelection.title")).toBeInTheDocument();
  });

  it("renders F2F, Conference, and group tabs", () => {
    renderPage();
    expect(screen.getByText("scenarioSelection.tabF2F")).toBeInTheDocument();
    expect(
      screen.getByText("scenarioSelection.tabConference"),
    ).toBeInTheDocument();
    expect(screen.getByText("组合训练")).toBeInTheDocument();
  });

  it("shows empty state when no scenarios available", () => {
    scenarioData = [];
    renderPage();
    expect(screen.getAllByTestId("empty-state").length).toBeGreaterThan(0);
  });

  it("shows loading skeleton when data is loading", () => {
    isLoading = true;
    scenarioData = undefined;
    const { container } = renderPage();
    expect(container.innerHTML.length).toBeGreaterThan(0);
  });

  it("renders scenario cards when scenarios exist", () => {
    scenarioData = [
      {
        id: "sc-1",
        name: "F2F Scenario",
        description: "Test",
        product: "Brukinsa",
        mode: "f2f",
        difficulty: "medium",
        status: "active",
      },
      {
        id: "sc-2",
        name: "Conference Scenario",
        description: "Test 2",
        product: "Tislelizumab",
        mode: "conference",
        difficulty: "hard",
        status: "active",
      },
    ];
    renderPage();

    const cards = screen.getAllByTestId("scenario-card");
    expect(cards.length).toBeGreaterThanOrEqual(1);
  });

  it("passes text, voice, and digital human modes to F2F scenario cards", () => {
    scenarioData = [
      {
        id: "sc-1",
        name: "F2F Scenario",
        description: "Test",
        product: "Brukinsa",
        mode: "f2f",
        difficulty: "medium",
        status: "active",
        hcp_profile: {
          voice_live_enabled: true,
          avatar_enabled: true,
        },
      },
    ];
    renderPage();

    expect(screen.getByTestId("modes-sc-1")).toHaveTextContent(
      "text,voice_realtime_model,digital_human_realtime_model",
    );
    expect(screen.getByTestId("default-mode-sc-1")).toHaveTextContent(
      "digital_human_realtime_model",
    );
  });

  it("selects Conference tab when mode query param is conference", () => {
    scenarioData = [
      {
        id: "sc-1",
        name: "F2F Scenario",
        description: "Test",
        product: "Brukinsa",
        mode: "f2f",
        difficulty: "medium",
        status: "active",
      },
      {
        id: "sc-2",
        name: "Conference Scenario",
        description: "Test 2",
        product: "Tislelizumab",
        mode: "conference",
        difficulty: "hard",
        status: "active",
      },
    ];

    renderPage("/user/training?mode=conference");

    expect(screen.queryByText("F2F Scenario")).not.toBeInTheDocument();
    expect(screen.getByText("Conference Scenario")).toBeInTheDocument();
  });

  it("disables digital human when the HCP Voice Live instance has avatar off", () => {
    scenarioData = [
      {
        id: "sc-1",
        name: "F2F Scenario",
        description: "Test",
        product: "Brukinsa",
        mode: "f2f",
        difficulty: "medium",
        status: "active",
        hcp_profile: {
          voice_live_enabled: true,
          avatar_enabled: false,
        },
      },
    ];
    renderPage();

    expect(screen.getByTestId("modes-sc-1")).toHaveTextContent(
      "text,voice_realtime_model",
    );
    expect(screen.getByTestId("default-mode-sc-1")).toHaveTextContent(
      "voice_realtime_model",
    );
  });

  it("renders search input", () => {
    renderPage();
    // The mock t() returns the key directly
    expect(
      screen.getByPlaceholderText("scenarioSelection.searchPlaceholder"),
    ).toBeInTheDocument();
  });
});

describe("ScenarioSelection Tabs", () => {
  it("does not render Voice tab (voice config is admin-only)", () => {
    renderPage();
    expect(
      screen.queryByText("scenarioSelection.tabVoice"),
    ).not.toBeInTheDocument();
  });

  it("renders F2F, Conference, and group tabs", () => {
    renderPage();
    expect(screen.getByText("scenarioSelection.tabF2F")).toBeInTheDocument();
    expect(
      screen.getByText("scenarioSelection.tabConference"),
    ).toBeInTheDocument();
    expect(screen.getByText("组合训练")).toBeInTheDocument();
  });
});

// NEW TESTS for uncovered branches
describe("ScenarioSelection Filters and Actions", () => {
  const twoScenarios = [
    {
      id: "sc-1",
      name: "F2F Scenario",
      description: "Test description",
      product: "Brukinsa",
      mode: "f2f",
      difficulty: "medium",
      status: "active",
      hcp_profile: {
        voice_live_enabled: true,
        avatar_enabled: false,
      },
    },
    {
      id: "sc-2",
      name: "Advanced Meeting",
      description: "Test 2",
      product: "Tislelizumab",
      mode: "conference",
      difficulty: "hard",
      status: "active",
      hcp_profile: {
        voice_live_enabled: true,
        avatar_enabled: false,
      },
    },
  ];

  it("filters scenarios by search term matching name", async () => {
    scenarioData = twoScenarios;
    renderPage();
    const input = screen.getByPlaceholderText("scenarioSelection.searchPlaceholder");
    await userEvent.setup().type(input, "F2F");
    expect(screen.getByText("F2F Scenario")).toBeInTheDocument();
    expect(screen.queryByText("Advanced Meeting")).not.toBeInTheDocument();
  });

  it("filters scenarios by search term matching description", async () => {
    scenarioData = twoScenarios;
    renderPage();
    // Switch to Conference tab to see the conference scenario
    const confTab = screen.getByText("scenarioSelection.tabConference");
    await userEvent.setup().click(confTab);
    const input = screen.getByPlaceholderText("scenarioSelection.searchPlaceholder");
    await userEvent.setup().type(input, "Test 2");
    expect(screen.queryByText("F2F Scenario")).not.toBeInTheDocument();
    expect(screen.getByText("Advanced Meeting")).toBeInTheDocument();
  });

  it("creates session and navigates to training session on F2F start", async () => {
    scenarioData = twoScenarios;
    mockMutateAsync.mockResolvedValue({ id: "new-session-1" });
    renderPage();

    // Click the Start button on first scenario card
    const startBtns = screen.getAllByText("Start");
    await userEvent.setup().click(startBtns[0]!);

    expect(mockMutateAsync).toHaveBeenCalledWith({
      scenarioId: "sc-1",
      mode: "voice_realtime_model",
    });
    expect(mockNavigate).toHaveBeenCalledWith("/user/training/session?id=new-session-1");
  });

  it("creates session and navigates to conference on Conference tab start", async () => {
    scenarioData = twoScenarios;
    mockConferenceMutateAsync.mockResolvedValue({ id: "conf-session-1" });
    renderPage();

    // Switch to Conference tab
    const confTab = screen.getByText("scenarioSelection.tabConference");
    await userEvent.setup().click(confTab);

    // Click start on the conference scenario card (sc-2 is mode: "conference")
    const startBtns = screen.getAllByText("Start");
    await userEvent.setup().click(startBtns[0]!);

    expect(mockConferenceMutateAsync).toHaveBeenCalledWith({
      scenarioId: "sc-2",
      mode: "voice_realtime_model",
    });
    expect(mockNavigate).toHaveBeenCalledWith(
      "/user/training/conference?id=conf-session-1&inputMode=audio",
    );
  });

  it("passes text and voice modes to conference scenario cards", async () => {
    scenarioData = twoScenarios;
    renderPage("/user/training?mode=conference");

    expect(screen.getByTestId("modes-sc-2")).toHaveTextContent(
      "text,voice_realtime_model",
    );
    expect(screen.getByTestId("default-mode-sc-2")).toHaveTextContent(
      "voice_realtime_model",
    );
  });

  it("allows digital human mode on avatar-capable conference scenario cards", async () => {
    scenarioData = [
      {
        id: "sc-2",
        name: "Advanced Meeting",
        description: "Test 2",
        product: "Tislelizumab",
        mode: "conference",
        difficulty: "hard",
        status: "active",
        hcp_profile: {
          voice_live_enabled: true,
          avatar_enabled: true,
        },
      },
    ];

    renderPage("/user/training?mode=conference");

    expect(screen.getByTestId("modes-sc-2")).toHaveTextContent(
      "text,voice_realtime_model,digital_human_realtime_model",
    );
    expect(screen.getByTestId("default-mode-sc-2")).toHaveTextContent(
      "voice_realtime_model",
    );
  });

  it("starts conference digital human mode through the conference session page", async () => {
    scenarioData = [
      {
        id: "sc-2",
        name: "Advanced Meeting",
        description: "Test 2",
        product: "Tislelizumab",
        mode: "conference",
        difficulty: "hard",
        status: "active",
        hcp_profile: {
          voice_live_enabled: true,
          avatar_enabled: true,
        },
      },
    ];
    mockConferenceMutateAsync.mockResolvedValue({ id: "digital-session-1" });

    renderPage("/user/training?mode=conference");

    await userEvent.setup().click(
      screen.getByTestId("start-sc-2-digital_human_realtime_model"),
    );

    expect(mockConferenceMutateAsync).toHaveBeenCalledWith({
      scenarioId: "sc-2",
      mode: "digital_human_realtime_model",
    });
    expect(mockMutateAsync).not.toHaveBeenCalled();
    expect(mockNavigate).toHaveBeenCalledWith(
      "/user/training/conference?id=digital-session-1&inputMode=audio",
    );
  });

  it("handles createSession failure gracefully for F2F", async () => {
    scenarioData = twoScenarios;
    mockMutateAsync.mockRejectedValue(new Error("API error"));
    renderPage();

    const startBtns = screen.getAllByText("Start");
    await userEvent.setup().click(startBtns[0]!);

    // Should not navigate on failure
    expect(mockNavigate).not.toHaveBeenCalled();
  });

  it("handles createSession failure gracefully for conference", async () => {
    scenarioData = twoScenarios;
    mockConferenceMutateAsync.mockRejectedValue(new Error("API error"));
    renderPage();

    const confTab = screen.getByText("scenarioSelection.tabConference");
    await userEvent.setup().click(confTab);

    const startBtns = screen.getAllByText("Start");
    await userEvent.setup().click(startBtns[0]!);

    expect(mockNavigate).not.toHaveBeenCalled();
  });

  it("shows empty state when search matches no scenarios", async () => {
    scenarioData = twoScenarios;
    renderPage();
    const input = screen.getByPlaceholderText("scenarioSelection.searchPlaceholder");
    await userEvent.setup().type(input, "nonexistent");
    expect(screen.getAllByTestId("empty-state").length).toBeGreaterThan(0);
  });

  it("renders loading skeletons with 6 skeleton card containers", () => {
    isLoading = true;
    scenarioData = undefined;
    const { container } = renderPage();
    // Loading state should render skeleton cards (overflow-hidden rounded-lg)
    const skeletonContainers = container.querySelectorAll(".overflow-hidden.rounded-lg");
    expect(skeletonContainers.length).toBeGreaterThanOrEqual(6);
  });
});
