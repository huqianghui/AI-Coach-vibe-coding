import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import SessionHistory from "./session-history";
import type { ScoreHistoryItem } from "@/types/report";
import type { CoachingSession } from "@/types/session";

const mockNavigate = vi.fn();

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, string>) => {
      if (opts?.defaultValue) return opts.defaultValue;
      return key;
    },
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
  };
});

// Mock recharts
vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="responsive-container">{children}</div>
  ),
  LineChart: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="line-chart">{children}</div>
  ),
  Line: () => <div />,
  XAxis: () => <div />,
  YAxis: () => <div />,
  CartesianGrid: () => <div />,
  Tooltip: () => <div />,
  Legend: () => <div />,
}));

vi.mock("@/components/analytics", () => ({
  PerformanceRadar: () => <div data-testid="performance-radar" />,
}));

vi.mock("@/components/ui", () => ({
  Badge: ({ children, className }: { children: React.ReactNode; className?: string }) => (
    <span data-testid="badge" className={className}>{children}</span>
  ),
  Button: ({
    children,
    onClick,
    disabled,
    variant,
    size,
  }: {
    children: React.ReactNode;
    onClick?: (e: React.MouseEvent) => void;
    disabled?: boolean;
    variant?: string;
    size?: string;
  }) => (
    <button onClick={onClick} disabled={disabled} data-variant={variant} data-size={size}>
      {children}
    </button>
  ),
  Input: ({
    placeholder,
    value,
    onChange,
  }: {
    placeholder?: string;
    value?: string;
    onChange?: (e: React.ChangeEvent<HTMLInputElement>) => void;
    className?: string;
  }) => (
    <input
      placeholder={placeholder}
      value={value}
      onChange={onChange}
      data-testid="search-input"
    />
  ),
  Select: ({
    children,
    value,
    onValueChange,
  }: {
    children: React.ReactNode;
    onValueChange?: (v: string) => void;
    value: string;
  }) => (
    <div data-testid="select" data-value={value}>
      {children}
      {/* Hidden select for testing onValueChange */}
      <select
        data-testid="hidden-select"
        value={value}
        onChange={(e) => onValueChange?.(e.target.value)}
      >
        <option value="__all__">All</option>
        <option value="created">Created</option>
        <option value="in_progress">In Progress</option>
        <option value="completed">Completed</option>
        <option value="scoring">Scoring</option>
        <option value="scored">Scored</option>
        <option value="high">High</option>
        <option value="mid">Mid</option>
        <option value="low">Low</option>
      </select>
    </div>
  ),
  SelectContent: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  SelectItem: ({
    children,
    value,
  }: {
    children: React.ReactNode;
    value: string;
  }) => <option value={value}>{children}</option>,
  SelectTrigger: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="select-trigger">{children}</div>
  ),
  SelectValue: () => <span />,
  Skeleton: ({ className }: { className?: string }) => (
    <div data-testid="skeleton" className={`animate-pulse ${className ?? ""}`} />
  ),
}));

const mockHistoryData: ScoreHistoryItem[] = [
  {
    session_id: "s1",
    scenario_name: "Dr. Sarah Mitchell",
    overall_score: 85,
    passed: true,
    completed_at: "2026-03-20T10:00:00Z",
    dimensions: [
      { dimension: "Knowledge", score: 88, weight: 0.3, improvement_pct: 5 },
      { dimension: "Communication", score: 82, weight: 0.3, improvement_pct: -2 },
    ],
  },
  {
    session_id: "s2",
    scenario_name: "Dr. James Wong",
    overall_score: 55,
    passed: false,
    completed_at: "2026-03-19T10:00:00Z",
    dimensions: [
      { dimension: "Knowledge", score: 60, weight: 0.3, improvement_pct: null },
      { dimension: "Communication", score: 50, weight: 0.3, improvement_pct: null },
    ],
  },
];

