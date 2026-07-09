import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { MessageSquare, ChevronDown, ChevronUp } from "lucide-react";
import { Badge, Button, ScrollArea } from "@/components/ui";
import { LoadingState } from "@/components/shared";
import { ChatBubble } from "@/components/shared/chat-bubble";
import { ScoreSummary } from "@/components/scoring/score-summary";
import { RadarChart } from "@/components/scoring/radar-chart";
import { DimensionBars } from "@/components/scoring/dimension-bars";
import { FeedbackCard } from "@/components/scoring/feedback-card";
import { ReportSection } from "@/components/scoring/report-section";
import { useSessionScore, useTriggerScoring, useScoreHistory } from "@/hooks/use-scoring";
import { useSessionReport } from "@/hooks/use-reports";
import { useSession, useSessionMessages } from "@/hooks/use-session";
import { useCombinedScore } from "@/hooks/use-combined-score";
import { useRefreshScenarioGroupRunScore } from "@/hooks/use-scenario-groups";
import { VoiceScoreSection } from "@/components/scoring/voice-score-section";

/** Determine badge variant based on score thresholds. */
function getScoreVariant(score: number): "success" | "secondary" | "destructive" {
  if (score >= 80) return "success";
  if (score >= 60) return "secondary";
  return "destructive";
}

