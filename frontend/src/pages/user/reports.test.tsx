import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import UserReportsPage from "./reports";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { changeLanguage: vi.fn(), language: "en" },
  }),
}));

// Use mutable mock data that can be changed per test
const mockStatsData = {
  data: {
    total_sessions: 24,
    avg_score: 76.5,
    this_week: 3,
    improvement: 4.2 as number | null,
  },
  isLoading: false,
};

const mockTrendsData = {
  data: [
    {
      session_id: "s1",
      completed_at: "2026-03-20",
      scenario_name: "Sc1",
      overall_score: 78,
      dimensions: [
        { dimension: "Product Knowledge", score: 82, weight: 30 },
        { dimension: "Clinical Discussion", score: 75, weight: 25 },
        { dimension: "Objection Handling", score: 68, weight: 20 },
      ],
    },
    {
      session_id: "s2",
      completed_at: "2026-03-10",
      scenario_name: "Sc2",
      overall_score: 72,
      dimensions: [
        { dimension: "Product Knowledge", score: 76, weight: 30 },
        { dimension: "Clinical Discussion", score: 70, weight: 25 },
        { dimension: "Objection Handling", score: 62, weight: 20 },
      ],
    },
  ] as unknown[],
  isLoading: false,
};

const mockRecommendations = {
  data: [
    {
      scenario_id: "s1",
      scenario_name: "Product Launch",
      product: "Zanubrutinib",
      difficulty: "Medium",
      reason: "Practice recommended",
    },
  ] as unknown[],
};

vi.mock("@/hooks/use-analytics", () => ({
  useDashboardStats: () => mockStatsData,
  useDimensionTrends: () => mockTrendsData,
  useRecommendedScenarios: () => mockRecommendations,
  useExportSessionsExcel: () => ({
    mutate: vi.fn(),
    isPending: false,
  }),
}));

vi.mock("@/components/analytics", () => ({
  PerformanceRadar: () => <div data-testid="performance-radar" />,
  TrendLineChart: () => <div data-testid="trend-line-chart" />,
}));

vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="responsive-container">{children}</div>
  ),
  RadarChart: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="radar-chart">{children}</div>
  ),
  PolarGrid: () => <div />,
  PolarAngleAxis: () => <div />,
  PolarRadiusAxis: () => <div />,
  Radar: () => <div />,
  LineChart: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="line-chart">{children}</div>
  ),
  Line: () => <div />,
  XAxis: () => <div />,
  YAxis: () => <div />,
  CartesianGrid: () => <div />,
  Tooltip: () => <div />,
  Legend: () => <div />,
  BarChart: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="bar-chart">{children}</div>
  ),
  Bar: () => <div />,
}));

vi.mock("@/components/ui", () => ({
  Button: ({
    children,
    onClick,
    disabled,
  }: {
    children: React.ReactNode;
    onClick?: () => void;
    variant?: string;
    size?: string;
    disabled?: boolean;
  }) => (
    <button onClick={onClick} disabled={disabled}>
      {children}
    </button>
  ),
  Card: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="card">{children}</div>
  ),
  CardContent: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  CardHeader: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  CardTitle: ({ children }: { children: React.ReactNode }) => (
    <h3>{children}</h3>
  ),
  Skeleton: ({ className }: { className?: string }) => (
    <div data-testid="skeleton" className={`animate-pulse ${className ?? ""}`} />
  ),
}));

function renderReportsPage() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <UserReportsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

// Save original data to restore
const origStats = { ...mockStatsData, data: { ...mockStatsData.data } };
const origTrends = { ...mockTrendsData, data: [...mockTrendsData.data] };
const origRec = { ...mockRecommendations, data: [...mockRecommendations.data] };

beforeEach(() => {
  // Restore defaults
  mockStatsData.data = { ...origStats.data };
  mockStatsData.isLoading = false;
  mockTrendsData.data = [...origTrends.data];
  mockTrendsData.isLoading = false;
  mockRecommendations.data = [...origRec.data];
});

