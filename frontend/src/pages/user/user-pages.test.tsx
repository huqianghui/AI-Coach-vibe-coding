import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";
import TrainingPage from "./training";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en-US" },
  }),
}));

vi.mock("@/contexts/config-context", () => ({
  useConfig: () => ({
    avatar_enabled: false,
    voice_enabled: false,
    realtime_voice_enabled: false,
    conference_enabled: false,
    voice_live_enabled: false,
    default_voice_mode: "text_only",
    region: "global",
  }),
}));

vi.mock("@/hooks/use-scenarios", () => ({
  useActiveScenarios: () => ({
    data: [],
    isLoading: false,
  }),
  useScenario: () => ({ data: undefined }),
}));

vi.mock("@/hooks/use-session", () => ({
  useCreateSession: () => ({ mutateAsync: vi.fn() }),
  useSession: () => ({ data: undefined }),
  useSessionMessages: () => ({ data: [], refetch: vi.fn() }),
  useEndSession: () => ({ mutateAsync: vi.fn() }),
}));

vi.mock("@/contexts/config-context", () => ({
  useConfig: () => ({
    avatar_enabled: false,
    voice_enabled: false,
    realtime_voice_enabled: false,
    conference_enabled: false,
    voice_live_enabled: false,
    default_voice_mode: "text_only",
    region: "global",
  }),
}));

vi.mock("@/hooks/use-scoring", () => ({
  useSessionScore: () => ({
    data: undefined,
    isLoading: true,
  }),
  useTriggerScoring: () => ({
    mutate: vi.fn(),
    isPending: false,
  }),
  useScoreHistory: () => ({ data: undefined, isLoading: false }),
}));

vi.mock("@/hooks/use-reports", () => ({
  useSessionReport: () => ({ data: undefined, isLoading: false }),
}));

vi.mock("@/hooks/use-sse", () => ({
  useSSEStream: () => ({
    sendMessage: vi.fn(),
    isStreaming: false,
    streamedText: "",
    error: null,
    abort: vi.fn(),
  }),
}));

// Mock recharts for scoring-feedback page
vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: { children: ReactNode }) => (
    <div>{children}</div>
  ),
  RadarChart: ({ children }: { children: ReactNode }) => (
    <div>{children}</div>
  ),
  PolarGrid: () => <div />,
  PolarAngleAxis: () => <div />,
  PolarRadiusAxis: () => <div />,
  Radar: () => <div />,
}));

function wrapper({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe("TrainingPage (ScenarioSelection)", () => {
  it("renders the scenario selection page title", async () => {
    render(<TrainingPage />, { wrapper });

    expect(
      screen.getByText("scenarioSelection.title"),
    ).toBeInTheDocument();
  });

  it("renders F2F and Conference tabs", async () => {
    render(<TrainingPage />, { wrapper });

    expect(screen.getByText("scenarioSelection.tabF2F")).toBeInTheDocument();
    expect(
      screen.getByText("scenarioSelection.tabConference"),
    ).toBeInTheDocument();
  });

  it("shows empty state when no scenarios", async () => {
    render(<TrainingPage />, { wrapper });

    expect(
      screen.getByText("scenarioSelection.emptyTitle"),
    ).toBeInTheDocument();
  });
});

describe("TrainingSession page", () => {
  it("renders the training session layout", async () => {
    const { default: TrainingSession } = await import("./training-session");
    render(<TrainingSession />, { wrapper });

    // Should render without crashing - the session panel, chat area, and hints panel
    // The page should be in the document
    expect(document.body).toBeInTheDocument();
  });
});

describe("ScoringFeedback page", () => {
  it("renders loading state when score is not yet available", async () => {
    const { default: ScoringFeedback } = await import("./scoring-feedback");
    render(<ScoringFeedback />, { wrapper });

    // Shows loading/scoring in progress text
    expect(screen.getByText("scoringInProgress")).toBeInTheDocument();
  });
});
