import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useQueries, useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { getHcpProfile } from "@/api/hcp-profiles";
import { useStreamingSpeechInput, useTextToSpeech } from "@/hooks/use-speech";
import { useSessionRecorder } from "@/hooks/use-session-recorder";
import { useAvatarStream } from "@/hooks/use-avatar-stream";
import { useVoiceLive } from "@/hooks/use-voice-live";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Button,
} from "@/components/ui";
import {
  ConferenceHeader,
  TopicGuide,
  ConferenceStage,
  TranscriptionPanel,
  AudiencePanel,
  QuestionQueue,
} from "@/components/conference";
import {
  useConferenceSession,
  useAudienceHcps,
  useEndConferenceSession,
} from "@/hooks/use-conference";
import { useConferenceSSE } from "@/hooks/use-conference-sse";
import type {
  AudienceHcp,
  ConferenceSubState,
  QueuedQuestion,
  TranscriptLine,
  SpeakerTextEvent,
  TurnChangeEvent,
  SubStateEvent,
} from "@/types/conference";
import type { VoiceConnectionState } from "@/types/voice-live";

interface ChatMessage {
  id: string;
  sender: "hcp" | "mr";
  text: string;
  timestamp: Date;
  speakerName?: string;
  speakerColor?: string;
}

interface PendingAvatarSpeech {
  speakerId: string;
  speakerName: string;
  content: string;
  hcp?: AudienceHcp;
}

type AudienceConfigMember = Partial<AudienceHcp> & {
  scenario_id?: string;
  hcp_profile_id?: string;
  name?: string;
  specialty?: string;
  role?: string;
  voice_id?: string;
  voice_name?: string;
  voice_live_instance_id?: string | null;
  sort_order?: number;
  voice_live_enabled?: boolean;
  avatar_enabled?: boolean;
  avatar_character?: string;
  avatar_style?: string;
};

const SPEAKER_COLORS: string[] = [
  "var(--primary)",
  "var(--chart-2)",
  "var(--chart-3)",
  "var(--chart-4)",
  "var(--chart-5)",
];

const CONFERENCE_SILENCE_MS = 2000;
const CONFERENCE_MIN_SPEECH_MS = 700;
const CONFERENCE_NO_SPEECH_TIMEOUT_MS = 20000;

function normalizeAudienceMember(member: AudienceConfigMember): AudienceHcp {
  const hcpProfileId = member.hcpProfileId ?? member.hcp_profile_id ?? member.id ?? "";
  return {
    id: member.id ?? hcpProfileId,
    scenarioId: member.scenarioId ?? member.scenario_id ?? "",
    hcpProfileId,
    hcpName: member.hcpName ?? member.name ?? "",
    hcpSpecialty: member.hcpSpecialty ?? member.specialty ?? "",
    roleInConference: member.roleInConference ?? member.role ?? "audience",
    voiceId: member.voiceId ?? member.voice_id ?? "",
    voiceLiveInstanceId: member.voiceLiveInstanceId ?? member.voice_live_instance_id,
    voiceName: member.voiceName ?? member.voice_name,
    voiceLiveEnabled: member.voiceLiveEnabled ?? member.voice_live_enabled ?? false,
    avatarEnabled: member.avatarEnabled ?? member.avatar_enabled ?? false,
    avatarCharacter: member.avatarCharacter ?? member.avatar_character,
    avatarStyle: member.avatarStyle ?? member.avatar_style,
    sortOrder: member.sortOrder ?? member.sort_order ?? 0,
    status: member.status ?? "listening",
  };
}

function sendAvatarSpeech(voiceLive: ReturnType<typeof useVoiceLive>, text: string) {
  voiceLive.send({
    type: "conversation.item.create",
    item: {
      type: "message",
      role: "user",
      content: [
        {
          type: "input_text",
          text: `请只用中文自然朗读以下会议发言，不要补充任何内容：${text}`,
        },
      ],
    },
  });
  voiceLive.send({
    type: "response.create",
    response: {
      modalities: ["audio", "text"],
      instructions: `只朗读下面这段文本，不要解释、不要改写、不要添加前后缀：${text}`,
    },
  });
}