describe("UserReportsPage", () => {
  it("renders the page title", () => {
    renderReportsPage();
    expect(screen.getByText("pageTitle")).toBeInTheDocument();
  });

  it("renders export buttons", () => {
    renderReportsPage();
    expect(screen.getByText("exportPdf")).toBeInTheDocument();
    expect(screen.getByText("exportExcel")).toBeInTheDocument();
  });

  it("prints the complete report from a print-safe root", async () => {
    const print = vi.fn();
    Object.defineProperty(window, "print", { value: print, writable: true });
    const { container } = renderReportsPage();

    expect(container.querySelector(".print-content")).toBeInTheDocument();
    expect(container.querySelectorAll(".print-avoid-break").length).toBeGreaterThan(0);

    await userEvent.setup().click(screen.getByText("exportPdf"));
    expect(print).toHaveBeenCalledOnce();
  });

  it("renders compact summary bar instead of stat cards", () => {
    renderReportsPage();
    // Should find inline stat labels from the compact summary
    expect(screen.getByText("totalSessions:")).toBeInTheDocument();
    expect(screen.getByText("24")).toBeInTheDocument();
    expect(screen.getByText("avgScore:")).toBeInTheDocument();
    expect(screen.getByText("76.5")).toBeInTheDocument();
    expect(screen.getByText("sessionsThisWeek:")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("improvement:")).toBeInTheDocument();
    expect(screen.getByText("+4.2")).toBeInTheDocument();
  });

  it("does not render individual stat card headings", () => {
    renderReportsPage();
    // The old 4-card grid used CardTitle (h3) for each stat
    // Now with compact summary, stat labels are in spans, not headings
    const headings = screen.getAllByRole("heading");
    const statHeadings = headings.filter(
      (h) =>
        h.textContent === "totalSessions" ||
        h.textContent === "avgScore" ||
        h.textContent === "sessionsThisWeek",
    );
    expect(statHeadings).toHaveLength(0);
  });

  it("renders chart sections", () => {
    renderReportsPage();
    expect(screen.getByText("performanceTrend")).toBeInTheDocument();
    expect(screen.getByText("skillGapHeatmap")).toBeInTheDocument();
  });

  it("renders performance trend and skill radar charts", () => {
    renderReportsPage();
    expect(screen.getByTestId("performance-radar")).toBeInTheDocument();
    expect(screen.getByTestId("trend-line-chart")).toBeInTheDocument();
  });

  it("renders recommendations section", () => {
    renderReportsPage();
    expect(screen.getByText("recommendations")).toBeInTheDocument();
    expect(screen.getByText("Product Launch")).toBeInTheDocument();
  });

  it("renders improvement stat with positive prefix", () => {
    renderReportsPage();
    expect(screen.getByText("+4.2")).toBeInTheDocument();
  });
});

describe("UserReportsPage - loading state", () => {
  it("shows loading skeleton when stats are loading", () => {
    mockStatsData.isLoading = true;
    mockTrendsData.isLoading = true;
    const { container } = renderReportsPage();
    expect(container.querySelector(".animate-pulse")).toBeInTheDocument();
  });
});

describe("UserReportsPage - empty state", () => {
  it("shows empty state when total_sessions is 0", () => {
    mockStatsData.data = {
      total_sessions: 0,
      avg_score: 0,
      this_week: 0,
      improvement: null,
    };
    renderReportsPage();
    expect(screen.getByText("noDataBody")).toBeInTheDocument();
  });
});

describe("UserReportsPage - no trends / no radar data", () => {
  it("shows noData message when trends < 2 and no current scores", () => {
    mockStatsData.data = {
      total_sessions: 5,
      avg_score: 70,
      this_week: 1,
      improvement: null,
    };
    mockTrendsData.data = [
      {
        session_id: "s1",
        completed_at: "2026-03-20",
        scenario_name: "Sc",
        overall_score: 70,
        dimensions: [],
      },
    ];
    mockRecommendations.data = [];

    renderReportsPage();
    const noDataMsgs = screen.getAllByText("noData");
    expect(noDataMsgs.length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("noImprovement")).toBeInTheDocument();
  });
});

describe("UserReportsPage - negative improvement", () => {
  it("renders negative improvement without + prefix", () => {
    mockStatsData.data = {
      total_sessions: 10,
      avg_score: 65,
      this_week: 2,
      improvement: -3.5,
    };
    renderReportsPage();
    expect(screen.getByText("-3.5")).toBeInTheDocument();
  });
});
