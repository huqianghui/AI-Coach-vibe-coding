import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import AdminDashboard from "./dashboard";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, string>) => {
      if (opts?.defaultValue) return opts.defaultValue;
      return key;
    },
    i18n: { changeLanguage: vi.fn(), language: "en" },
  }),
}));

/* ── Configurable analytics hook mock ─────────────────────────────────── */

let mockAnalyticsReturn: {
  data: Record<string, unknown> | undefined;
  isLoading: boolean;
};

vi.mock("@/hooks/use-analytics", () => ({
  useOrgAnalytics: () => mockAnalyticsReturn,
}));

vi.mock("@/components/shared", () => ({
  StatCard: ({ label, value }: { label: string; value: string | number }) => (
    <div data-testid="stat-card">
      {label}: {value}
    </div>
  ),
}));

vi.mock("@/components/analytics", () => ({
  BuComparisonBar: ({ data }: { data: unknown[] }) => (
    <div data-testid="bu-comparison">bu-items:{data.length}</div>
  ),
  SkillGapHeatmap: ({ data }: { data: unknown[] }) => (
    <div data-testid="skill-gap">gap-items:{data.length}</div>
  ),
  CompletionRate: () => <div data-testid="completion-rate" />,
}));

vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
    <div>{children}</div>
  ),
  BarChart: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="score-bar-chart">{children}</div>
  ),
  Bar: () => <div />,
  XAxis: () => <div />,
  YAxis: () => <div />,
  CartesianGrid: () => <div />,
  Tooltip: () => <div />,
}));

function renderDashboard() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <AdminDashboard />
    </QueryClientProvider>,
  );
}

/* ── Full mock data for all dashboard sections ────────────────────────── */

const FULL_ORG_DATA = {
  total_users: 50,
  active_users: 30,
  total_sessions: 200,
  avg_org_score: 75,
  completion_rate: 0.6,
  bu_stats: [
    { bu: "Oncology", avg_score: 80, count: 10 },
    { bu: "Hematology", avg_score: 70, count: 8 },
  ],
  skill_gaps: [
    { skill: "Objection Handling", gap: 0.3 },
    { skill: "Product Knowledge", gap: 0.2 },
  ],
  score_distribution: [
    { range: "0-20", count: 2 },
    { range: "21-40", count: 5 },
    { range: "41-60", count: 12 },
    { range: "61-80", count: 20 },
    { range: "81-100", count: 11 },
  ],
  top_performers: [
    { name: "Alice Zhang", bu: "Oncology", score: 95 },
    { name: "Bob Li", bu: "Hematology", score: 90 },
    { name: "Carol Wang", bu: "Oncology", score: 88 },
  ],
  needs_attention: [
    { name: "Dave Chen", bu: "Neurology", score: 35, sessions: 2 },
    { name: "Eve Liu", bu: "Cardiology", score: 40, sessions: 1 },
  ],
  training_activity: [
    [3, 2, 5, 1, 4, 0, 0],
    [2, 3, 4, 2, 1, 1, 0],
    [0, 0, 0, 0, 0, 0, 0],
    [1, 2, 3, 4, 5, 6, 7],
  ],
};