const mockCompletedSession: CoachingSession = {
  id: "s3",
  user_id: "u1",
  scenario_id: "sc1",
  scenario_name: "Dr. Pending Review",
  status: "completed",
  started_at: "2026-03-21T09:00:00Z",
  completed_at: "2026-03-21T09:30:00Z",
  duration_seconds: 1800,
  key_messages_status: [],
  overall_score: null,
  passed: null,
  mode: "text",
  agent_name: null,
  agent_version: null,
  message_count: 12,
  created_at: "2026-03-21T09:00:00Z",
  updated_at: "2026-03-21T09:30:00Z",
};

const mockScoredSession: CoachingSession = {
  id: "s1",
  user_id: "u1",
  scenario_id: "sc2",
  scenario_name: "Dr. Sarah Mitchell",
  status: "scored",
  started_at: "2026-03-20T09:00:00Z",
  completed_at: "2026-03-20T10:00:00Z",
  duration_seconds: 3600,
  key_messages_status: [],
  overall_score: 85,
  passed: true,
  mode: "text",
  agent_name: "dr-sarah-mitchell",
  agent_version: "1",
  message_count: 20,
  created_at: "2026-03-20T09:00:00Z",
  updated_at: "2026-03-20T10:00:00Z",
};

const mockCreatedSession: CoachingSession = {
  id: "s4",
  user_id: "u1",
  scenario_id: "sc3",
  scenario_name: "Dr. New Session",
  status: "created",
  started_at: null,
  completed_at: null,
  duration_seconds: null,
  key_messages_status: [],
  overall_score: null,
  passed: null,
  mode: "text",
  agent_name: null,
  agent_version: null,
  message_count: 0,
  created_at: "2026-03-22T08:00:00Z",
  updated_at: "2026-03-22T08:00:00Z",
};

const mockInProgressSession: CoachingSession = {
  id: "s5",
  user_id: "u1",
  scenario_id: "sc4",
  scenario_name: "Dr. Active Practice",
  status: "in_progress",
  started_at: "2026-03-22T09:00:00Z",
  completed_at: null,
  duration_seconds: null,
  key_messages_status: [],
  overall_score: null,
  passed: null,
  mode: "voice_pipeline",
  agent_name: "dr-active-practice",
  agent_version: "3",
  message_count: 5,
  created_at: "2026-03-22T09:00:00Z",
  updated_at: "2026-03-22T09:15:00Z",
};

let mockScoreHistoryReturn: {
  data: ScoreHistoryItem[] | undefined;
  isLoading: boolean;
} = { data: mockHistoryData, isLoading: false };

let mockSessionsReturn: {
  data: { items: CoachingSession[]; total: number; page: number; page_size: number; total_pages: number } | undefined;
  isLoading: boolean;
} = {
  data: {
    items: [mockCompletedSession, mockScoredSession],
    total: 2,
    page: 1,
    page_size: 100,
    total_pages: 1,
  },
  isLoading: false,
};

const mockTriggerScoringMutate = vi.fn();

vi.mock("@/hooks/use-scoring", () => ({
  useScoreHistory: () => mockScoreHistoryReturn,
  useTriggerScoring: () => ({
    mutate: mockTriggerScoringMutate,
    isPending: false,
  }),
}));

vi.mock("@/hooks/use-session", () => ({
  useUserSessions: () => mockSessionsReturn,
}));

