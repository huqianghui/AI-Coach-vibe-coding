import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { CompletionRate } from "../completion-rate";
import { SkillGapHeatmap } from "../skill-gap-heatmap";
import { PerformanceRadar } from "../performance-radar";
import { TrendLineChart } from "../trend-line-chart";
import { BuComparisonBar } from "../bu-comparison-bar";
import type { SkillGapCell, BuStats, DimensionTrendPoint } from "@/types/analytics";

// Mock react-i18next
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: { defaultValue?: string }) => opts?.defaultValue ?? key,
  }),
}));

// Mock recharts - ResponsiveContainer does not render in jsdom
vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => children,
  RadarChart: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="radar-chart">{children}</div>
  ),
  PolarGrid: () => <div data-testid="polar-grid" />,
  PolarAngleAxis: () => <div data-testid="polar-angle-axis" />,
  PolarRadiusAxis: () => <div data-testid="polar-radius-axis" />,
  Radar: ({ name }: { name: string }) => <div data-testid={`radar-${name}`} />,
  Tooltip: () => null,
  BarChart: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="bar-chart">{children}</div>
  ),
  LineChart: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="line-chart">{children}</div>
  ),
  Line: ({ name }: { name?: string }) => <div data-testid={`line-${name ?? "unknown"}`} />,
  XAxis: () => null,
  YAxis: () => null,
  CartesianGrid: () => null,
  Legend: () => null,
  Bar: ({ dataKey }: { dataKey: string }) => <div data-testid={`bar-${dataKey}`} />,
}));

describe("CompletionRate", () => {
  it("renders the rate percentage", () => {
    render(<CompletionRate rate={65} totalUsers={100} activeUsers={65} />);
    expect(screen.getByText("65%")).toBeInTheDocument();
  });

  it("shows active / total users text", () => {
    render(<CompletionRate rate={65} totalUsers={100} activeUsers={65} />);
    expect(screen.getByText(/65 \/ 100/)).toBeInTheDocument();
  });

  it("renders progress bar with correct width", () => {
    const { container } = render(
      <CompletionRate rate={75} totalUsers={200} activeUsers={150} />
    );
    const progressBar = container.querySelector("[style]");
    expect(progressBar).toBeTruthy();
    // The inner div has inline width style
    const innerBar = container.querySelector(".bg-primary");
    expect(innerBar).toHaveStyle({ width: "75%" });
  });

  it("caps progress bar at 100%", () => {
    const { container } = render(
      <CompletionRate rate={120} totalUsers={100} activeUsers={120} />
    );
    const innerBar = container.querySelector(".bg-primary");
    expect(innerBar).toHaveStyle({ width: "100%" });
  });

  it("handles zero rate", () => {
    render(<CompletionRate rate={0} totalUsers={100} activeUsers={0} />);
    expect(screen.getByText("0%")).toBeInTheDocument();
  });
});

