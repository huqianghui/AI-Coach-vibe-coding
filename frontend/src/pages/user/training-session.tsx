import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui";
import { Button } from "@/components/ui";
import { ScenarioPanel } from "@/components/coach/scenario-panel";
import { ChatArea } from "@/components/coach/chat-area";
import { HintsPanel } from "@/components/coach/hints-panel";
import { useSession, useSessionMessages, useEndSession } from "@/hooks/use-session";
import { useScenario } from "@/hooks/use-scenarios";
import { useSSEStream } from "@/hooks/use-sse";
import type { SessionMessage, KeyMessageStatus, CoachingHint } from "@/types/session";
import type { Scenario } from "@/types/scenario";

export default function TrainingSession() {
  const { t } = useTranslation("coach");
  const { t: tc } = useTranslation("common");
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const sessionId = searchParams.get("id") ?? "";
  const groupRunId = searchParams.get("groupRunId");

  // Fetch session and messages
  const { data: session } = useSession(sessionId || undefined);
  const { data: apiMessages, refetch: refetchMessages } = useSessionMessages(
    sessionId || undefined
  );
  const { data: scenario } = useScenario(session?.scenario_id);
  const endSessionMutation = useEndSession();

  // Local state
  const [messages, setMessages] = useState<SessionMessage[]>([]);
  const [keyMessagesStatus, setKeyMessagesStatus] = useState<KeyMessageStatus[]>([]);
  const [hints, setHints] = useState<CoachingHint[]>([]);
  const [leftCollapsed, setLeftCollapsed] = useState(false);
  const [rightCollapsed, setRightCollapsed] = useState(false);
  const [showEndDialog, setShowEndDialog] = useState(false);

  // Mobile: collapse side panels by default
  const [mobileHintsVisible, setMobileHintsVisible] = useState(false);

  // Sync API messages into local state
  useEffect(() => {
    if (apiMessages && apiMessages.length > 0) {
      setMessages(apiMessages);
    }
  }, [apiMessages]);

  // Initialize key messages from scenario
  useEffect(() => {
    if (scenario && keyMessagesStatus.length === 0) {
      setKeyMessagesStatus(
        scenario.key_messages.map((msg) => ({
          message: msg,
          delivered: false,
          detected_at: null,
        }))
      );
    }
  }, [scenario, keyMessagesStatus.length]);

  // SSE streaming callbacks
  const sseCallbacks = useMemo(
    () => ({
      onText: (_text: string) => {
        // streamedText is updated by the hook itself
      },
      onHint: (hint: CoachingHint) => {
        setHints((prev) => [...prev, hint]);
      },
      onKeyMessages: (status: KeyMessageStatus[]) => {
        setKeyMessagesStatus(status);
      },
      onDone: () => {
        // Refetch messages to get the finalized HCP response
        void refetchMessages();
      },
      onError: (error: string) => {
        console.error("SSE error:", error);
      },
    }),
    [refetchMessages]
  );

  const { sendMessage, isStreaming, streamedText } = useSSEStream(sseCallbacks);

  // Send message handler
  const handleSendMessage = useCallback(
    (text: string) => {
      // Optimistically add user message
      const userMsg: SessionMessage = {
        id: `temp-${Date.now()}`,
        session_id: sessionId,
        role: "user",
        content: text,
        message_index: messages.length,
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, userMsg]);

      // Send via SSE
      void sendMessage(sessionId, text);
    },
    [sessionId, sendMessage]
  );

  // End session handler
  const handleEndSession = useCallback(() => {
    setShowEndDialog(true);
  }, []);

  const confirmEndSession = useCallback(async () => {
    setShowEndDialog(false);
    try {
      await endSessionMutation.mutateAsync(sessionId);
      const scoringUrl = groupRunId
        ? `/user/scoring/${sessionId}?groupRunId=${groupRunId}`
        : `/user/scoring/${sessionId}`;
      navigate(scoringUrl);
    } catch {
      // Error handled by mutation
    }
  }, [groupRunId, sessionId, endSessionMutation, navigate]);

  // Session stats
  const sessionStats = useMemo(() => {
    const userMessages = messages.filter((m) => m.role === "user");
    const wordCount = userMessages.reduce(
      (acc, m) => acc + m.content.split(/\s+/).length,
      0
    );
    const startTime = session?.started_at
      ? new Date(session.started_at).getTime()
      : Date.now();
    const duration = Math.floor((Date.now() - startTime) / 1000);
    return {
      duration,
      wordCount,
      messageCount: messages.length,
    };
  }, [messages, session?.started_at]);

  // Default scenario for when data is still loading
  const defaultScenario: Scenario = {
    id: "",
    name: tc("loading"),
    description: "",
    product: "",
    therapeutic_area: "",
    mode: "f2f",
    difficulty: "medium",
    status: "active",
    hcp_profile_id: "",
    key_messages: [],
    rubric_id: "",
    pass_threshold: 70,
    estimated_duration: 15,
    created_by: "",
    created_at: "",
    updated_at: "",
    skill_id: null,
    skill_version_id: null,
  };

  const currentScenario: Scenario = scenario ?? defaultScenario;
  const hcpInitials =
    currentScenario.hcp_profile?.name
      .split(" ")
      .map((n: string) => n[0])
      .join("")
      .toUpperCase()
      .slice(0, 2) ?? "HC";

  return (
    <div className="flex h-screen w-screen flex-col overflow-hidden bg-background lg:flex-row">
      {/* Left panel — hidden on mobile by default, shown on desktop */}
      <div className="hidden lg:block">
        <ScenarioPanel
          scenario={currentScenario}
          keyMessagesStatus={keyMessagesStatus}
          isCollapsed={leftCollapsed}
          onToggle={() => setLeftCollapsed((prev) => !prev)}
        />
      </div>

      {/* Mobile: compact HCP info bar */}
      <div className="flex items-center gap-3 border-b border-border bg-card px-4 py-2 lg:hidden">
        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary text-xs text-primary-foreground">
          {hcpInitials}
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-foreground">
            {currentScenario.hcp_profile?.name ?? currentScenario.name}
          </p>
          <p className="truncate text-xs text-muted-foreground">
            {currentScenario.hcp_profile?.specialty ?? currentScenario.product}
          </p>
        </div>
      </div>

      {/* Center panel */}
      <div className="min-h-0 flex-1">
        <ChatArea
          sessionId={sessionId}
          messages={messages}
          onSendMessage={handleSendMessage}
          isStreaming={isStreaming}
          streamingText={streamedText}
          onEndSession={handleEndSession}
          sessionStatus={session?.status ?? "created"}
          startedAt={session?.started_at}
          hcpInitials={hcpInitials}
        />
      </div>

      {/* Right panel — hidden on mobile by default, shown on desktop */}
      <div className="hidden lg:block">
        <HintsPanel
          hints={hints}
          keyMessagesStatus={keyMessagesStatus}
          sessionStats={sessionStats}
          isCollapsed={rightCollapsed}
          onToggle={() => setRightCollapsed((prev) => !prev)}
        />
      </div>

      {/* Mobile: collapsible hints panel at bottom */}
      <div className="border-t border-border bg-card lg:hidden">
        <button
          className="flex w-full items-center justify-center gap-2 px-4 py-2 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground"
          onClick={() => setMobileHintsVisible((prev) => !prev)}
        >
          {mobileHintsVisible
            ? t("session.hideHints")
            : t("session.showHints")}
        </button>
        {mobileHintsVisible && (
          <div className="max-h-64 overflow-y-auto border-t border-border px-4 pb-4">
            {hints.length > 0 ? (
              <ul className="space-y-2 pt-2">
                {hints.map((hint, idx) => (
                  <li key={idx} className="text-sm text-muted-foreground">
                    {hint.content}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="py-4 text-center text-sm text-muted-foreground">
                {t("session.noHints")}
              </p>
            )}
          </div>
        )}
      </div>

      {/* End session confirmation dialog */}
      <Dialog open={showEndDialog} onOpenChange={setShowEndDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("session.endSession")}</DialogTitle>
            <DialogDescription>
              {t("session.endConfirm")}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowEndDialog(false)}>
              {tc("cancel")}
            </Button>
            <Button variant="destructive" onClick={confirmEndSession}>
              {t("session.endSession")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