function renderSessionHistory() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <SessionHistory />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("SessionHistory", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockScoreHistoryReturn = { data: mockHistoryData, isLoading: false };
    mockSessionsReturn = {
      data: {
        items: [mockCompletedSession, mockScoredSession],
        total: 2,
        page: 1,
        page_size: 100,
        total_pages: 1,
      },
      isLoading: false,
    };
  });

  it("renders the page title", () => {
    renderSessionHistory();
    expect(screen.getByText("history.title")).toBeInTheDocument();
  });

  it("renders scored session rows", () => {
    renderSessionHistory();
    expect(screen.getAllByText("Dr. Sarah Mitchell").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Dr. James Wong").length).toBeGreaterThanOrEqual(1);
  });

  it("renders completed (unscored) session rows", () => {
    renderSessionHistory();
    expect(screen.getAllByText("Dr. Pending Review").length).toBeGreaterThanOrEqual(1);
  });

  it("renders overall scores for scored sessions", () => {
    renderSessionHistory();
    expect(screen.getAllByText("85").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("55").length).toBeGreaterThanOrEqual(1);
  });

  it("renders status badges for different states", () => {
    renderSessionHistory();
    // Completed session shows "statusPending" badge
    expect(screen.getAllByText("history.statusPending").length).toBeGreaterThanOrEqual(1);
    // Scored sessions show "statusScored" badge
    expect(screen.getAllByText("history.statusScored").length).toBeGreaterThanOrEqual(1);
  });

  it("renders submit scoring button for completed sessions", () => {
    renderSessionHistory();
    const submitButtons = screen.getAllByText("history.submitScoring");
    expect(submitButtons.length).toBeGreaterThanOrEqual(1);
  });

  it("triggers scoring when submit button is clicked", async () => {
    const user = userEvent.setup();
    renderSessionHistory();
    const submitButtons = screen.getAllByText("history.submitScoring");
    await user.click(submitButtons[0]!);
    expect(mockTriggerScoringMutate).toHaveBeenCalledWith("s3", expect.any(Object));
  });

  it("does not render the retired analytics charts", () => {
    renderSessionHistory();
    expect(screen.queryByTestId("performance-radar")).not.toBeInTheDocument();
    expect(screen.queryByTestId("line-chart")).not.toBeInTheDocument();
  });

  it("renders the search input", () => {
    renderSessionHistory();
    expect(screen.getByTestId("search-input")).toBeInTheDocument();
  });

  it("renders view details links for scored sessions", () => {
    renderSessionHistory();
    const viewDetails = screen.getAllByText("history.viewDetails");
    expect(viewDetails.length).toBeGreaterThanOrEqual(2);
  });

  it("navigates to scoring page when scored row is clicked", async () => {
    const user = userEvent.setup();
    renderSessionHistory();

    // Find a desktop table row for a scored session
    const elements = screen.getAllByText("Dr. Sarah Mitchell");
    const row = elements.map((el) => el.closest("tr")).find(Boolean);
    expect(row).toBeTruthy();
    await user.click(row!);

    expect(mockNavigate).toHaveBeenCalledWith("/user/scoring/s1");
  });

  it("does NOT navigate when completed (unscored) row is clicked", async () => {
    const user = userEvent.setup();
    renderSessionHistory();

    const elements = screen.getAllByText("Dr. Pending Review");
    const row = elements.map((el) => el.closest("tr")).find(Boolean);
    expect(row).toBeTruthy();
    await user.click(row!);

    expect(mockNavigate).not.toHaveBeenCalled();
  });

  it("shows loading state", () => {
    mockScoreHistoryReturn = { data: undefined, isLoading: true };
    renderSessionHistory();
    const skeleton = document.querySelector(".animate-pulse");
    expect(skeleton).toBeTruthy();
  });

  it("shows empty state when no history and no sessions", () => {
    mockScoreHistoryReturn = { data: [], isLoading: false };
    mockSessionsReturn = {
      data: { items: [], total: 0, page: 1, page_size: 100, total_pages: 0 },
      isLoading: false,
    };
    renderSessionHistory();
    expect(screen.getByText("history.noSessions")).toBeInTheDocument();
  });

  it("shows empty state when both data sources are undefined", () => {
    mockScoreHistoryReturn = { data: undefined, isLoading: false };
    mockSessionsReturn = { data: undefined, isLoading: false };
    renderSessionHistory();
    expect(screen.getByText("history.noSessions")).toBeInTheDocument();
  });

  it("filters by search term", async () => {
    const user = userEvent.setup();
    renderSessionHistory();
    const input = screen.getByTestId("search-input");
    await user.type(input, "Sarah");
    expect(screen.getAllByText("Dr. Sarah Mitchell").length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText("Dr. James Wong")).not.toBeInTheDocument();
    expect(screen.queryByText("Dr. Pending Review")).not.toBeInTheDocument();
  });

  it("filters by status (completed only)", async () => {
    renderSessionHistory();
    const selects = screen.getAllByTestId("hidden-select");
    const statusSelect = selects[0]!;
    await userEvent.setup().selectOptions(statusSelect, "completed");
    expect(screen.getAllByText("Dr. Pending Review").length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText("Dr. Sarah Mitchell")).not.toBeInTheDocument();
  });

  it("filters by status (scored only)", async () => {
    renderSessionHistory();
    const selects = screen.getAllByTestId("hidden-select");
    const statusSelect = selects[0]!;
    await userEvent.setup().selectOptions(statusSelect, "scored");
    expect(screen.getAllByText("Dr. Sarah Mitchell").length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText("Dr. Pending Review")).not.toBeInTheDocument();
  });

  it("filters by score range (high >= 80)", async () => {
    renderSessionHistory();
    const selects = screen.getAllByTestId("hidden-select");
    const scoreSelect = selects[1]!;
    await userEvent.setup().selectOptions(scoreSelect, "high");
    expect(screen.getAllByText("Dr. Sarah Mitchell").length).toBeGreaterThanOrEqual(1); // 85
    expect(screen.queryByText("Dr. James Wong")).not.toBeInTheDocument(); // 55
  });

  it("filters by score range (low < 60)", async () => {
    renderSessionHistory();
    const selects = screen.getAllByTestId("hidden-select");
    const scoreSelect = selects[1]!;
    await userEvent.setup().selectOptions(scoreSelect, "low");
    expect(screen.getAllByText("Dr. James Wong").length).toBeGreaterThanOrEqual(1); // 55
    expect(screen.queryByText("Dr. Sarah Mitchell")).not.toBeInTheDocument(); // 85
  });

  it("shows results count reflecting filtered items", () => {
    renderSessionHistory();
    const resultsSpan = screen.getByText(/results/);
    // 3 total rows: 2 scored + 1 completed
    expect(resultsSpan.textContent).toContain("3");
  });

  it("renders pagination when more than 10 items", () => {
    // Create 12 scored items
    const manyItems: ScoreHistoryItem[] = Array.from({ length: 12 }, (_, i) => ({
      session_id: `s${i + 1}`,
      scenario_name: `Scenario ${i + 1}`,
      overall_score: 50 + (i % 50),
      passed: i % 3 !== 0,
      completed_at: `2026-03-${String(20 - i).padStart(2, "0")}T10:00:00Z`,
      dimensions: [
        { dimension: "Knowledge", score: 60 + (i % 30), weight: 0.3, improvement_pct: null },
      ],
    }));
    mockScoreHistoryReturn = { data: manyItems, isLoading: false };
    mockSessionsReturn = {
      data: { items: [], total: 0, page: 1, page_size: 100, total_pages: 0 },
      isLoading: false,
    };
    renderSessionHistory();
    expect(screen.getAllByText("history.previous").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("history.next").length).toBeGreaterThanOrEqual(1);
  });

  it("does not render pagination when 10 or fewer items", () => {
    renderSessionHistory(); // 3 items
    expect(screen.queryByText("history.previous")).not.toBeInTheDocument();
    expect(screen.queryByText("history.next")).not.toBeInTheDocument();
  });

  it("navigates to next page on Next click", async () => {
    const user = userEvent.setup();
    const manyItems: ScoreHistoryItem[] = Array.from({ length: 15 }, (_, i) => ({
      session_id: `s${i + 1}`,
      scenario_name: `Scenario ${i + 1}`,
      overall_score: 50 + (i % 50),
      passed: true,
      completed_at: `2026-03-${String(20 - i).padStart(2, "0")}T10:00:00Z`,
      dimensions: [
        { dimension: "Knowledge", score: 60, weight: 0.3, improvement_pct: null },
      ],
    }));
    mockScoreHistoryReturn = { data: manyItems, isLoading: false };
    mockSessionsReturn = {
      data: { items: [], total: 0, page: 1, page_size: 100, total_pages: 0 },
      isLoading: false,
    };
    renderSessionHistory();

    const nextBtns = screen.getAllByText("history.next");
    await user.click(nextBtns[0]!);
    expect(screen.getAllByText("2 / 2").length).toBeGreaterThanOrEqual(1);
  });

  it("Previous button is disabled on first page", () => {
    const manyItems: ScoreHistoryItem[] = Array.from({ length: 15 }, (_, i) => ({
      session_id: `s${i + 1}`,
      scenario_name: `Scenario ${i + 1}`,
      overall_score: 70,
      passed: true,
      completed_at: `2026-03-${String(20 - i).padStart(2, "0")}T10:00:00Z`,
      dimensions: [
        { dimension: "Knowledge", score: 70, weight: 0.3, improvement_pct: null },
      ],
    }));
    mockScoreHistoryReturn = { data: manyItems, isLoading: false };
    mockSessionsReturn = {
      data: { items: [], total: 0, page: 1, page_size: 100, total_pages: 0 },
      isLoading: false,
    };
    renderSessionHistory();
    const prevBtns = screen.getAllByText("history.previous");
    expect(prevBtns[0]!).toBeDisabled();
  });

  it("renders score badge with green styling for high scores", () => {
    renderSessionHistory();
    const score85Elements = screen.getAllByText("85");
    const greenStyled = score85Elements.find((el) => el.className.includes("bg-green-100"));
    expect(greenStyled).toBeTruthy();
  });

  it("renders score badge with red styling for low scores", () => {
    renderSessionHistory();
    const score55Elements = screen.getAllByText("55");
    const redStyled = score55Elements.find((el) => el.className.includes("bg-red-100"));
    expect(redStyled).toBeTruthy();
  });

  it("renders TrendingUp icon for positive improvement", () => {
    renderSessionHistory();
    const trendElements = document.querySelectorAll(".text-green-600");
    expect(trendElements.length).toBeGreaterThanOrEqual(1);
  });

  it("renders TrendingDown icon for negative improvement", () => {
    renderSessionHistory();
    const trendElements = document.querySelectorAll(".text-red-600");
    expect(trendElements.length).toBeGreaterThanOrEqual(1);
  });

  it("does not render trend chart when only 1 scored data point", () => {
    mockScoreHistoryReturn = {
      data: [{
        session_id: "s1",
        scenario_name: "Single",
        overall_score: 85,
        passed: true,
        completed_at: "2026-03-20T10:00:00Z",
        dimensions: [
          { dimension: "Knowledge", score: 88, weight: 0.3, improvement_pct: 5 },
        ],
      }],
      isLoading: false,
    };
    renderSessionHistory();
    expect(screen.queryByTestId("line-chart")).not.toBeInTheDocument();
  });

  it("renders created and in_progress sessions", () => {
    mockSessionsReturn = {
      data: {
        items: [mockCreatedSession, mockInProgressSession, mockCompletedSession, mockScoredSession],
        total: 4,
        page: 1,
        page_size: 100,
        total_pages: 1,
      },
      isLoading: false,
    };
    renderSessionHistory();
    // Should show: 2 scored (from history) + 1 completed + 1 created + 1 in_progress = 5 rows
    const rows = document.querySelectorAll("tbody tr");
    expect(rows.length).toBe(5);
    // Check status badges
    expect(screen.getAllByText("history.statusCreated").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("history.statusInProgress").length).toBeGreaterThanOrEqual(1);
  });

  it("renders statusCreated badge for created sessions", () => {
    mockSessionsReturn = {
      data: {
        items: [mockCreatedSession],
        total: 1,
        page: 1,
        page_size: 100,
        total_pages: 1,
      },
      isLoading: false,
    };
    renderSessionHistory();
    expect(screen.getAllByText("history.statusCreated").length).toBeGreaterThanOrEqual(1);
  });

  it("renders statusInProgress badge for in_progress sessions", () => {
    mockSessionsReturn = {
      data: {
        items: [mockInProgressSession],
        total: 1,
        page: 1,
        page_size: 100,
        total_pages: 1,
      },
      isLoading: false,
    };
    renderSessionHistory();
    expect(screen.getAllByText("history.statusInProgress").length).toBeGreaterThanOrEqual(1);
  });

  it("does not show submit scoring button for created/in_progress sessions", () => {
    mockScoreHistoryReturn = { data: [], isLoading: false };
    mockSessionsReturn = {
      data: {
        items: [mockCreatedSession, mockInProgressSession],
        total: 2,
        page: 1,
        page_size: 100,
        total_pages: 1,
      },
      isLoading: false,
    };
    renderSessionHistory();
    expect(screen.queryByText("history.submitScoring")).not.toBeInTheDocument();
  });

  it("filters by status (created only)", async () => {
    mockSessionsReturn = {
      data: {
        items: [mockCreatedSession, mockInProgressSession, mockCompletedSession, mockScoredSession],
        total: 4,
        page: 1,
        page_size: 100,
        total_pages: 1,
      },
      isLoading: false,
    };
    renderSessionHistory();
    const selects = screen.getAllByTestId("hidden-select");
    const statusSelect = selects[0]!;
    await userEvent.setup().selectOptions(statusSelect, "created");
    expect(screen.getAllByText("Dr. New Session").length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText("Dr. Active Practice")).not.toBeInTheDocument();
    expect(screen.queryByText("Dr. Pending Review")).not.toBeInTheDocument();
  });

  it("filters by status (in_progress only)", async () => {
    mockSessionsReturn = {
      data: {
        items: [mockCreatedSession, mockInProgressSession, mockCompletedSession, mockScoredSession],
        total: 4,
        page: 1,
        page_size: 100,
        total_pages: 1,
      },
      isLoading: false,
    };
    renderSessionHistory();
    const selects = screen.getAllByTestId("hidden-select");
    const statusSelect = selects[0]!;
    await userEvent.setup().selectOptions(statusSelect, "in_progress");
    expect(screen.getAllByText("Dr. Active Practice").length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText("Dr. New Session")).not.toBeInTheDocument();
    expect(screen.queryByText("Dr. Pending Review")).not.toBeInTheDocument();
  });

  it("renders completed_at date in table rows", () => {
    renderSessionHistory();
    const rows = document.querySelectorAll("tbody tr");
    // 3 rows: 1 completed + 2 scored
    expect(rows.length).toBe(3);
  });

  it("renders '-' for missing completed_at date", () => {
    mockScoreHistoryReturn = {
      data: [
        {
          session_id: "s1",
          scenario_name: "No Date",
          overall_score: 70,
          passed: true,
          completed_at: null as unknown as string,
          dimensions: [
            { dimension: "Knowledge", score: 70, weight: 0.3, improvement_pct: null },
          ],
        },
        {
          session_id: "s2",
          scenario_name: "Dummy",
          overall_score: 60,
          passed: true,
          completed_at: "2026-03-19T10:00:00Z",
          dimensions: [
            { dimension: "Knowledge", score: 60, weight: 0.3, improvement_pct: null },
          ],
        },
      ],
      isLoading: false,
    };
    mockSessionsReturn = {
      data: { items: [], total: 0, page: 1, page_size: 100, total_pages: 0 },
      isLoading: false,
    };
    renderSessionHistory();
    const dashes = screen.getAllByText("-");
    expect(dashes.length).toBeGreaterThanOrEqual(1);
  });

  it("formats duration correctly", () => {
    renderSessionHistory();
    // mockCompletedSession has duration_seconds: 1800 -> "30:00"
    expect(screen.getAllByText("30:00").length).toBeGreaterThanOrEqual(1);
  });

  it("shows message count for sessions with messages", () => {
    renderSessionHistory();
    // mockCompletedSession has message_count: 12
    const msgElements = screen.getAllByText(/12 history\.messages/);
    expect(msgElements.length).toBeGreaterThanOrEqual(1);
  });

  it("renders Resume button for in_progress sessions", () => {
    mockScoreHistoryReturn = { data: [], isLoading: false };
    mockSessionsReturn = {
      data: {
        items: [mockInProgressSession],
        total: 1,
        page: 1,
        page_size: 100,
        total_pages: 1,
      },
      isLoading: false,
    };
    renderSessionHistory();
    const resumeButtons = screen.getAllByText("history.resume");
    expect(resumeButtons.length).toBeGreaterThanOrEqual(1);
  });

  it("renders Resume button for created sessions", () => {
    mockScoreHistoryReturn = { data: [], isLoading: false };
    mockSessionsReturn = {
      data: {
        items: [mockCreatedSession],
        total: 1,
        page: 1,
        page_size: 100,
        total_pages: 1,
      },
      isLoading: false,
    };
    renderSessionHistory();
    const resumeButtons = screen.getAllByText("history.resume");
    expect(resumeButtons.length).toBeGreaterThanOrEqual(1);
  });

  it("navigates to training session page when Resume is clicked", async () => {
    const user = userEvent.setup();
    mockScoreHistoryReturn = { data: [], isLoading: false };
    mockSessionsReturn = {
      data: {
        items: [mockInProgressSession],
        total: 1,
        page: 1,
        page_size: 100,
        total_pages: 1,
      },
      isLoading: false,
    };
    renderSessionHistory();
    const resumeButtons = screen.getAllByText("history.resume");
    await user.click(resumeButtons[0]!);
    expect(mockNavigate).toHaveBeenCalledWith("/user/training/session?id=s5");
  });

  it("shows started_at date for in_progress sessions without completed_at", () => {
    mockScoreHistoryReturn = { data: [], isLoading: false };
    mockSessionsReturn = {
      data: {
        items: [mockInProgressSession],
        total: 1,
        page: 1,
        page_size: 100,
        total_pages: 1,
      },
      isLoading: false,
    };
    renderSessionHistory();
    // mockInProgressSession has started_at: "2026-03-22T09:00:00Z", completed_at: null
    // Should show the date from started_at, not "-"
    const dateStr = new Date("2026-03-22T09:00:00Z").toLocaleDateString();
    const dateElements = screen.getAllByText(dateStr);
    expect(dateElements.length).toBeGreaterThanOrEqual(1);
  });

  it("shows created_at date for created sessions without started_at or completed_at", () => {
    mockScoreHistoryReturn = { data: [], isLoading: false };
    mockSessionsReturn = {
      data: {
        items: [mockCreatedSession],
        total: 1,
        page: 1,
        page_size: 100,
        total_pages: 1,
      },
      isLoading: false,
    };
    renderSessionHistory();
    // mockCreatedSession has started_at: null, completed_at: null, created_at: "2026-03-22T08:00:00Z"
    // Should show the date from created_at, not "-"
    const dateStr = new Date("2026-03-22T08:00:00Z").toLocaleDateString();
    const dateElements = screen.getAllByText(dateStr);
    expect(dateElements.length).toBeGreaterThanOrEqual(1);
  });
});