describe("SkillGapHeatmap", () => {
  const mockData: SkillGapCell[] = [
    { business_unit: "Oncology", dimension: "Knowledge", avg_score: 85 },
    { business_unit: "Oncology", dimension: "Communication", avg_score: 62 },
    { business_unit: "Hematology", dimension: "Knowledge", avg_score: 55 },
    { business_unit: "Hematology", dimension: "Communication", avg_score: 72 },
  ];

  it("renders table with BU rows", () => {
    render(<SkillGapHeatmap data={mockData} />);
    expect(screen.getByText("Oncology")).toBeInTheDocument();
    expect(screen.getByText("Hematology")).toBeInTheDocument();
  });

  it("renders dimension columns as headers", () => {
    render(<SkillGapHeatmap data={mockData} />);
    expect(screen.getByText("Knowledge")).toBeInTheDocument();
    expect(screen.getByText("Communication")).toBeInTheDocument();
  });

  it("renders score values in cells", () => {
    render(<SkillGapHeatmap data={mockData} />);
    expect(screen.getByText("85.0")).toBeInTheDocument();
    expect(screen.getByText("62.0")).toBeInTheDocument();
    expect(screen.getByText("55.0")).toBeInTheDocument();
    expect(screen.getByText("72.0")).toBeInTheDocument();
  });

  it("applies green color for scores >= 80", () => {
    render(<SkillGapHeatmap data={mockData} />);
    const highScore = screen.getByText("85.0");
    expect(highScore.className).toContain("bg-green");
  });

  it("applies red color for scores < 60", () => {
    render(<SkillGapHeatmap data={mockData} />);
    const lowScore = screen.getByText("55.0");
    expect(lowScore.className).toContain("bg-red");
  });

  it("applies orange color for scores 60-69", () => {
    render(<SkillGapHeatmap data={mockData} />);
    const midScore = screen.getByText("62.0");
    expect(midScore.className).toContain("bg-orange");
  });

  it("applies yellow color for scores 70-79", () => {
    render(<SkillGapHeatmap data={mockData} />);
    const midScore = screen.getByText("72.0");
    expect(midScore.className).toContain("bg-yellow");
  });

  it("shows noData message for empty data", () => {
    render(<SkillGapHeatmap data={[]} />);
    expect(screen.getByText("noData")).toBeInTheDocument();
  });

  it("shows fallback for empty business unit name", () => {
    const dataWithEmptyBu: SkillGapCell[] = [
      { business_unit: "", dimension: "Knowledge", avg_score: 75 },
    ];
    render(<SkillGapHeatmap data={dataWithEmptyBu} />);
    expect(screen.getByText("noData")).toBeInTheDocument();
  });

  it("shows dash for missing score cell", () => {
    // Create data where one BU-dimension combination is missing
    const sparseData: SkillGapCell[] = [
      { business_unit: "BU1", dimension: "DimA", avg_score: 90 },
      { business_unit: "BU2", dimension: "DimB", avg_score: 50 },
    ];
    render(<SkillGapHeatmap data={sparseData} />);
    // BU1 x DimB and BU2 x DimA should show "--"
    const dashes = screen.getAllByText("--");
    expect(dashes.length).toBe(2);
  });
});

describe("PerformanceRadar", () => {
  const currentScores = [
    { dimension: "Knowledge", score: 85 },
    { dimension: "Communication", score: 70 },
    { dimension: "Objection", score: 60 },
  ];

  it("renders the radar chart", () => {
    render(<PerformanceRadar currentScores={currentScores} />);
    expect(screen.getByTestId("radar-chart")).toBeInTheDocument();
  });

  it("renders Current radar series", () => {
    render(<PerformanceRadar currentScores={currentScores} />);
    expect(screen.getByTestId("radar-Current")).toBeInTheDocument();
  });

  it("does not render Previous radar when no previousScores", () => {
    render(<PerformanceRadar currentScores={currentScores} />);
    expect(screen.queryByTestId("radar-Previous")).not.toBeInTheDocument();
  });

  it("renders Previous radar when previousScores provided", () => {
    const previousScores = [
      { dimension: "Knowledge", score: 75 },
      { dimension: "Communication", score: 65 },
      { dimension: "Objection", score: 55 },
    ];
    render(
      <PerformanceRadar
        currentScores={currentScores}
        previousScores={previousScores}
      />
    );
    expect(screen.getByTestId("radar-Previous")).toBeInTheDocument();
  });

  it("does not render Previous radar for empty previousScores array", () => {
    render(
      <PerformanceRadar currentScores={currentScores} previousScores={[]} />
    );
    expect(screen.queryByTestId("radar-Previous")).not.toBeInTheDocument();
  });

  it("renders with custom height", () => {
    const { container } = render(
      <PerformanceRadar currentScores={currentScores} height={400} />
    );
    const wrapper = container.firstChild as HTMLElement;
    expect(wrapper.style.height).toBe("400px");
  });

  it("uses default height of 280", () => {
    const { container } = render(
      <PerformanceRadar currentScores={currentScores} />
    );
    const wrapper = container.firstChild as HTMLElement;
    expect(wrapper.style.height).toBe("280px");
  });

  it("handles previousScores with missing dimension match", () => {
    const previousScores = [
      { dimension: "Knowledge", score: 70 },
      // Communication and Objection missing from previous
    ];
    render(
      <PerformanceRadar
        currentScores={currentScores}
        previousScores={previousScores}
      />
    );
    // Should still render without error; missing prev scores default to 0
    expect(screen.getByTestId("radar-chart")).toBeInTheDocument();
  });
});