describe("AdminDashboard", () => {
  beforeEach(() => {
    mockAnalyticsReturn = {
      data: FULL_ORG_DATA,
      isLoading: false,
    };
  });

  /* ---- Loading state ---- */

  it("renders loading skeleton when loading", () => {
    mockAnalyticsReturn = { data: undefined, isLoading: true };
    renderDashboard();
    // Should NOT show the title when loading
    expect(screen.queryByText("adminDashboard")).not.toBeInTheDocument();
  });

  /* ---- Header ---- */

  it("renders the admin dashboard heading", () => {
    renderDashboard();
    expect(screen.getByText("adminDashboard")).toBeInTheDocument();
  });

  it("renders the dashboard description", () => {
    renderDashboard();
    expect(screen.getByText("adminDashboardDesc")).toBeInTheDocument();
  });

  /* ---- Stat cards ---- */

  it("renders four stat cards", () => {
    renderDashboard();
    const statCards = screen.getAllByTestId("stat-card");
    expect(statCards).toHaveLength(4);
  });

  it("renders stat card values", () => {
    renderDashboard();
    expect(screen.getByText("totalUsers: 50")).toBeInTheDocument();
    expect(screen.getByText("activeUsers: 30")).toBeInTheDocument();
    expect(screen.getByText("totalSessions: 200")).toBeInTheDocument();
    expect(screen.getByText("avgOrgScore: 75")).toBeInTheDocument();
  });

  /* ---- Completion rate ---- */

  it("renders completion rate card", () => {
    renderDashboard();
    expect(screen.getByText("completionRate")).toBeInTheDocument();
    expect(screen.getByTestId("completion-rate")).toBeInTheDocument();
  });

  /* ---- BU Comparison ---- */

  it("renders BU comparison with data", () => {
    renderDashboard();
    expect(screen.getByText("buComparison")).toBeInTheDocument();
    expect(screen.getByTestId("bu-comparison")).toHaveTextContent(
      "bu-items:2",
    );
  });

  it("renders noData when bu_stats is empty", () => {
    mockAnalyticsReturn = {
      data: { ...FULL_ORG_DATA, bu_stats: [] },
      isLoading: false,
    };
    renderDashboard();
    // The "noData" fallback text should appear in the BU section
    const noDataElements = screen.getAllByText("noData");
    expect(noDataElements.length).toBeGreaterThanOrEqual(1);
  });

  /* ---- Score Distribution ---- */

  it("renders score distribution chart", () => {
    renderDashboard();
    expect(screen.getByText("scoreDistribution")).toBeInTheDocument();
    expect(screen.getByTestId("score-bar-chart")).toBeInTheDocument();
  });

  /* ---- Skill Gap Heatmap ---- */

  it("renders skill gap heatmap with data", () => {
    renderDashboard();
    expect(screen.getByText("skillGapHeatmap")).toBeInTheDocument();
    expect(screen.getByTestId("skill-gap")).toHaveTextContent("gap-items:2");
  });

  it("renders noData when skill_gaps is empty", () => {
    mockAnalyticsReturn = {
      data: { ...FULL_ORG_DATA, skill_gaps: [] },
      isLoading: false,
    };
    renderDashboard();
    const noDataElements = screen.getAllByText("noData");
    expect(noDataElements.length).toBeGreaterThanOrEqual(1);
  });

  /* ---- Top Performers ---- */

  it("renders top performers section", () => {
    renderDashboard();
    expect(screen.getByText("topPerformers")).toBeInTheDocument();
  });

  it("renders all top performer names", () => {
    renderDashboard();
    expect(screen.getByText("Alice Zhang")).toBeInTheDocument();
    expect(screen.getByText("Bob Li")).toBeInTheDocument();
    expect(screen.getByText("Carol Wang")).toBeInTheDocument();
  });

  it("renders top performer scores", () => {
    renderDashboard();
    expect(screen.getByText("95")).toBeInTheDocument();
    expect(screen.getByText("90")).toBeInTheDocument();
    expect(screen.getByText("88")).toBeInTheDocument();
  });

  it("renders top performer BU info", () => {
    renderDashboard();
    // Alice and Carol are in Oncology, Bob in Hematology
    expect(screen.getAllByText("Oncology")).toHaveLength(2);
    expect(screen.getByText("Hematology")).toBeInTheDocument();
  });

  it("renders ranking badges for top performers", () => {
    renderDashboard();
    // Ranking numbers (1, 2, 3) appear inside styled spans.
    // Since numbers like "1" also appear in heatmap cells, we verify
    // that at least 3 rounded-full ranking badges exist.
    const allText = document.querySelectorAll(".rounded-full");
    expect(allText.length).toBeGreaterThanOrEqual(3);
  });

  /* ---- Needs Attention ---- */

  it("renders needs attention section", () => {
    renderDashboard();
    expect(screen.getByText("needsAttention")).toBeInTheDocument();
  });

  it("renders needs attention user names", () => {
    renderDashboard();
    expect(screen.getByText("Dave Chen")).toBeInTheDocument();
    expect(screen.getByText("Eve Liu")).toBeInTheDocument();
  });

  it("renders needs attention scores", () => {
    renderDashboard();
    expect(screen.getByText("35")).toBeInTheDocument();
    expect(screen.getByText("40")).toBeInTheDocument();
  });

  it("renders needs attention session counts", () => {
    renderDashboard();
    // "Neurology · 2 sessions"
    expect(screen.getByText(/Neurology.*2.*sessions/)).toBeInTheDocument();
    expect(screen.getByText(/Cardiology.*1.*sessions/)).toBeInTheDocument();
  });

  /* ---- Training Activity Heatmap ---- */

  it("renders training activity section", () => {
    renderDashboard();
    expect(screen.getByText("trainingActivity")).toBeInTheDocument();
  });

  it("renders training activity description", () => {
    renderDashboard();
    expect(
      screen.getByText("trainingActivityDesc"),
    ).toBeInTheDocument();
  });

  it("renders day headers", () => {
    renderDashboard();
    expect(screen.getByText("Mon")).toBeInTheDocument();
    expect(screen.getByText("Tue")).toBeInTheDocument();
    expect(screen.getByText("Wed")).toBeInTheDocument();
    expect(screen.getByText("Thu")).toBeInTheDocument();
    expect(screen.getByText("Fri")).toBeInTheDocument();
    expect(screen.getByText("Sat")).toBeInTheDocument();
    expect(screen.getByText("Sun")).toBeInTheDocument();
  });

  it("renders week labels for training activity", () => {
    renderDashboard();
    expect(screen.getByText("week 1")).toBeInTheDocument();
    expect(screen.getByText("week 2")).toBeInTheDocument();
    expect(screen.getByText("week 3")).toBeInTheDocument();
    expect(screen.getByText("week 4")).toBeInTheDocument();
  });

  it("renders non-zero heatmap values", () => {
    renderDashboard();
    // Week 4 has values 1-7, check some are visible
    expect(screen.getByText("7")).toBeInTheDocument();
    expect(screen.getByText("6")).toBeInTheDocument();
  });

  it("renders heatmap cells with title attributes", () => {
    renderDashboard();
    // Week 1, Mon: 3 sessions
    const cell = screen.getByTitle("Mon: 3 sessions");
    expect(cell).toBeInTheDocument();
  });

  /* ---- Empty performers/attention ---- */

  it("renders empty top performers when no data", () => {
    mockAnalyticsReturn = {
      data: { ...FULL_ORG_DATA, top_performers: [], needs_attention: [] },
      isLoading: false,
    };
    renderDashboard();
    expect(screen.getByText("topPerformers")).toBeInTheDocument();
    expect(screen.getByText("needsAttention")).toBeInTheDocument();
    // No user names should appear
    expect(screen.queryByText("Alice Zhang")).not.toBeInTheDocument();
  });

  /* ---- Null safety ---- */

  it("handles undefined orgData gracefully", () => {
    mockAnalyticsReturn = { data: undefined, isLoading: false };
    renderDashboard();
    // Should still render stat cards with 0 values
    expect(screen.getByText("totalUsers: 0")).toBeInTheDocument();
  });
});