export default function ConferenceSession() {
  const { t } = useTranslation("conference");
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const sessionId = searchParams.get("id") ?? "";
  const groupRunId = searchParams.get("groupRunId");
  const initialInputMode = searchParams.get("inputMode") === "audio" ? "audio" : "text";
  const hasRequestedStartRef = useRef(false);

  // Fetch session
  const { data: session } = useConferenceSession(sessionId || undefined);
  const { data: scenarioAudienceHcps } = useAudienceHcps(
    session?.mode === "digital_human_realtime_model" ? session.scenarioId : undefined,
  );
  const endSessionMutation = useEndConferenceSession();

  // Local state
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [transcriptLines, setTranscriptLines] = useState<TranscriptLine[]>([]);
  const [questionQueue, setQuestionQueue] = useState<QueuedQuestion[]>([]);
  const [audienceHcps, setAudienceHcps] = useState<AudienceHcp[]>([]);
  const [subState, setSubState] = useState<ConferenceSubState>("");
  const [currentSpeaker, setCurrentSpeaker] = useState("");
  const [currentSpeakerId, setCurrentSpeakerId] = useState("");
  const [leftCollapsed, setLeftCollapsed] = useState(false);
  const [rightCollapsed, setRightCollapsed] = useState(false);
  const [inputMode, setInputMode] = useState<"text" | "audio">(initialInputMode);
  const [avatarConnectionState, setAvatarConnectionState] =
    useState<VoiceConnectionState>("disconnected");
  const [isAvatarConnected, setIsAvatarConnected] = useState(false);
  const [isAvatarSwitching, setIsAvatarSwitching] = useState(false);
  const [showEndDialog, setShowEndDialog] = useState(false);
  const [keyTopics, setKeyTopics] = useState<
    Array<{ message: string; delivered: boolean }>
  >([]);
  const isDigitalHumanMode = session?.mode === "digital_human_realtime_model";
  const { speak, stop: stopSpeaking, isSpeaking } = useTextToSpeech("zh-CN", undefined, {
    queue: true,
  });
  const sessionRecorder = useSessionRecorder();
  const avatarVideoRef = useRef<HTMLVideoElement>(null);
  const avatarStream = useAvatarStream(avatarVideoRef);
  const avatarResponseDoneResolverRef = useRef<(() => void) | null>(null);
  const voiceLive = useVoiceLive({
    language: "zh-CN",
    systemPrompt: "",
    onConnectionStateChange: setAvatarConnectionState,
    onResponseDone: () => {
      avatarResponseDoneResolverRef.current?.();
      avatarResponseDoneResolverRef.current = null;
    },
    onError: (error) => {
      avatarResponseDoneResolverRef.current?.();
      avatarResponseDoneResolverRef.current = null;
      toast.error(`数字人连接失败：${error.message}`);
    },
  });
  const avatarStreamRef = useRef(avatarStream);
  const voiceLiveRef = useRef(voiceLive);
  const startRecordingRef = useRef<() => Promise<void>>(async () => {});
  const stopRecordingRef = useRef<() => void>(() => {});
  const autoStartInFlightRef = useRef(false);
  const connectedAvatarHcpIdRef = useRef("");
  const audienceHcpsRef = useRef<AudienceHcp[]>([]);
  const avatarConnectionPromiseRef = useRef<Promise<boolean> | null>(null);
  const avatarSpeechQueueRef = useRef<PendingAvatarSpeech[]>([]);
  const isProcessingAvatarSpeechRef = useRef(false);

  useEffect(() => {
    avatarStreamRef.current = avatarStream;
    voiceLiveRef.current = voiceLive;
  });

  useEffect(() => {
    audienceHcpsRef.current = audienceHcps;
  }, [audienceHcps]);

  // Session timer
  const [sessionTime, setSessionTime] = useState("00:00");
  useEffect(() => {
    const startTime = session?.createdAt
      ? new Date(session.createdAt).getTime()
      : Date.now();
    const interval = setInterval(() => {
      const elapsed = Math.floor((Date.now() - startTime) / 1000);
      const mins = Math.floor(elapsed / 60)
        .toString()
        .padStart(2, "0");
      const secs = (elapsed % 60).toString().padStart(2, "0");
      setSessionTime(`${mins}:${secs}`);
    }, 1000);
    return () => clearInterval(interval);
  }, [session?.createdAt]);

  // Initialize audience from session
  useEffect(() => {
    if (session?.audienceConfig) {
      try {
        const parsed = JSON.parse(session.audienceConfig) as AudienceConfigMember[];
        setAudienceHcps(parsed.map(normalizeAudienceMember));
      } catch {
        // Invalid JSON, skip
      }
    }
  }, [session?.audienceConfig]);

  useEffect(() => {
    if (!isDigitalHumanMode || !scenarioAudienceHcps?.length) return;
    setAudienceHcps((prev) => {
      if (prev.some((hcp) => hcp.hcpProfileId)) return prev;
      return scenarioAudienceHcps;
    });
  }, [isDigitalHumanMode, scenarioAudienceHcps]);

  // Initialize sub-state from session
  useEffect(() => {
    if (session?.subState) {
      setSubState(session.subState);
    }
  }, [session?.subState]);

  useEffect(() => {
    if (
      session?.mode === "voice_realtime_model" ||
      session?.mode === "digital_human_realtime_model"
    ) {
      setInputMode("audio");
    }
  }, [session?.mode]);

  const activeAvatarHcp = useMemo(() => {
    if (!isDigitalHumanMode) return undefined;
    const matchingSpeaker = audienceHcps.find(
      (hcp) =>
        hcp.hcpProfileId === currentSpeakerId ||
        hcp.id === currentSpeakerId ||
        hcp.hcpName === currentSpeaker,
    );
    if (matchingSpeaker) return matchingSpeaker;

    const moderator = audienceHcps.find(
      (hcp) =>
        hcp.roleInConference === "moderator" &&
        hcp.voiceLiveEnabled &&
        hcp.avatarEnabled,
    );
    if (!currentSpeakerId && !currentSpeaker && moderator) return moderator;

    return (
      audienceHcps.find((hcp) => hcp.voiceLiveEnabled && hcp.avatarEnabled) ??
      audienceHcps[0]
    );
  }, [audienceHcps, currentSpeaker, currentSpeakerId, isDigitalHumanMode]);

  const { data: activeAvatarProfile } = useQuery({
    queryKey: ["hcp-profile", activeAvatarHcp?.hcpProfileId, "conference-avatar"],
    queryFn: () => getHcpProfile(activeAvatarHcp!.hcpProfileId),
    enabled: isDigitalHumanMode && Boolean(activeAvatarHcp?.hcpProfileId),
  });

  const audienceVoiceProfileQueries = useQueries({
    queries: audienceHcps.map((hcp) => ({
      queryKey: ["hcp-profile", hcp.hcpProfileId, "conference-voice"],
      queryFn: () => getHcpProfile(hcp.hcpProfileId),
      enabled: Boolean(hcp.hcpProfileId) && !hcp.voiceName,
    })),
  });

  const voiceNameByHcpId = useMemo(() => {
    const map = new Map<string, string>();
    audienceHcps.forEach((hcp, index) => {
      const profile = audienceVoiceProfileQueries[index]?.data;
      const profileVoiceName = profile?.voice_live_instance?.voice_name;
      const voiceName = hcp.voiceName || profileVoiceName;
      if (hcp.hcpProfileId && voiceName?.trim()) {
        map.set(hcp.hcpProfileId, voiceName);
      }
    });
    return map;
  }, [audienceHcps, audienceVoiceProfileQueries]);

  const activeAvatarCharacter =
    activeAvatarHcp?.avatarCharacter ||
    activeAvatarProfile?.voice_live_instance?.avatar_character ||
    "lori";
  const activeAvatarStyle =
    activeAvatarHcp?.avatarStyle ||
    activeAvatarProfile?.voice_live_instance?.avatar_style ||
    "casual";
  const activeAvatarName =
    activeAvatarHcp?.hcpName ?? activeAvatarProfile?.name ?? currentSpeaker;

  const findAvatarHcpForSpeaker = useCallback(
    (speakerId: string, speakerName: string) =>
      audienceHcpsRef.current.find(
        (hcp) =>
          hcp.hcpProfileId === speakerId ||
          hcp.id === speakerId ||
          hcp.hcpName === speakerName,
      ),
    [],
  );

  const speakHcpText = useCallback(
    (text: string, hcp?: AudienceHcp) => {
      const voiceName = hcp
        ? hcp.voiceName || voiceNameByHcpId.get(hcp.hcpProfileId) || hcp.voiceId
        : undefined;
      void speak(text, voiceName || undefined);
    },
    [speak, voiceNameByHcpId],
  );

  const connectConferenceAvatar = useCallback(async (targetHcp?: AudienceHcp) => {
    if (!isDigitalHumanMode) return false;
    const avatarHcp = targetHcp ?? activeAvatarHcp;
    if (!avatarHcp?.hcpProfileId) {
      toast.error("未找到数字人绑定的 HCP 配置");
      return false;
    }

    if (connectedAvatarHcpIdRef.current === avatarHcp.hcpProfileId) {
      return true;
    }

    if (avatarConnectionPromiseRef.current) {
      const connected = await avatarConnectionPromiseRef.current;
      if (connected && connectedAvatarHcpIdRef.current === avatarHcp.hcpProfileId) {
        return true;
      }
    }

    setIsAvatarSwitching(true);
    if (connectedAvatarHcpIdRef.current && connectedAvatarHcpIdRef.current !== avatarHcp.hcpProfileId) {
      setIsAvatarConnected(false);
      avatarStream.disconnect();
      await voiceLive.disconnect();
    }

    setAvatarConnectionState("connecting");
    setIsAvatarConnected(false);
    voiceLive.avatarSdpCallbackRef.current = (serverSdp: string) => {
      void avatarStream.handleServerSdp(serverSdp);
    };

    const connectionPromise = (async () => {
      const result = await voiceLive.connect(
        avatarHcp.hcpProfileId,
        "",
        undefined,
        true,
      );
      if (result.avatarEnabled) {
        await avatarStream.connect(result.iceServers, async (clientSdp: string) => {
          voiceLive.send({
            type: "session.avatar.connect",
            client_sdp: clientSdp,
          });
        });
        setAvatarConnectionState("connected");
        setIsAvatarConnected(true);
        connectedAvatarHcpIdRef.current = avatarHcp.hcpProfileId;
        return true;
      } else {
        setAvatarConnectionState("error");
        connectedAvatarHcpIdRef.current = "";
        avatarStream.disconnect();
        await voiceLive.disconnect();
        toast.error("当前 HCP 未启用真实数字人");
        return false;
      }
    })();

    avatarConnectionPromiseRef.current = connectionPromise;

    try {
      return await connectionPromise;
    } catch (error) {
      console.error("Failed to connect conference avatar", error);
      setAvatarConnectionState("error");
      setIsAvatarConnected(false);
      connectedAvatarHcpIdRef.current = "";
      avatarStream.disconnect();
      await voiceLive.disconnect();
      const message = error instanceof Error ? error.message : t("error.avatarFailed");
      toast.error(`数字人连接失败：${message}`);
      return false;
    } finally {
      if (avatarConnectionPromiseRef.current === connectionPromise) {
        avatarConnectionPromiseRef.current = null;
      }
      setIsAvatarSwitching(false);
    }
  }, [activeAvatarHcp, avatarStream, isDigitalHumanMode, t, voiceLive]);

  const waitForAvatarResponseDone = useCallback(
    () =>
      new Promise<void>((resolve) => {
        let timeoutId: number;
        const done = () => {
          window.clearTimeout(timeoutId);
          resolve();
        };

        timeoutId = window.setTimeout(() => {
          if (avatarResponseDoneResolverRef.current === done) {
            avatarResponseDoneResolverRef.current = null;
          }
          resolve();
        }, 30000);

        avatarResponseDoneResolverRef.current = done;
      }),
    [],
  );

  const processAvatarSpeechQueue = useCallback(async () => {
    if (isProcessingAvatarSpeechRef.current) return;
    isProcessingAvatarSpeechRef.current = true;

    try {
      while (avatarSpeechQueueRef.current.length > 0) {
        const nextSpeech = avatarSpeechQueueRef.current.shift();
        if (!nextSpeech) continue;

        setCurrentSpeaker(nextSpeech.speakerName);
        setCurrentSpeakerId(nextSpeech.speakerId);

        const speechHcp =
          nextSpeech.hcp ??
          findAvatarHcpForSpeaker(nextSpeech.speakerId, nextSpeech.speakerName);
        const isCurrentConnectedSpeaker =
          connectedAvatarHcpIdRef.current === nextSpeech.speakerId;

        if (!speechHcp && !isCurrentConnectedSpeaker) {
          speakHcpText(nextSpeech.content);
          continue;
        }

        const connected = isCurrentConnectedSpeaker
          ? true
          : await connectConferenceAvatar(speechHcp);
        if (connected) {
          sendAvatarSpeech(voiceLive, nextSpeech.content);
          await waitForAvatarResponseDone();
        } else {
          speakHcpText(nextSpeech.content, speechHcp);
        }
      }
    } finally {
      isProcessingAvatarSpeechRef.current = false;
    }
  }, [connectConferenceAvatar, findAvatarHcpForSpeaker, speakHcpText, voiceLive, waitForAvatarResponseDone]);

  const enqueueAvatarSpeech = useCallback(
    (speech: PendingAvatarSpeech) => {
      avatarSpeechQueueRef.current.push(speech);
      void processAvatarSpeechQueue();
    },
    [processAvatarSpeechQueue],
  );

  useEffect(() => {
    if (!isDigitalHumanMode) return;
    return () => {
      setIsAvatarConnected(false);
      connectedAvatarHcpIdRef.current = "";
      avatarResponseDoneResolverRef.current?.();
      avatarResponseDoneResolverRef.current = null;
      avatarSpeechQueueRef.current = [];
      isProcessingAvatarSpeechRef.current = false;
      avatarStreamRef.current.disconnect();
      void voiceLiveRef.current.disconnect();
    };
  }, [isDigitalHumanMode]);

  // Initialize key topics from session
  useEffect(() => {
    if (session?.keyMessagesStatus) {
      try {
        const parsed = JSON.parse(session.keyMessagesStatus) as Array<{
          message: string;
          delivered: boolean;
        }>;
        setKeyTopics(parsed);
      } catch {
        // Invalid JSON, skip
      }
    }
  }, [session?.keyMessagesStatus]);

  // Speaker color map
  const speakerMap = useMemo(() => {
    const map = new Map<string, number>();
    // MR is always index 0
    map.set("MR", 0);
    audienceHcps.forEach((hcp, index) => {
      map.set(hcp.id, (index % (SPEAKER_COLORS.length - 1)) + 1);
      map.set(hcp.hcpName, (index % (SPEAKER_COLORS.length - 1)) + 1);
    });
    return map;
  }, [audienceHcps]);

  function getSpeakerColor(speakerIdOrName: string): string {
    const index = speakerMap.get(speakerIdOrName) ?? 0;
    return SPEAKER_COLORS[index % SPEAKER_COLORS.length] ?? "var(--primary)";
  }

  // SSE callbacks
  const sseCallbacks = useMemo(
    () => ({
      onText: (_chunk: string) => {
        // streamedText is updated by hook
      },
      onSpeakerText: (data: SpeakerTextEvent) => {
        const msg: ChatMessage = {
          id: `hcp-${Date.now()}-${data.speaker_id}`,
          sender: "hcp",
          text: data.content,
          timestamp: new Date(),
          speakerName: data.speaker_name,
          speakerColor: getSpeakerColor(data.speaker_id),
        };
        setMessages((prev) => [...prev, msg]);
        setCurrentSpeaker(data.speaker_name);
        setCurrentSpeakerId(data.speaker_id);
        if (inputMode === "audio") {
          const speakerAvatarHcp = findAvatarHcpForSpeaker(
            data.speaker_id,
            data.speaker_name,
          );
          if (isDigitalHumanMode) {
            enqueueAvatarSpeech({
              speakerId: data.speaker_id,
              speakerName: data.speaker_name,
              content: data.content,
              hcp: speakerAvatarHcp,
            });
          } else {
            speakHcpText(data.content, speakerAvatarHcp);
          }
        }
      },
      onQueueUpdate: (queue: QueuedQuestion[]) => {
        setQuestionQueue(queue);
      },
      onTurnChange: (data: TurnChangeEvent) => {
        setCurrentSpeaker(data.speaker_name);
        setCurrentSpeakerId(data.speaker_id);
        setAudienceHcps((prev) =>
          prev.map((hcp) =>
            hcp.id === data.speaker_id || hcp.hcpProfileId === data.speaker_id
              ? {
                  ...hcp,
                  status: data.action === "asking" ? "speaking" : "listening",
                }
              : hcp,
          ),
        );
      },
      onSubState: (data: SubStateEvent) => {
        setSubState(data.sub_state);
      },
      onTranscription: (line: {
        speaker: string;
        text: string;
        timestamp: string;
      }) => {
        setTranscriptLines((prev) => [
          ...prev,
          {
            speaker: line.speaker,
            text: line.text,
            timestamp: new Date(line.timestamp),
          },
        ]);
      },
      onKeyMessages: (
        msgs: Array<{ message: string; delivered: boolean }>,
      ) => {
        setKeyTopics(msgs);
      },
      onDone: () => {
        // Session completed
      },
      onError: (error: string) => {
        console.error("Conference SSE error:", error);
      },
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [speakerMap, inputMode, isDigitalHumanMode, findAvatarHcpForSpeaker, enqueueAvatarSpeech, speakHcpText],
  );

  useEffect(
    () => () => {
      stopSpeaking();
      avatarStreamRef.current.disconnect();
      void voiceLiveRef.current.disconnect();
    },
    [stopSpeaking],
  );

  const { sendMessage, isStreaming, streamedText } = useConferenceSSE(
    sessionId,
    sseCallbacks,
  );

  useEffect(() => {
    if (!sessionId || !session || hasRequestedStartRef.current) return;
    if (isDigitalHumanMode && !isAvatarConnected) return;
    hasRequestedStartRef.current = true;
    sendMessage("start", "");
  }, [isAvatarConnected, isDigitalHumanMode, sessionId, session, sendMessage]);

  // Handlers
  const handleConferenceInput = useCallback(
    (text: string) => {
      const pendingQuestion = questionQueue[0];
      const userMsg: ChatMessage = {
        id: `mr-${Date.now()}`,
        sender: "mr",
        text,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, userMsg]);

      if (pendingQuestion) {
        setQuestionQueue((prev) =>
          prev.map((q, index) =>
            index === 0 ? { ...q, status: "active" as const } : q,
          ),
        );
        sendMessage("respond", text, pendingQuestion.hcpProfileId);
        return;
      }

      sendMessage("present", text);
    },
    [questionQueue, sendMessage],
  );

  // Speech input for conference mic
  const handleSpeechTranscribed = useCallback(
    (text: string) => {
      handleConferenceInput(text);
    },
    [handleConferenceInput],
  );

  const handleSpeechStreamReady = useCallback(
    async (stream: MediaStream) => {
      if (inputMode !== "audio") return;
      const started = await sessionRecorder.startRecording(stream);
      if (!started) {
        toast.error(t("error.voiceRecordingFailed"));
      }
    },
    [inputMode, sessionRecorder, t],
  );

  const {
    startRecording,
    stopRecording,
    recordingState,
    error: speechError,
  } = useStreamingSpeechInput(handleSpeechTranscribed, "zh-CN", {
    autoStopOnSilence: true,
    silenceMs: CONFERENCE_SILENCE_MS,
    minSpeechMs: CONFERENCE_MIN_SPEECH_MS,
    noSpeechTimeoutMs: CONFERENCE_NO_SPEECH_TIMEOUT_MS,
    onStreamReady: handleSpeechStreamReady,
  });

  useEffect(() => {
    startRecordingRef.current = startRecording;
  }, [startRecording]);

  useEffect(() => {
    stopRecordingRef.current = stopRecording;
  }, [stopRecording]);

  useEffect(() => {
    if (speechError) {
      toast.error(speechError);
      // Auto-fallback to text mode on configuration errors to prevent infinite retry
      if (
        speechError.includes("未配置") ||
        speechError.includes("not configured") ||
        speechError.includes("连接失败")
      ) {
        setInputMode("text");
      }
    }
  }, [speechError]);

  const handleConferenceMicClick = useCallback(() => {
    if (recordingState === "recording") {
      stopRecording();
    } else if (recordingState === "idle") {
      void startRecording();
    }
  }, [recordingState, startRecording, stopRecording]);

  const shouldAutoListen =
    inputMode === "audio" &&
    Boolean(sessionId && session) &&
    session?.status !== "completed" &&
    !isSpeaking;

  useEffect(() => {
    if (!shouldAutoListen) {
      autoStartInFlightRef.current = false;
      if (recordingState !== "idle") {
        stopRecordingRef.current();
      }
      return;
    }

    if (recordingState !== "idle" || autoStartInFlightRef.current) return;

    autoStartInFlightRef.current = true;
    void Promise.resolve(startRecordingRef.current()).finally(() => {
      autoStartInFlightRef.current = false;
    });
  }, [recordingState, shouldAutoListen]);

  const handleRespondToQuestion = useCallback(
    (hcpId: string) => {
      const question = questionQueue.find(
        (q) => q.hcpProfileId === hcpId && q.status === "waiting",
      );
      if (question) {
        setQuestionQueue((prev) =>
          prev.map((q) =>
            q.hcpProfileId === hcpId && q.status === "waiting"
              ? { ...q, status: "active" as const }
              : q,
          ),
        );
        sendMessage("respond", "", hcpId);
      }
    },
    [questionQueue, sendMessage],
  );

  const handleEndSession = useCallback(() => {
    setShowEndDialog(true);
  }, []);

  const confirmEndSession = useCallback(async () => {
    setShowEndDialog(false);
    try {
      stopSpeaking();
      avatarStream.disconnect();
      await voiceLive.disconnect();
      if (recordingState !== "idle") {
        stopRecordingRef.current();
      }
      if (inputMode === "audio") {
        const uploadResult = await sessionRecorder.stopAndUpload(sessionId);
        if (!uploadResult.success) {
          toast.error(uploadResult.error ?? t("error.voiceRecordingFailed"));
        }
      }
      await endSessionMutation.mutateAsync(sessionId);
      const scoringUrl = groupRunId
        ? `/user/scoring/${sessionId}?groupRunId=${groupRunId}`
        : `/user/scoring/${sessionId}`;
      navigate(scoringUrl);
    } catch {
      toast.error(t("error.endFailed"));
    }
  }, [avatarStream, endSessionMutation, groupRunId, inputMode, navigate, recordingState, sessionId, sessionRecorder, stopSpeaking, t, voiceLive]);

  return (
    <div className="flex h-screen w-screen flex-col overflow-hidden bg-background">
      {/* Conference Header */}
      <ConferenceHeader
        session={session}
        subState={subState}
        onEndSession={handleEndSession}
        sessionTime={sessionTime}
      />

      {/* Main content: TopicGuide + ConferenceStage + TranscriptionPanel */}
      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        <TopicGuide
          topics={keyTopics}
          scenarioName={session?.presentationTopic ?? ""}
          isCollapsed={leftCollapsed}
          onToggle={() => setLeftCollapsed((prev) => !prev)}
        />

        <ConferenceStage
          sessionId={sessionId}
          onSendMessage={handleConferenceInput}
          isStreaming={isStreaming}
          streamedText={streamedText}
          currentSpeaker={currentSpeaker}
          currentSpeakerId={currentSpeakerId}
          avatarEnabled={true}
          featureAvatarEnabled={isDigitalHumanMode}
          digitalHumanEnabled={isDigitalHumanMode}
          audienceHcps={audienceHcps}
          avatarVideoRef={avatarVideoRef}
          isAvatarConnected={isAvatarConnected}
          isAvatarConnecting={
            isAvatarSwitching || avatarConnectionState === "connecting"
          }
          avatarAudioState={voiceLive.audioState}
          avatarCharacter={activeAvatarCharacter}
          avatarStyle={activeAvatarStyle}
          avatarHcpName={activeAvatarName}
          activeAvatarHcpId={activeAvatarHcp?.hcpProfileId || activeAvatarHcp?.id}
          onAvatarConnectClick={() => void connectConferenceAvatar()}
          messages={messages}
          inputMode={inputMode}
          onInputModeChange={setInputMode}
          onMicClick={handleConferenceMicClick}
          recordingState={recordingState}
          disabled={session?.status === "completed"}
        />

        <TranscriptionPanel
          lines={transcriptLines}
          isCollapsed={rightCollapsed}
          onToggle={() => setRightCollapsed((prev) => !prev)}
          speakerMap={speakerMap}
        />
      </div>

      {/* Audience Panel */}
      <AudiencePanel hcps={audienceHcps} />

      {/* Question Queue */}
      <QuestionQueue
        questions={questionQueue}
        onRespondTo={handleRespondToQuestion}
      />

      {/* End session confirmation dialog */}
      <Dialog open={showEndDialog} onOpenChange={setShowEndDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("endPresentation")}</DialogTitle>
            <DialogDescription>
              {t("endConfirm")}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setShowEndDialog(false)}
            >
              {t("continuePresenting")}
            </Button>
            <Button variant="destructive" onClick={confirmEndSession}>
              {t("endPresentation")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