export default function ScoringFeedback() {
  const { t } = useTranslation("scoring");
  const navigate = useNavigate();
  const params = useParams();
  const [searchParams] = useSearchParams();
  const sessionId = params.sessionId ?? "";
  const groupRunId = searchParams.get("groupRunId");

  const { data: session } = useSession(sessionId || undefined);
  const { data: messages } = useSessionMessages(sessionId || undefined);
  const { data: score, isLoading: scoreLoading } = useSessionScore(
    sessionId || undefined
  );
  const triggerScoring = useTriggerScoring();
  const refreshGroupRunScore = useRefreshScenarioGroupRunScore();
  const [showTranscript, setShowTranscript] = useState(true);

  // Load full report only when score is available
  const { data: report } = useSessionReport(score ? sessionId : undefined);

  // Load combined score report (includes voice scoring)
  const { data: combinedReport } = useCombinedScore(score ? sessionId : undefined);

  // Load score history for RadarChart overlay
  const { data: history } = useScoreHistory(5);
  const previousScores = useMemo(() => {
    if (!history || !sessionId) return undefined;
    const idx = history.findIndex((h) => h.session_id === sessionId);
    const prev = idx >= 0 && idx < history.length - 1 ? history[idx + 1] : undefined;
    if (!prev) return undefined;
    return prev.dimensions.map((d) => ({ dimension: d.dimension, score: d.score }));
  }, [history, sessionId]);

  // If session is completed but not scored, trigger scoring
  // eslint-disable-next-line react-hooks/exhaustive-deps -- triggerScoring.mutate is stable; including the full object causes re-fire loops
  useEffect(() => {
    if (session?.status === "completed" && !score && !scoreLoading) {
      triggerScoring.mutate(sessionId);
    }
  }, [session?.status, score, scoreLoading, sessionId]);

  useEffect(() => {
    if (groupRunId && score && !refreshGroupRunScore.isPending) {
      refreshGroupRunScore.mutate(groupRunId);
    }
  }, [groupRunId, score?.session_id]);

  // Loading state while scoring
  if (scoreLoading || triggerScoring.isPending || !score) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-medium text-foreground">{t("title")}</h1>
        <LoadingState variant="card" />
        <p className="text-center text-sm text-muted-foreground">
          {t("scoringInProgress")}
        </p>
      </div>
    );
  }

  const contentDetails = score.details.filter((d) => (d.category ?? "content") === "content");
  const displayedOverallScore = combinedReport?.overall_combined_score ?? score.overall_score;
  const currentScores = contentDetails.map((d) => ({
    dimension: d.dimension,
    score: d.score,
  }));

  return (
    <div className="space-y-6">
      {/* Print stylesheet */}
      <style>{`
        @media print {
          nav, .sidebar, header, footer, .action-bar { display: none !important; }
          .space-y-6 { padding: 0 !important; }
          .recharts-wrapper { break-inside: avoid; }
          button { display: none !important; }
        }
      `}</style>

      <h1 className="text-2xl font-medium text-foreground">
        {t("title")}
      </h1>

      {/* Session metadata */}
      {session && (
        <div className="flex flex-wrap items-center gap-4 text-sm text-muted-foreground">
          <span>{t("scenario")}: <strong className="text-foreground">{session.scenario_name || session.scenario_id || "---"}</strong></span>
          <span className="text-border">|</span>
          <span>{t("mode")}: <strong className="text-foreground">{t(`modes.${session.mode || "text"}`)}</strong></span>
          <span className="text-border">|</span>
          <span>{t("date")}: <strong className="text-foreground">{session.created_at ? new Date(session.created_at).toLocaleDateString() : "---"}</strong></span>
        </div>
      )}

      {/* Top section: Circular progress + Score summary */}
      <div className="flex items-center gap-8 rounded-lg border border-border bg-card p-6">
        {/* Circular progress ring */}
        <div className="relative flex-shrink-0">
          <svg width="120" height="120" viewBox="0 0 120 120">
            <circle
              cx="60" cy="60" r="52"
              fill="none"
              className="stroke-muted"
              strokeWidth="8"
            />
            <circle
              cx="60" cy="60" r="52"
              fill="none"
              stroke={displayedOverallScore >= 80 ? "var(--strength)" : displayedOverallScore >= 60 ? "var(--chart-3)" : "var(--destructive)"}
              strokeWidth="8"
              strokeLinecap="round"
              strokeDasharray={`${(displayedOverallScore / 100) * 2 * Math.PI * 52} ${2 * Math.PI * 52}`}
              transform="rotate(-90 60 60)"
            />
            <text x="60" y="55" textAnchor="middle" className="fill-foreground text-2xl font-bold" fontSize="28" fontWeight="700">
              {Math.round(displayedOverallScore)}
            </text>
            <text x="60" y="75" textAnchor="middle" className="fill-muted-foreground" fontSize="12">
              / 100
            </text>
          </svg>
        </div>
        <div className="flex-1">
          <ScoreSummary
            overallScore={Math.round(displayedOverallScore)}
            passed={score.passed}
          />
        </div>
      </div>

      {/* Category Subtotals (D-11, D-12) */}
      {combinedReport && (
        <div className="flex items-center gap-2">
          <Badge variant={getScoreVariant(combinedReport.content_total ?? score.overall_score)}>
            {t("contentScore")}: {Math.round(combinedReport.content_total ?? score.overall_score)}/100
            {combinedReport.content_weight != null && ` (${combinedReport.content_weight}%)`}
          </Badge>
          {combinedReport.voice_total != null ? (
            <Badge variant={getScoreVariant(combinedReport.voice_total)}>
              {t("voiceScore")}: {Math.round(combinedReport.voice_total)}/100
              {combinedReport.voice_weight != null && ` (${combinedReport.voice_weight}%)`}
            </Badge>
          ) : (
            <span className="text-xs text-muted-foreground">
              {combinedReport.audio_url
                ? t("voiceScoringPending")
                : t("textOnlyNote")}
            </span>
          )}
        </div>
      )}

      {/* Two-column layout */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Left: Radar chart + Dimension bars */}
        <div className="space-y-6">
          <div className="rounded-lg border border-border bg-card p-4">
            <RadarChart currentScores={currentScores} previousScores={previousScores} />
          </div>
          <div className="rounded-lg border border-border bg-card p-4">
            <DimensionBars details={contentDetails} />
          </div>
        </div>

        {/* Right: Feedback cards */}
        <ScrollArea className="max-h-[600px]">
          <div className="space-y-4">
            {contentDetails.map((detail) => (
              <FeedbackCard key={detail.dimension} detail={detail} />
            ))}
          </div>
        </ScrollArea>
      </div>

      {/* Voice score section (D-09, D-11) */}
      {combinedReport && (
        <VoiceScoreSection
          dimensions={combinedReport.voice_summary.dimensions}
          overallVoiceScore={combinedReport.voice_summary.overall_voice_score}
          voiceScoreStatus={combinedReport.voice_summary.voice_score_status}
          audioUrl={combinedReport.audio_url ? `/sessions/${sessionId}/audio` : null}
          sessionId={sessionId}
        />
      )}

      {/* Report: Improvement priorities and key messages */}
      {report && (
        <div className="rounded-lg border border-border bg-card p-6">
          <h2 className="mb-4 text-xl font-medium text-foreground">{t("report.improvementTitle")}</h2>
          <ReportSection
            improvements={report.improvements}
            keyMessagesDelivered={report.key_messages_delivered}
            keyMessagesTotal={report.key_messages_total}
          />
        </div>
      )}

      {/* Conversation History */}
      {messages && messages.length > 0 && (
        <div className="rounded-lg border border-border bg-card p-6">
          <button
            type="button"
            className="flex w-full items-center justify-between"
            onClick={() => setShowTranscript((v) => !v)}
          >
            <h2 className="flex items-center gap-2 text-xl font-medium text-foreground">
              <MessageSquare className="size-5" />
              {t("transcript.title")}
              <span className="text-sm font-normal text-muted-foreground">
                ({messages.length} {t("transcript.messageCount")})
              </span>
            </h2>
            {showTranscript ? (
              <ChevronUp className="size-5 text-muted-foreground" />
            ) : (
              <ChevronDown className="size-5 text-muted-foreground" />
            )}
          </button>
          {showTranscript && (
            <div className="mt-4 max-h-[500px] overflow-y-auto">
              <div className="space-y-3">
                {messages.map((msg) => (
                  <ChatBubble
                    key={msg.id}
                    sender={msg.role === "user" ? "mr" : "hcp"}
                    text={msg.content}
                    timestamp={new Date(msg.created_at)}
                    speakerName={
                      msg.role === "user"
                        ? t("transcript.mrLabel")
                        : t("transcript.hcpLabel")
                    }
                  />
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Bottom action bar */}
      <div className="action-bar flex flex-wrap items-center justify-end gap-4 border-t border-border pt-6">
        {groupRunId && (
          <Button
            variant="outline"
            onClick={() => navigate(`/user/training/groups?id=${groupRunId}`)}
            className="transition-colors duration-150"
          >
            返回组合训练
          </Button>
        )}
        <Button
          variant="outline"
          onClick={() => navigate(groupRunId ? `/user/training/groups?id=${groupRunId}` : "/user/training")}
          className="transition-colors duration-150"
        >
          {t("tryAgain")}
        </Button>
        <Button variant="outline" onClick={() => window.print()} className="transition-colors duration-150">
          {t("exportPdf")}
        </Button>
        <Button variant="outline" disabled className="transition-colors duration-150">
          {t("shareWithManager")}
        </Button>
        <Button onClick={() => navigate("/user/dashboard")} className="transition-colors duration-150">
          {t("backToDashboard")}
        </Button>
      </div>
    </div>
  );
}
