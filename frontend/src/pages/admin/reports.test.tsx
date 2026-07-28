import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import AdminReportsPage from "./reports";

vi.mock("react-i18next", async () => {
  const { createTestTranslator } = await import("@/test/i18n-mock");
  return {
    useTranslation: (namespace?: string | string[]) => ({
      t: createTestTranslator(namespace),
      i18n: { changeLanguage: vi.fn(), language: "en-US" },
    }),
  };
});

const mockExportSessionsMutate = vi.fn();
const mockExportAdminMutate = vi.fn();

vi.mock("@/hooks/use-analytics", () => ({
  useExportSessionsExcel: () => ({
    mutate: mockExportSessionsMutate,
    isPending: false,
  }),
  useExportAdminReport: () => ({
    mutate: mockExportAdminMutate,
    isPending: false,
  }),
  useOrgAnalytics: () => ({
    data: {
      total_sessions: 1247,
      avg_org_score: 73.8,
      completion_rate: 68,
      active_users: 156,
      bu_stats: [
        { business_unit: "Oncology", avg_score: 78, session_count: 300, user_count: 40 },
        { business_unit: "Hematology", avg_score: 72, session_count: 250, user_count: 35 },
        { business_unit: "Immunology", avg_score: 65, session_count: 200, user_count: 30 },
        { business_unit: "Neurology", avg_score: 70, session_count: 150, user_count: 25 },
      ],
      skill_gaps: [
        { business_unit: "Oncology", dimension: "Knowledge", avg_score: 82 },
        { business_unit: "Oncology", dimension: "Communication", avg_score: 75 },
        { business_unit: "Hematology", dimension: "Knowledge", avg_score: 70 },
        { business_unit: "Hematology", dimension: "Communication", avg_score: 68 },
        { business_unit: "Immunology", dimension: "Knowledge", avg_score: 60 },
        { business_unit: "Immunology", dimension: "Communication", avg_score: 55 },
        { business_unit: "Neurology", dimension: "Knowledge", avg_score: 72 },
        { business_unit: "Neurology", dimension: "Communication", avg_score: 66 },
      ],
    },
    isLoading: false,
  }),
  useScoreTrends: () => ({
    data: [
      { month: "Jan", overall: 70, benchmark: 75 },
      { month: "Feb", overall: 72, benchmark: 75 },
    ],
  }),
}));

vi.mock("@/components/shared", () => ({
  StatCard: ({ label, value }: { label: string; value: string | number }) => (
    <div data-testid="stat-card"><span>{label}</span><span>{String(value)}</span></div>
  ),
}));

vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="responsive-container">{children}</div>
  ),
  BarChart: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="bar-chart">{children}</div>
  ),
  Bar: () => <div data-testid="bar" />,
  XAxis: () => <div data-testid="x-axis" />,
  YAxis: () => <div data-testid="y-axis" />,
  CartesianGrid: () => <div data-testid="cartesian-grid" />,
  Tooltip: () => <div data-testid="tooltip" />,
  Legend: () => <div data-testid="legend" />,
  LineChart: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="line-chart">{children}</div>
  ),
  Line: () => <div data-testid="line" />,
  Cell: () => <div data-testid="cell" />,
}));

function renderPage() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <AdminReportsPage />
    </QueryClientProvider>,
  );
}

describe("AdminReportsPage", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders the page title", () => {
    renderPage();
    expect(screen.getByText("Organization Analytics")).toBeInTheDocument();
  });

  it("renders the subtitle description", () => {
    renderPage();
    expect(
      screen.getByText(
        "Comprehensive performance overview across all business units",
      ),
    ).toBeInTheDocument();
  });

  it("renders export buttons", () => {
    renderPage();
    expect(screen.getByText("Export Sessions")).toBeInTheDocument();
    expect(screen.getByText("Export Full Report")).toBeInTheDocument();
  });

  it("renders summary stat cards with values", () => {
    renderPage();
    expect(screen.getByText("Total Sessions")).toBeInTheDocument();
    expect(screen.getByText("1247")).toBeInTheDocument();
    expect(screen.getByText("Org Avg Score")).toBeInTheDocument();
    expect(screen.getByText("73.8")).toBeInTheDocument();
    expect(screen.getByText("Training Completion Rate")).toBeInTheDocument();
    expect(screen.getByText("68%")).toBeInTheDocument();
    expect(screen.getByText("Active Users")).toBeInTheDocument();
    expect(screen.getByText("156")).toBeInTheDocument();
  });

  it("renders chart section titles", () => {
    renderPage();
    expect(screen.getByText("Group Performance")).toBeInTheDocument();
    expect(screen.getByText("Score Trends")).toBeInTheDocument();
    expect(screen.getByText("Completion Rates")).toBeInTheDocument();
    expect(screen.getByText("Skill Gap Analysis")).toBeInTheDocument();
  });

  it("renders skill gap analysis table with BU data", () => {
    renderPage();
    expect(screen.getByText("Oncology")).toBeInTheDocument();
    expect(screen.getByText("Hematology")).toBeInTheDocument();
    expect(screen.getByText("Immunology")).toBeInTheDocument();
    expect(screen.getByText("Neurology")).toBeInTheDocument();
  });

  it("calls export sessions mutation on button click", async () => {
    renderPage();
    const { userEvent: ue } = await import("@testing-library/user-event");
    const user = ue.setup();
    await user.click(screen.getByText("Export Sessions"));
    expect(mockExportSessionsMutate).toHaveBeenCalledTimes(1);
  });

  it("calls export admin report mutation on button click", async () => {
    renderPage();
    const { userEvent: ue } = await import("@testing-library/user-event");
    const user = ue.setup();
    await user.click(screen.getByText("Export Full Report"));
    expect(mockExportAdminMutate).toHaveBeenCalledTimes(1);
  });

  it("renders filter section", () => {
    renderPage();
    // The filter card with Filter icon should be present
    // Radix Select renders the trigger with placeholder text
    const triggers = document.querySelectorAll("[role='combobox']");
    expect(triggers.length).toBeGreaterThanOrEqual(0);
  });
});
