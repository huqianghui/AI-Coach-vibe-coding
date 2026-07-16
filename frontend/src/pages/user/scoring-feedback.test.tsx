import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import ScoringFeedback from "./scoring-feedback";

const mockNavigate = vi.fn();
const mockMutate = vi.fn();
const mockPrint = vi.fn();

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
    useParams: () => ({ sessionId: "session-1" }),
    useSearchParams: () => [new URLSearchParams("id=session-1")],
  };
});

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { changeLanguage: vi.fn(), language: "en" },
  }),
}));

const mockScore = {
  overall_score: 82,
  passed: true,
  details: [
    {
      dimension: "Communication",
      score: 85,
      weight: 30,
      category: "content",
      strengths: ["clear"],
      weaknesses: ["speed"],
      suggestions: ["slow down"],
    },
    {
      dimension: "Product Knowledge",
      score: 78,
      weight: 25,
      category: "content",
      strengths: ["detail"],
      weaknesses: [],
      suggestions: ["study more"],
    },
    {
      dimension: "fluency",
      score: 95,
      weight: 25,
      category: "voice",
      strengths: [],
      weaknesses: [],
      suggestions: [],
    },
  ],
};

let sessionData: unknown = { status: "scored", scenario_id: "sc-1", scenario_name: "Oncology HCP Visit", mode: "text", created_at: "2026-03-20T10:00:00Z" };
let scoreData: unknown = mockScore;
let scoreLoading = false;
let reportData: unknown = undefined;
let historyData: unknown = undefined;

vi.mock("@/hooks/use-scoring", () => ({
  useSessionScore: () => ({ data: scoreData, isLoading: scoreLoading }),
  useTriggerScoring: () => ({ mutate: mockMutate, isPending: false }),
  useScoreHistory: () => ({ data: historyData, isLoading: false }),
}));

let messagesData: unknown = undefined;

vi.mock("@/hooks/use-session", () => ({
  useSession: () => ({ data: sessionData }),
  useSessionMessages: () => ({ data: messagesData, isLoading: false }),
}));

vi.mock("@/hooks/use-reports", () => ({
  useSessionReport: () => ({ data: reportData, isLoading: false }),
}));

let combinedReportData: unknown = undefined;

vi.mock("@/hooks/use-combined-score", () => ({
  useCombinedScore: () => ({ data: combinedReportData, isLoading: false }),
}));

// Mock child scoring components to simplify
vi.mock("@/components/scoring/score-summary", () => ({
  ScoreSummary: (props: { overallScore: number; passed: boolean }) => (
    <div data-testid="score-summary">Score: {props.overallScore} {props.passed ? "PASS" : "FAIL"}</div>
  ),
}));
vi.mock("@/components/scoring/radar-chart", () => ({
  RadarChart: (props: { currentScores: Array<{ dimension: string }>; previousScores?: unknown }) => (
    <div
      data-testid="radar-chart"
      data-has-previous={props.previousScores ? "true" : "false"}
      data-current-dimensions={props.currentScores.map((s) => s.dimension).join(",")}
    />
  ),
}));
vi.mock("@/components/scoring/dimension-bars", () => ({
  DimensionBars: (props: { details: Array<{ dimension: string }> }) => (
    <div data-testid="dimension-bars" data-dimensions={props.details.map((d) => d.dimension).join(",")} />
  ),
}));
vi.mock("@/components/scoring/feedback-card", () => ({
  FeedbackCard: (props: { detail: { dimension: string } }) => (
    <div data-testid="feedback-card">{props.detail.dimension}</div>
  ),
}));
vi.mock("@/components/scoring/report-section", () => ({
  ReportSection: (props: { improvements: string[]; keyMessagesDelivered: number; keyMessagesTotal: number }) => (
    <div data-testid="report-section">
      {props.improvements.join(",")} {props.keyMessagesDelivered}/{props.keyMessagesTotal}
    </div>
  ),
}));
vi.mock("@/components/shared/chat-bubble", () => ({
  ChatBubble: (props: { sender: string; text: string; speakerName?: string }) => (
    <div data-testid="chat-bubble" data-sender={props.sender}>
      <span data-testid="chat-speaker">{props.speakerName}</span>
      <span data-testid="chat-text">{props.text}</span>
    </div>
  ),
}));

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ScoringFeedback />
    </QueryClientProvider>
  );
}

