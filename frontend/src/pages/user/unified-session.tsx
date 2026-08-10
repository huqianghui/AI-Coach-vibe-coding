import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Loader2, AlertTriangle } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Button,
} from "@/components/ui";
import { useSession, useEndSession } from "@/hooks/use-session";
import { useScenario } from "@/hooks/use-scenarios";
import { useVoiceLive } from "@/hooks/use-voice-live";
import { useAvatarStream } from "@/hooks/use-avatar-stream";
import { useAudioHandler } from "@/hooks/use-audio-handler";
import { useAudioPlayer } from "@/hooks/use-audio-player";
import { useVoiceSessionLifecycle } from "@/hooks/use-voice-session-lifecycle";
import { useSessionRecorder } from "@/hooks/use-session-recorder";
import { streamSessionMessage } from "@/api/sessions";
import { persistTranscriptMessage } from "@/api/voice-live";
import { VoiceSessionHeader } from "@/components/voice/voice-session-header";
import { AvatarView } from "@/components/voice/avatar-view";
import { VoiceTranscript } from "@/components/voice/voice-transcript";
import { VoiceControls } from "@/components/voice/voice-controls";
import { ScenarioPanel } from "@/components/coach/scenario-panel";
import { HintsPanel } from "@/components/coach/hints-panel";
import { createVoiceLogger } from "@/lib/voice-logger";
import type {
  SessionMode,
  TranscriptSegment,
} from "@/types/voice-live";
import type {
  CoachingHint,
  KeyMessageStatus,
  SessionStreamError,
  SessionTurnState,
  SessionTurnStatus,
} from "@/types/session";
import type { Scenario } from "@/types/scenario";

function normalizeSessionMode(mode: string | undefined): SessionMode {
  if (
    mode === "text" ||
    mode === "voice_realtime_model" ||
    mode === "digital_human_realtime_model" ||
    mode === "voice_realtime_agent" ||
    mode === "digital_human_realtime_agent"
  ) {
    return mode;
  }
  return "voice_realtime_model";
}

function isDigitalHumanMode(mode: SessionMode): boolean {
  return mode.startsWith("digital_human_");
}

/**
 * Unified training session page — reuses voice-session components with
 * additional text input and coaching panels for MR training.
 *
 * Layout: ScenarioPanel (left) | Avatar+Controls (center) | Transcript+Hints (right)
 * Matches the admin HCP preview page while adding training context.
 */