describe("TrendLineChart", () => {
  const makeData = (count: number): DimensionTrendPoint[] =>
    Array.from({ length: count }, (_, i) => ({
      session_id: `s${i}`,
      completed_at: new Date(2026, 2, 20 - i).toISOString(),
      scenario_name: `Scenario ${i}`,
      overall_score: 70 + i,
      dimensions: [
        { dimension: "Knowledge", score: 75 + i, weight: 30 },
        { dimension: "Communication", score: 65 + i, weight: 25 },
      ],
    }));

  it("returns null for less than 2 data points", () => {
    const { container } = render(<TrendLineChart data={makeData(1)} />);
    expect(container.firstChild).toBeNull();
  });

  it("returns null for empty data", () => {
    const { container } = render(<TrendLineChart data={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders line chart for 2+ data points", () => {
    render(<TrendLineChart data={makeData(3)} />);
    expect(screen.getByTestId("line-chart")).toBeInTheDocument();
  });

  it("renders with custom height", () => {
    const { container } = render(
      <TrendLineChart data={makeData(3)} height={500} />
    );
    const wrapper = container.firstChild as HTMLElement;
    expect(wrapper.style.height).toBe("500px");
  });

  it("renders overall line", () => {
    render(<TrendLineChart data={makeData(2)} />);
    expect(screen.getByTestId("line-avgScore")).toBeInTheDocument();
  });

  it("renders dimension lines", () => {
    render(<TrendLineChart data={makeData(2)} />);
    expect(screen.getByTestId("line-Knowledge")).toBeInTheDocument();
    expect(screen.getByTestId("line-Communication")).toBeInTheDocument();
  });

  it("handles null completed_at", () => {
    const data: DimensionTrendPoint[] = [
      {
        session_id: "s1",
        completed_at: null,
        scenario_name: "Sc1",
        overall_score: 80,
        dimensions: [{ dimension: "K", score: 80, weight: 50 }],
      },
      {
        session_id: "s2",
        completed_at: null,
        scenario_name: "Sc2",
        overall_score: 75,
        dimensions: [{ dimension: "K", score: 75, weight: 50 }],
      },
    ];
    render(<TrendLineChart data={data} />);
    expect(screen.getByTestId("line-chart")).toBeInTheDocument();
  });
});

describe("BuComparisonBar", () => {
  const mockBuStats: BuStats[] = [
    { business_unit: "Oncology", session_count: 50, avg_score: 78, user_count: 10 },
    { business_unit: "Hematology", session_count: 30, avg_score: 82, user_count: 8 },
  ];

  it("renders bar chart", () => {
    render(<BuComparisonBar data={mockBuStats} />);
    expect(screen.getByTestId("bar-chart")).toBeInTheDocument();
  });

  it("renders session count and avg score bars", () => {
    render(<BuComparisonBar data={mockBuStats} />);
    expect(screen.getByTestId("bar-sessionCount")).toBeInTheDocument();
    expect(screen.getByTestId("bar-avgScore")).toBeInTheDocument();
  });

  it("renders with custom height", () => {
    const { container } = render(
      <BuComparisonBar data={mockBuStats} height={400} />
    );
    const wrapper = container.firstChild as HTMLElement;
    expect(wrapper.style.height).toBe("400px");
  });

  it("uses default height of 300", () => {
    const { container } = render(<BuComparisonBar data={mockBuStats} />);
    const wrapper = container.firstChild as HTMLElement;
    expect(wrapper.style.height).toBe("300px");
  });

  it("handles empty business_unit name with noData fallback", () => {
    const dataWithEmpty: BuStats[] = [
      { business_unit: "", session_count: 10, avg_score: 60, user_count: 2 },
    ];
    render(<BuComparisonBar data={dataWithEmpty} />);
    expect(screen.getByTestId("bar-chart")).toBeInTheDocument();
  });
});