describe("ScoringFeedback", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionData = { status: "scored", scenario_id: "sc-1", scenario_name: "Oncology HCP Visit", mode: "text", created_at: "2026-03-20T10:00:00Z" };
    scoreData = mockScore;
    scoreLoading = false;
    reportData = undefined;
    historyData = undefined;
    messagesData = undefined;
    combinedReportData = undefined;
    // Mock window.print
    Object.defineProperty(window, "print", { value: mockPrint, writable: true });
  });

  it("renders loading state when score is loading", () => {
    scoreLoading = true;
    scoreData = undefined;
    renderPage();
    expect(screen.getByText("scoringInProgress")).toBeInTheDocument();
  });

  it("renders loading state when score is null", () => {
    scoreData = undefined;
    renderPage();
    expect(screen.getByText("scoringInProgress")).toBeInTheDocument();
  });

  it("renders score summary when score is available", () => {
    renderPage();
    expect(screen.getByTestId("score-summary")).toHaveTextContent("Score: 82 PASS");
  });

  it("renders radar chart and dimension bars", () => {
    renderPage();
    expect(screen.getByTestId("radar-chart")).toBeInTheDocument();
    expect(screen.getByTestId("dimension-bars")).toBeInTheDocument();
  });

  it("renders feedback cards for each dimension", () => {
    renderPage();
    const cards = screen.getAllByTestId("feedback-card");
    expect(cards).toHaveLength(2);
    expect(cards[0]).toHaveTextContent("Communication");
    expect(cards[1]).toHaveTextContent("Product Knowledge");
    expect(screen.queryByText("fluency")).not.toBeInTheDocument();
  });

  it("keeps voice dimensions out of the main radar and dimension bars", () => {
    renderPage();
    expect(screen.getByTestId("radar-chart")).toHaveAttribute(
      "data-current-dimensions",
      "Communication,Product Knowledge",
    );
    expect(screen.getByTestId("dimension-bars")).toHaveAttribute(
      "data-dimensions",
      "Communication,Product Knowledge",
    );
  });

  it("uses combined overall score when the combined report is available", () => {
    combinedReportData = {
      overall_combined_score: 88,
      content_total: 82,
      content_weight: 60,
      voice_total: 95,
      voice_weight: 40,
      voice_summary: {
        overall_voice_score: 95,
        voice_score_status: "completed",
        dimensions: [],
      },
      audio_url: "https://example.test/audio.wav",
    };
    renderPage();
    expect(screen.getByTestId("score-summary")).toHaveTextContent("Score: 88 PASS");
  });

  it("renders action buttons", () => {
    renderPage();
    expect(screen.getByText("tryAgain")).toBeInTheDocument();
    expect(screen.getByText("exportPdf")).toBeInTheDocument();
    expect(screen.getByText("backToDashboard")).toBeInTheDocument();
  });

  it("navigates to training on tryAgain click", async () => {
    renderPage();
    await userEvent.setup().click(screen.getByText("tryAgain"));
    expect(mockNavigate).toHaveBeenCalledWith("/user/training");
  });

  it("navigates to dashboard on backToDashboard click", async () => {
    renderPage();
    await userEvent.setup().click(screen.getByText("backToDashboard"));
    expect(mockNavigate).toHaveBeenCalledWith("/user/dashboard");
  });

  it("renders page title", () => {
    renderPage();
    expect(screen.getByText("title")).toBeInTheDocument();
  });

  // NEW TESTS for uncovered branches

  it("triggers scoring when session is completed but not scored", () => {
    sessionData = { status: "completed" };
    scoreData = undefined;
    scoreLoading = false;
    renderPage();
    expect(mockMutate).toHaveBeenCalledWith("session-1");
  });

  it("does not trigger scoring when session is already scored", () => {
    sessionData = { status: "scored" };
    scoreData = mockScore;
    renderPage();
    expect(mockMutate).not.toHaveBeenCalled();
  });

  it("renders session metadata with scenario name and mode", () => {
    renderPage();
    expect(screen.getByText(/Oncology HCP Visit/)).toBeInTheDocument();
    expect(screen.getByText(/modes\.text/)).toBeInTheDocument();
  });

  it("falls back to scenario_id when scenario_name is null", () => {
    sessionData = {
      status: "scored",
      scenario_id: "sc-1",
      scenario_name: null,
      mode: "voice_realtime_model",
      created_at: "2026-03-20T10:00:00Z",
    };
    renderPage();
    expect(screen.getByText(/sc-1/)).toBeInTheDocument();
    expect(screen.getByText(/modes\.voice_realtime_model/)).toBeInTheDocument();
  });

  it("displays digital human mode correctly", () => {
    sessionData = {
      status: "scored",
      scenario_id: "sc-2",
      scenario_name: "Cardiology Discussion",
      mode: "digital_human_realtime_agent",
      created_at: "2026-03-20T10:00:00Z",
    };
    renderPage();
    expect(screen.getByText(/Cardiology Discussion/)).toBeInTheDocument();
    expect(screen.getByText(/modes\.digital_human_realtime_agent/)).toBeInTheDocument();
  });

  it("renders circular progress ring with overall score", () => {
    renderPage();
    // The SVG text element contains "82"
    const scoreTexts = screen.getAllByText("82");
    expect(scoreTexts.length).toBeGreaterThanOrEqual(1);
  });

  it("calls window.print when exportPdf is clicked", async () => {
    renderPage();
    await userEvent.setup().click(screen.getByText("exportPdf"));
    expect(mockPrint).toHaveBeenCalled();
  });

  it("marks feedback and transcript scroll regions for full print expansion", () => {
    messagesData = [
      { id: "msg-1", session_id: "session-1", role: "user", content: "Hello", message_index: 0, created_at: "2026-03-20T10:01:00Z" },
    ];
    const { container } = renderPage();

    expect(container.querySelector(".print-content")).toBeInTheDocument();
    expect(screen.getByTestId("feedback-scroll-area")).toHaveClass("print-expand");
    expect(screen.getByTestId("transcript-scroll-area")).toHaveClass("print-expand");
  });

  it("expands a collapsed transcript before printing", async () => {
    messagesData = [
      { id: "msg-1", session_id: "session-1", role: "user", content: "Hello", message_index: 0, created_at: "2026-03-20T10:01:00Z" },
    ];
    renderPage();
    const user = userEvent.setup();

    await user.click(screen.getByText("transcript.title"));
    expect(screen.queryByTestId("chat-bubble")).not.toBeInTheDocument();

    await user.click(screen.getByText("exportPdf"));
    expect(screen.getByTestId("chat-bubble")).toBeInTheDocument();
    expect(mockPrint).toHaveBeenCalledOnce();
  });

  it("renders report section when report data is available", () => {
    reportData = {
      improvements: ["focus on communication", "handle objections better"],
      key_messages_delivered: 3,
      key_messages_total: 5,
    };
    renderPage();
    expect(screen.getByTestId("report-section")).toBeInTheDocument();
    expect(screen.getByText("report.improvementTitle")).toBeInTheDocument();
  });

  it("does not render report section when report data is undefined", () => {
    reportData = undefined;
    renderPage();
    expect(screen.queryByTestId("report-section")).not.toBeInTheDocument();
  });

  it("passes previousScores to RadarChart when history contains a previous session", () => {
    historyData = [
      {
        session_id: "session-1",
        dimensions: [
          { dimension: "Communication", score: 85 },
          { dimension: "Product Knowledge", score: 78 },
        ],
      },
      {
        session_id: "session-0",
        dimensions: [
          { dimension: "Communication", score: 75 },
          { dimension: "Product Knowledge", score: 70 },
        ],
      },
    ];
    renderPage();
    const radar = screen.getByTestId("radar-chart");
    expect(radar).toHaveAttribute("data-has-previous", "true");
  });

  it("passes undefined previousScores when current session is the only one in history", () => {
    historyData = [
      {
        session_id: "session-1",
        dimensions: [
          { dimension: "Communication", score: 85 },
        ],
      },
    ];
    renderPage();
    const radar = screen.getByTestId("radar-chart");
    expect(radar).toHaveAttribute("data-has-previous", "false");
  });

  it("passes undefined previousScores when history is empty", () => {
    historyData = undefined;
    renderPage();
    const radar = screen.getByTestId("radar-chart");
    expect(radar).toHaveAttribute("data-has-previous", "false");
  });

  it("renders shareWithManager button as disabled", () => {
    renderPage();
    const shareBtn = screen.getByText("shareWithManager");
    expect(shareBtn.closest("button")).toBeDisabled();
  });

  // Conversation history tests
  it("renders conversation history when messages are available", () => {
    messagesData = [
      { id: "msg-1", session_id: "session-1", role: "user", content: "Hello doctor", message_index: 0, created_at: "2026-03-20T10:01:00Z" },
      { id: "msg-2", session_id: "session-1", role: "assistant", content: "Hello, how can I help?", message_index: 1, created_at: "2026-03-20T10:01:30Z" },
    ];
    renderPage();
    expect(screen.getByText("transcript.title")).toBeInTheDocument();
    expect(screen.getByText("(2 transcript.messageCount)")).toBeInTheDocument();
    const bubbles = screen.getAllByTestId("chat-bubble");
    expect(bubbles).toHaveLength(2);
    expect(bubbles[0]).toHaveAttribute("data-sender", "mr");
    expect(bubbles[1]).toHaveAttribute("data-sender", "hcp");
  });

  it("does not render conversation history section when messages are empty", () => {
    messagesData = [];
    renderPage();
    expect(screen.queryByText("transcript.title")).not.toBeInTheDocument();
  });

  it("does not render conversation history section when messages are undefined", () => {
    messagesData = undefined;
    renderPage();
    expect(screen.queryByText("transcript.title")).not.toBeInTheDocument();
  });

  it("displays correct speaker labels in chat bubbles", () => {
    messagesData = [
      { id: "msg-1", session_id: "session-1", role: "user", content: "Test message", message_index: 0, created_at: "2026-03-20T10:01:00Z" },
      { id: "msg-2", session_id: "session-1", role: "assistant", content: "Response", message_index: 1, speaker_id: "hcp-1", speaker_name: "Dr. Chen", created_at: "2026-03-20T10:01:30Z" },
    ];
    renderPage();
    const speakers = screen.getAllByTestId("chat-speaker");
    expect(speakers[0]).toHaveTextContent("transcript.mrLabel");
    expect(speakers[1]).toHaveTextContent("Dr. Chen");
  });

  it("falls back to the generic HCP label when speaker attribution is unavailable", () => {
    messagesData = [
      { id: "msg-1", session_id: "session-1", role: "assistant", content: "Response", message_index: 0, speaker_name: "", created_at: "2026-03-20T10:01:30Z" },
    ];
    renderPage();
    expect(screen.getByTestId("chat-speaker")).toHaveTextContent("transcript.hcpLabel");
  });

  it("toggles conversation history visibility when header is clicked", async () => {
    messagesData = [
      { id: "msg-1", session_id: "session-1", role: "user", content: "Hello", message_index: 0, created_at: "2026-03-20T10:01:00Z" },
    ];
    renderPage();
    // Initially visible
    expect(screen.getByTestId("chat-bubble")).toBeInTheDocument();
    // Click to collapse
    await userEvent.setup().click(screen.getByText("transcript.title"));
    expect(screen.queryByTestId("chat-bubble")).not.toBeInTheDocument();
    // Click to expand again
    await userEvent.setup().click(screen.getByText("transcript.title"));
    expect(screen.getByTestId("chat-bubble")).toBeInTheDocument();
  });
});