export default function UnifiedSession() {
  const log = createVoiceLogger("UnifiedSession");
  const { t } = useTranslation("session");
  const { t: tv } = useTranslation("voice");
  const { t: tc } = useTranslation("common");
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const sessionId = searchParams.get("id") ?? "";

  // Data fetching
  const {
    data: session,
    isLoading: sessionLoading,
    isError: sessionError,
  } = useSession(sessionId || undefined);
  const {
    data: scenario,
    isLoading: scenarioLoading,
    isError: scenarioError,
  } = useScenario(session?.scenario_id);

  // State
  const [currentMode, setCurrentMode] = useState<SessionMode>("voice_realtime_model");
  const initialModeRef = useRef<SessionMode>("voice_realtime_model");
  const [transcripts, setTranscripts] = useState<TranscriptSegment[]>([]);
  const [showKeyboard, setShowKeyboard] = useState(true); // Text input always visible for MR
  const [showEndDialog, setShowEndDialog] = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);
  const [sessionStarted, setSessionStarted] = useState(false);
  const [keyMessagesStatus, setKeyMessagesStatus] = useState<KeyMessageStatus[]>([]);
  const [hints, setHints] = useState<CoachingHint[]>([]);
  const [startedAt] = useState<string>(new Date().toISOString());
  const [scenarioPanelCollapsed, setScenarioPanelCollapsed] = useState(false);
  const [hintsPanelCollapsed, setHintsPanelCollapsed] = useState(false);
  const [turnStatus, setTurnStatus] = useState<SessionTurnStatus>("idle");
  const [turnError, setTurnError] = useState<string | null>(null);
  const [pendingMessage, setPendingMessage] = useState<string | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const assistantSegmentIdRef = useRef<string | null>(null);
  const assistantTextRef = useRef("");
  const turnAbortRef = useRef<AbortController | null>(null);

  // Track pending transcript flush promises
  const pendingFlushesRef = useRef<Promise<void>[]>([]);

  // Session stats
  const sessionStats = useMemo(() => {
    const userTranscripts = transcripts.filter((t) => t.role === "user" && t.isFinal);
    const wordCount = userTranscripts.reduce(
      (acc, t) => acc + t.content.split(/\s+/).filter(Boolean).length,
      0,
    );
    const duration = sessionStarted
      ? Math.floor((Date.now() - new Date(startedAt).getTime()) / 1000)
      : 0;
    return { duration, wordCount, messageCount: transcripts.filter((t) => t.isFinal).length };
  }, [transcripts, sessionStarted, startedAt]);

  // Session mode is server-owned. Until a mode-update API exists, the UI must
  // not advertise client-only transitions that the backend cannot authorize.
  const availableModes = useMemo((): SessionMode[] => {
    return [normalizeSessionMode(session?.mode)];
  }, [session?.mode]);

  // Hooks
  const endSessionMutation = useEndSession();

  // Transcript handler (shared between voice and text)
  const handleTranscript = useCallback(
    (segment: TranscriptSegment) => {
      setTranscripts((prev) => {
        const existing = prev.findIndex((s) => s.id === segment.id);
        if (existing >= 0) {
          const updated = [...prev];
          const existingSegment = updated[existing]!;
          if (!segment.isFinal && !existingSegment.isFinal) {
            updated[existing] = {
              ...segment,
              content: existingSegment.content + segment.content,
            };
          } else {
            updated[existing] = segment;
          }
          return updated;
        }
        return [...prev, segment];
      });

      // Persist final transcripts to backend
      if (segment.isFinal) {
        const flushPromise = persistTranscriptMessage(
          sessionId,
          segment.role,
          segment.content,
        );
        pendingFlushesRef.current.push(flushPromise);
        flushPromise.finally(() => {
          pendingFlushesRef.current = pendingFlushesRef.current.filter(
            (p) => p !== flushPromise,
          );
        });
      }
    },
    [sessionId],
  );

  // Voice hooks
  const avatarStream = useAvatarStream(videoRef);
  const audioHandler = useAudioHandler();
  const audioPlayer = useAudioPlayer();
  const sessionRecorder = useSessionRecorder();

  const voiceLive = useVoiceLive({
    language: "zh-CN",
    systemPrompt: "",
    onTranscript: handleTranscript,
    onAudioDelta: audioPlayer.playAudio,
    onConnectionStateChange: (state) => {
      if (state === "error") {
        toast.error(tv("error.connectionFailed"));
      }
    },
    onError: (error) => {
      log.error("Voice Live error: %o", error);
    },
  });

  const { startSession: startVoiceSession, stopSession: stopVoiceSession } =
    useVoiceSessionLifecycle({
      voiceLive,
      avatarStream,
      audioHandler,
      audioPlayer,
    });

  const sseCallbacks = useMemo(
    () => ({
      onState: (state: SessionTurnState) => {
        if (state.code === "SESSION_TURN_RECONCILING") {
          setTurnStatus("reconciling");
        } else if (state.code === "SESSION_TURN_FAILED") {
          setTurnStatus("failed_terminal");
        } else if (state.code === "SESSION_TURN_ACCEPTED") {
          setTurnStatus("accepted");
        } else {
          setTurnStatus("in_progress");
        }
      },
      onText: (chunk: string) => {
        assistantTextRef.current += chunk;
        const segmentId = assistantSegmentIdRef.current ?? `sse-assistant-${Date.now()}`;
        assistantSegmentIdRef.current = segmentId;
        setTranscripts((prev) => {
          const existing = prev.findIndex((segment) => segment.id === segmentId);
          if (existing >= 0) {
            const updated = [...prev];
            updated[existing] = {
              ...updated[existing]!,
              content: assistantTextRef.current,
              isFinal: false,
            };
            return updated;
          }
          return [
            ...prev,
            {
              id: segmentId,
              role: "assistant" as const,
              content: assistantTextRef.current,
              isFinal: false,
              timestamp: Date.now(),
            },
          ];
        });
      },
      onHint: (hint: CoachingHint) => {
        setHints((prev) => [...prev, hint]);
      },
      onKeyMessages: (status: KeyMessageStatus[]) => {
        setKeyMessagesStatus(status);
      },
      onDone: () => {
        const segmentId = assistantSegmentIdRef.current;
        setTranscripts((prev) => {
          if (!segmentId) return prev;
          return prev.map((segment) =>
            segment.id === segmentId ? { ...segment, isFinal: true } : segment,
          );
        });
        setTurnStatus("succeeded");
        setPendingMessage(null);
      },
      onError: (error: SessionStreamError) => {
        setTurnStatus("failed_terminal");
        setTurnError(error.message);
        toast.error(error.message);
      },
    }),
    [],
  );
  const isTurnBusy = ["accepted", "in_progress", "reconciling"].includes(turnStatus);

  // Initialize display mode from the persisted session mode.
  useEffect(() => {
    if (!session?.mode || sessionStarted) return;
    const mode = normalizeSessionMode(session.mode);
    setCurrentMode(mode);
    initialModeRef.current = mode;
  }, [session?.mode, sessionStarted]);

  // Initialize key messages from scenario
  useEffect(() => {
    if (scenario && keyMessagesStatus.length === 0) {
      setKeyMessagesStatus(
        scenario.key_messages.map((msg) => ({
          message: msg,
          delivered: false,
          detected_at: null,
        })),
      );
    }
  }, [scenario, keyMessagesStatus.length]);

  // Ref to track stopVoiceSession for unmount cleanup
  const stopVoiceSessionRef = useRef(stopVoiceSession);
  stopVoiceSessionRef.current = stopVoiceSession;

  // Start session handler — initiates voice for voice/avatar modes, skips for text mode
  const handleStartSession = useCallback(async () => {
    setIsConnecting(true);
    setTurnError(null);
    log.info("handleStartSession: mode=%s scenarioId=%s", session?.mode, session?.scenario_id);

    // Text mode: skip voice connection entirely.
    if (session?.mode === "text") {
      setSessionStarted(true);
      setCurrentMode("text");
      initialModeRef.current = "text";
      setIsConnecting(false);
      return;
    }

    try {
      // The browser supplies only the owned Session identifier. The backend
      // resolves the exact Agent pin, HCP Voice configuration, and modality.
      const result = await startVoiceSession({
        sessionId,
        onMicDenied: () => toast.error(tv("error.micDenied")),
        onAudioWorkletFailed: () => toast.error(tv("error.audioWorkletFailed")),
        onAvatarFailed: () => toast.error(tv("error.avatarFailed")),
        onConnectionFailed: (error) => {
          log.error("Session Voice Live connection failed: %o", error);
          toast.error(tv("error.connectionFailed"));
        },
      });

      if (!result) return;

      const usesAgent = result.mode === "agent";
      const requestedAvatar = isDigitalHumanMode(normalizeSessionMode(session?.mode));
      const resolvedMode: SessionMode = requestedAvatar && result.avatarEnabled
        ? usesAgent
          ? "digital_human_realtime_agent"
          : "digital_human_realtime_model"
        : usesAgent
          ? "voice_realtime_agent"
          : "voice_realtime_model";
      setCurrentMode(resolvedMode);
      initialModeRef.current = resolvedMode;
      setSessionStarted(true);

      const micStream = audioHandler.streamRef.current;
      if (micStream) {
        await sessionRecorder.startRecording(micStream);
      }
    } finally {
      setIsConnecting(false);
    }
  }, [
    session?.mode,
    session?.scenario_id,
    sessionId,
    startVoiceSession,
    audioHandler.streamRef,
    sessionRecorder,
    tv,
    log,
  ]);

  // Auto-start for text mode — no voice connection needed, show avatar immediately
  useEffect(() => {
    if (session?.mode === "text" && !sessionStarted) {
      setSessionStarted(true);
      setCurrentMode("text");
      initialModeRef.current = "text";
    }
  }, [session?.mode, sessionStarted]);

  // Cleanup on unmount — disconnect voice and avatar
  useEffect(() => {
    return () => {
      void stopVoiceSessionRef.current();
    };
  }, []);

  // In-session mode switch handler
  const handleModeSwitch = useCallback(
    async (newMode: SessionMode) => {
      if (newMode === currentMode) return;
      log.warn("Rejected unsupported client-side mode switch: %s -> %s", currentMode, newMode);
      toast.error("训练模式由服务端会话固定；当前暂不支持会话内切换。 ");
    },
    [currentMode, log],
  );

  // End session handler
  const handleEndSession = useCallback(() => {
    setShowEndDialog(true);
  }, []);

  const confirmEndSession = useCallback(async () => {
    setShowEndDialog(false);
    // Flush all pending transcript writes
    await Promise.all(pendingFlushesRef.current);

    // Stop recording and upload audio for voice scoring via CU
    if (sessionRecorder.isRecording) {
      toast.info(tv("recording.uploading"));
      const uploadResult = await sessionRecorder.stopAndUpload(sessionId);
      if (uploadResult.success) {
        log.info("Session audio uploaded successfully");
      } else {
        log.warn("Session audio upload failed: %s", uploadResult.error);
        toast.warning(tv("recording.uploadFailed"));
      }
    }

    // Disconnect voice and avatar (ignore errors — voice may not be connected)
    try {
      await stopVoiceSession();
    } catch {
      // Voice cleanup failure is non-fatal
    }
    // Call endSession API
    try {
      await endSessionMutation.mutateAsync(sessionId);
      navigate("/user/history");
    } catch {
      toast.error(t("endSessionFailed"));
      navigate("/user/training");
    }
  }, [sessionId, sessionRecorder, stopVoiceSession, endSessionMutation, navigate, t, tv, log]);

  const sendTextTurn = useCallback(
    async (text: string, resume: boolean) => {
      if (isTurnBusy) return;
      if (!resume) {
        setTranscripts((prev) => [
          ...prev,
          {
            id: `user-text-${Date.now()}`,
            role: "user",
            content: text,
            isFinal: true,
            timestamp: Date.now(),
          },
        ]);
        assistantSegmentIdRef.current = `sse-assistant-${Date.now()}`;
        assistantTextRef.current = "";
      }
      setPendingMessage(text);
      setTurnError(null);
      setTurnStatus("accepted");
      const controller = new AbortController();
      turnAbortRef.current = controller;
      try {
        await streamSessionMessage(sessionId, text, sseCallbacks, controller.signal);
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setTurnStatus("disconnected");
        setTurnError(tv("turn.disconnected"));
      } finally {
        if (turnAbortRef.current === controller) turnAbortRef.current = null;
      }
    },
    [isTurnBusy, sessionId, sseCallbacks, tv],
  );

  const [inputText, setInputText] = useState("");

  const handleKeyboardSubmit = useCallback(() => {
    if (!inputText.trim() || isTurnBusy || session?.mode !== "text") return;
    void sendTextTurn(inputText.trim(), false);
    setInputText("");
  }, [inputText, isTurnBusy, sendTextTurn, session?.mode]);

  // Error state
  if (sessionError || scenarioError) {
    return (
      <div className="flex h-screen w-screen items-center justify-center bg-background">
        <div className="flex flex-col items-center gap-4">
          <AlertTriangle className="h-10 w-10 text-destructive" />
          <p className="text-sm text-muted-foreground">{t("error.loadFailed")}</p>
          <Button variant="outline" onClick={() => navigate("/user/training")}>
            {tc("back")}
          </Button>
        </div>
      </div>
    );
  }

  // Loading state
  if (sessionLoading || !session || (session.scenario_id && scenarioLoading)) {
    return (
      <div className="flex h-screen w-screen items-center justify-center bg-background">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
          <p className="text-sm text-muted-foreground">{t("loading")}</p>
        </div>
      </div>
    );
  }

  const hcpName = scenario?.hcp_profile?.name ?? "HCP";
  const defaultScenario: Scenario = {
    id: "",
    name: tc("loading"),
    description: "",
    tags: [],
    mode: "f2f",
    difficulty: "medium",
    status: "active",
    hcp_profile_id: "",
    key_messages: [],
    rubric_id: "",
    skill_id: "",
    skill_version_id: null,
    pass_threshold: 70,
    created_by: "",
    created_at: "",
    updated_at: "",
  };
  const currentScenario = scenario ?? defaultScenario;

  return (
    <div className="flex h-screen w-screen flex-col overflow-hidden bg-slate-100">
      {/* Header — reuses VoiceSessionHeader with mode switching */}
      <VoiceSessionHeader
        scenarioTitle={currentScenario.name}
        currentMode={currentMode}
        initialMode={initialModeRef.current}
        connectionState={voiceLive.connectionState}
        onEndSession={handleEndSession}
        startedAt={startedAt}
        isFullScreen={false}
        onModeChange={handleModeSwitch}
        availableModes={availableModes}
      />

      {/* 3-panel layout: ScenarioPanel | Avatar+Controls | Transcript+Hints */}
      <div className="flex min-h-0 flex-1 overflow-hidden">
        {/* Left: Scenario/Training context panel */}
        <ScenarioPanel
          scenario={currentScenario}
          keyMessagesStatus={keyMessagesStatus}
          isCollapsed={scenarioPanelCollapsed}
          onToggle={() => setScenarioPanelCollapsed((prev) => !prev)}
        />

        {/* Center: Avatar + Voice Controls */}
        <div className="relative flex min-w-0 flex-1 flex-col overflow-hidden bg-slate-900">
          <AvatarView
            videoRef={videoRef}
            isAvatarConnected={avatarStream.isConnected}
            isSessionActive={sessionStarted && voiceLive.connectionState === "connected"}
            audioState={voiceLive.audioState}
            isConnecting={isConnecting}
            isDigitalHumanMode={isDigitalHumanMode(currentMode)}
            hcpName={hcpName}
            isFullScreen={false}
            avatarCharacter={
              isDigitalHumanMode(currentMode)
                ? scenario?.hcp_profile?.voice_live_instance?.avatar_character
                : undefined
            }
            avatarStyle={
              isDigitalHumanMode(currentMode)
                ? scenario?.hcp_profile?.voice_live_instance?.avatar_style
                : undefined
            }
            className="flex-1"
          />

          {/* Start button overlay — shown before session begins */}
          {!sessionStarted && !isConnecting && (
            <div
              className="absolute inset-0 z-30 flex flex-col items-center justify-center"
              data-testid="start-overlay"
            >
              <button
                type="button"
                onClick={handleStartSession}
                className="group flex items-center gap-3 rounded-full px-8 py-4 bg-white/15 text-white shadow-lg backdrop-blur-md transition-all duration-200 hover:scale-105 hover:bg-white/25 hover:shadow-xl focus:outline-none focus:ring-2 focus:ring-white/50"
                aria-label={tv("startButton")}
                data-testid="start-session-btn"
              >
                <Loader2 className="h-6 w-6 text-white transition-transform group-hover:scale-110" />
                <span className="text-lg font-semibold">{tv("startButton")}</span>
              </button>
            </div>
          )}

          {/* Voice controls at bottom of center panel */}
          <VoiceControls
            audioState={voiceLive.audioState}
            connectionState={voiceLive.connectionState}
            isMuted={voiceLive.isMuted}
            onToggleMute={voiceLive.toggleMute}
            onToggleKeyboard={() => setShowKeyboard((prev) => !prev)}
            onEndSession={handleEndSession}
            isFullScreen={false}
            isTextMode={currentMode === "text"}
          />
        </div>

        {/* Right: Transcript + Text input + Hints panel */}
        <div className="flex min-h-0 w-[380px] shrink-0 flex-col border-l border-slate-200 bg-white">
          {/* Transcript area */}
          <div className="min-h-0 flex-1 overflow-hidden" data-testid="chat-area">
            {transcripts.length === 0 ? (
              <div className="flex h-full items-center justify-center">
                <p className="text-sm text-slate-400">
                  {sessionStarted
                    ? (currentMode === "text" ? tv("emptyTranscriptText") : tv("waitingForResponse"))
                    : tv("startPrompt")}
                </p>
              </div>
            ) : (
              <VoiceTranscript
                transcripts={transcripts}
                hcpName={hcpName}
                className="h-full"
              />
            )}
          </div>

          {/* Keyboard/text input area — always visible for MR to type */}
          {showKeyboard && (
            <div className="flex flex-col gap-2 border-t border-slate-200 px-4 py-3">
              {turnStatus !== "idle" && (
                <div className="text-xs text-slate-500" data-testid="turn-status">
                  {tv(`turn.${turnStatus}`)}
                </div>
              )}
              {turnError && <div className="text-xs text-red-600">{turnError}</div>}
              {turnStatus === "disconnected" && pendingMessage && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => void sendTextTurn(pendingMessage, true)}
                  data-testid="resume-turn-btn"
                >
                  {tv("turn.resume")}
                </Button>
              )}
              <div className="flex items-center gap-2">
              <input
                type="text"
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") handleKeyboardSubmit();
                }}
                placeholder={t("chat.placeholder")}
                disabled={isTurnBusy || session.mode !== "text"}
                className="flex-1 rounded-lg border border-slate-300 bg-slate-50 px-3 py-2 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary disabled:opacity-50"
                data-testid="text-input"
              />
              <Button
                size="sm"
                onClick={handleKeyboardSubmit}
                disabled={isTurnBusy || session.mode !== "text" || !inputText.trim()}
                data-testid="send-btn"
              >
                {tc("send")}
              </Button>
              </div>
            </div>
          )}
        </div>

        {/* Far right: Coaching hints panel */}
        <HintsPanel
          hints={hints}
          keyMessagesStatus={keyMessagesStatus}
          sessionStats={sessionStats}
          isCollapsed={hintsPanelCollapsed}
          onToggle={() => setHintsPanelCollapsed((prev) => !prev)}
        />
      </div>

      {/* End session confirmation dialog */}
      <Dialog open={showEndDialog} onOpenChange={setShowEndDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("endSessionConfirm")}</DialogTitle>
            <DialogDescription>{t("endSessionDescription")}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowEndDialog(false)}>
              {tc("cancel")}
            </Button>
            <Button variant="destructive" onClick={confirmEndSession}>
              {t("endSession")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
