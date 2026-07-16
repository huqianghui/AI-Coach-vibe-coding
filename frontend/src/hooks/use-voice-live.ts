import { useCallback, useRef, useState } from "react";
import type {
  VoiceLiveOptions,
  VoiceConnectionState,
  AudioState,
} from "@/types/voice-live";
import {
  createVoiceLogger,
  setSessionCorrelationId,
  getEventSummary,
  resetEventSummary,
} from "@/lib/voice-logger";

const log = createVoiceLogger("VoiceLive");

export interface VoiceLiveConnectOptions {
  hcpProfileId?: string;
  systemPrompt?: string;
  vlInstanceId?: string;
  enableAvatar?: boolean;
  sessionId?: string;
}

interface InternalVoiceLiveConnectOptions extends VoiceLiveConnectOptions {
  isReconnect?: boolean;
}

/**
 * Voice Live session hook using backend WebSocket proxy.
 *
 * The backend connects to Azure Voice Live via Python SDK (azure-ai-voicelive).
 * The frontend connects to the backend WebSocket and exchanges Azure RT protocol messages.
 *
 * Flow:
 *   1. Open WebSocket to /api/v1/voice-live/ws
 *   2. Send: {"type": "session.update", "session": {"hcp_profile_id": "...", "system_prompt": "..."}}
 *   3. Backend connects to Azure, sends back {"type": "proxy.connected", ...}
 *   4. Backend proxies Azure session config -> client receives session.created, session.updated
 *   5. Bidirectional: client sends audio/events -> backend -> Azure -> backend -> client
 */
export function useVoiceLive(options: VoiceLiveOptions) {
  const wsRef = useRef<WebSocket | null>(null);
  const [connectionState, setConnectionState] =
    useState<VoiceConnectionState>("disconnected");
  const [audioState, setAudioState] = useState<AudioState>("idle");
  const [isMuted, setIsMuted] = useState(false);
  const transcriptIdCounter = useRef(0);
  const connectionStateRef = useRef<VoiceConnectionState>("disconnected");
  const optionsRef = useRef(options);
  optionsRef.current = options;
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectAttemptRef = useRef(0);
  const intentionalCloseRef = useRef(false);
  const lastConnectArgsRef = useRef<VoiceLiveConnectOptions | null>(null);

  /** Ref for external avatar SDP answer callback (set by voice-session.tsx). */
  const avatarSdpCallbackRef = useRef<((serverSdp: string) => void) | null>(
    null,
  );

  /**
   * Connect to Azure Voice Live via backend WebSocket proxy.
   * @returns avatarEnabled, model name, and ICE servers for avatar WebRTC.
   */
  const connect = useCallback(
    async (
      optionsOrHcpProfileId?: InternalVoiceLiveConnectOptions | string,
      legacySystemPrompt?: string,
      legacyVlInstanceId?: string,
      legacyEnableAvatar?: boolean,
      legacySessionId?: string,
    ) => {
      const connectOptions: InternalVoiceLiveConnectOptions =
        typeof optionsOrHcpProfileId === "object"
          ? optionsOrHcpProfileId
          : {
              hcpProfileId: optionsOrHcpProfileId,
              systemPrompt: legacySystemPrompt,
              vlInstanceId: legacyVlInstanceId,
              enableAvatar: legacyEnableAvatar,
              sessionId: legacySessionId,
            };
      const {
        hcpProfileId,
        systemPrompt,
        vlInstanceId,
        enableAvatar,
        sessionId,
        isReconnect = false,
      } = connectOptions;
      const sid = crypto.randomUUID().slice(0, 8);
      setSessionCorrelationId(sid);
      resetEventSummary();
      log.info("connect() hcpProfileId=%s vlInstanceId=%s enableAvatar=%s sid=%s", hcpProfileId, vlInstanceId, enableAvatar, sid);

      lastConnectArgsRef.current = { hcpProfileId, systemPrompt, vlInstanceId, enableAvatar, sessionId };
      if (!isReconnect) reconnectAttemptRef.current = 0;
      intentionalCloseRef.current = false;
      setConnectionState("connecting");
      connectionStateRef.current = "connecting";
      optionsRef.current.onConnectionStateChange?.("connecting");

      return new Promise<{
        avatarEnabled: boolean;
        model: string;
        mode: "agent" | "model";
        iceServers: RTCIceServer[];
      }>((resolve, reject) => {
        try {
          const protocol = location.protocol === "https:" ? "wss:" : "ws:";
          const token = localStorage.getItem("access_token") ?? "";
          const wsUrl = `${protocol}//${location.host}/api/v1/voice-live/ws?token=${encodeURIComponent(token)}&sid=${sid}`;
          const ws = new WebSocket(wsUrl);

          let resolved = false;
          let lastErrorMessage: string | null = null;
          let sessionResult = { avatarEnabled: false, model: "gpt-4o", mode: "model" as "agent" | "model" };
          let iceServersResolve: ((servers: RTCIceServer[]) => void) | null =
            null;
          const iceServersPromise = new Promise<RTCIceServer[]>((res) => {
            iceServersResolve = res;
          });

          ws.onopen = () => {
            log.info("WebSocket open, sending session.update");
            ws.send(
              JSON.stringify({
                type: "session.update",
                session: {
                  ...(sessionId ? { session_id: sessionId } : {}),
                  ...(!sessionId && hcpProfileId ? { hcp_profile_id: hcpProfileId } : {}),
                  ...(!sessionId && vlInstanceId ? { vl_instance_id: vlInstanceId } : {}),
                  ...(!sessionId && enableAvatar !== undefined
                    ? { avatar_enabled: enableAvatar }
                    : {}),
                  ...(!sessionId ? {
                    system_prompt: systemPrompt || optionsRef.current.systemPrompt,
                  } : {}),
                },
              }),
            );
          };

          ws.onmessage = (event: MessageEvent) => {
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            let msg: any;
            try {
              msg = JSON.parse(event.data as string);
            } catch {
              log.warn("Non-JSON message received, ignoring");
              return;
            }

            // Check for avatar SDP answer by field presence (Azure may use
            // various event types — reference impl matches by field, not type)
            if (
              (msg.server_sdp || msg.sdp || msg.answer) &&
              msg.type !== "session.update"
            ) {
              const sdpValue = msg.server_sdp || msg.sdp || msg.answer;
              log.info(
                "Avatar SDP answer received, type=%s",
                msg.type,
              );
              avatarSdpCallbackRef.current?.(sdpValue);
            }

            // Count every event type for session summary
            if (msg.type) {
              log.event(msg.type);
            }

            // Debug: log event types (except high-frequency audio deltas)
            if (
              msg.type &&
              msg.type !== "response.audio.delta" &&
              msg.type !== "response.audio_transcript.delta"
            ) {
              log.debug("Event: %s, keys=%s", msg.type, Object.keys(msg).join(","));
            }

            switch (msg.type) {
              case "proxy.connected":
                sessionResult = {
                  avatarEnabled: msg.avatar_enabled ?? false,
                  model: msg.model ?? "gpt-4o",
                  mode: (msg.mode === "agent" ? "agent" : "model") as "agent" | "model",
                };
                log.info(
                  "Proxy connected, mode=%s, model=%s, avatar=%s",
                  sessionResult.mode,
                  sessionResult.model,
                  sessionResult.avatarEnabled,
                );
                break;

              case "session.created":
                log.info(
                  "Session created: %s",
                  msg.session?.id,
                );
                break;

              case "session.updated": {
                log.info("Session updated, avatar keys=%s",
                  Object.keys(msg.session?.avatar || {}).join(","));
                // Extract ICE servers from avatar config — matching reference
                // implementation which uses session-level username/credential
                // applied to all ICE servers (not per-server credentials).
                const avatarResp = msg.session?.avatar;
                const rawServers = avatarResp?.ice_servers ||
                  msg.session?.rtc?.ice_servers ||
                  msg.session?.ice_servers || [];

                // Session-level TURN credentials (reference: session.avatar.username)
                const sessionUsername: string | undefined =
                  avatarResp?.username ||
                  avatarResp?.ice_username ||
                  msg.session?.rtc?.ice_username ||
                  msg.session?.ice_username;
                const sessionCredential: string | undefined =
                  avatarResp?.credential ||
                  avatarResp?.ice_credential ||
                  msg.session?.rtc?.ice_credential ||
                  msg.session?.ice_credential;

                // Build ICE servers: apply session-level credentials if present
                const servers: RTCIceServer[] = (
                  // eslint-disable-next-line @typescript-eslint/no-explicit-any
                  Array.isArray(rawServers) ? rawServers : [{ urls: rawServers }]
                ).map(
                  // eslint-disable-next-line @typescript-eslint/no-explicit-any
                  (s: any) => {
                    const urls = typeof s === "string" ? s : (s.urls || []);
                    return {
                      urls,
                      username: sessionUsername || s.username,
                      credential: sessionCredential || s.credential,
                      ...(sessionUsername ? { credentialType: "password" as const } : {}),
                    };
                  },
                );
                if (servers.length > 0) {
                  log.info(
                    "ICE servers received: count=%d, hasSessionCreds=%s",
                    servers.length,
                    !!(sessionUsername && sessionCredential),
                  );
                } else if (sessionResult.avatarEnabled) {
                  log.warn("Avatar enabled but session.updated did not include ICE servers");
                }
                iceServersResolve?.(servers);

                // Mark as connected
                setConnectionState("connected");
                connectionStateRef.current = "connected";
                setAudioState("idle");
                optionsRef.current.onConnectionStateChange?.("connected");

                // Resolve connect promise
                if (!resolved) {
                  resolved = true;
                  void iceServersPromise.then((iceServers) => {
                    resolve({ ...sessionResult, iceServers });
                  });
                }
                break;
              }

              // Avatar SDP answer from server
              case "session.avatar.connecting":
                if (msg.server_sdp || msg.serverSdp) {
                  log.info("Avatar SDP answer received (session.avatar.connecting)");
                  avatarSdpCallbackRef.current?.(
                    msg.server_sdp || msg.serverSdp,
                  );
                }
                break;

              // Audio state: user speaking
              case "input_audio_buffer.speech_started":
                setAudioState("listening");
                optionsRef.current.onAudioStateChange?.("listening");
                break;

              case "input_audio_buffer.speech_stopped":
                setAudioState("idle");
                optionsRef.current.onAudioStateChange?.("idle");
                break;

              // User transcript completed
              case "conversation.item.input_audio_transcription.completed":
                if (msg.transcript) {
                  optionsRef.current.onTranscript?.({
                    id: `user-${++transcriptIdCounter.current}`,
                    role: "user",
                    content: msg.transcript,
                    isFinal: true,
                    timestamp: Date.now(),
                  });
                }
                break;

              // Assistant audio generation started
              case "response.created":
                setAudioState("speaking");
                optionsRef.current.onAudioStateChange?.("speaking");
                break;

              // Streaming assistant audio data (base64 PCM16 24kHz)
              case "response.audio.delta":
                if (msg.delta) {
                  optionsRef.current.onAudioDelta?.(msg.delta);
                } else {
                  log.warn(
                    "response.audio.delta without delta field, keys=%s",
                    Object.keys(msg).join(","),
                  );
                }
                break;

              // Streaming assistant audio transcript
              case "response.audio_transcript.delta":
                if (msg.delta) {
                  optionsRef.current.onTranscript?.({
                    id: `assistant-${msg.response_id}-${msg.item_id}`,
                    role: "assistant",
                    content: msg.delta,
                    isFinal: false,
                    timestamp: Date.now(),
                  });
                }
                break;

              // Final assistant audio transcript
              case "response.audio_transcript.done":
                if (msg.transcript) {
                  optionsRef.current.onTranscript?.({
                    id: `assistant-${msg.response_id}-${msg.item_id}`,
                    role: "assistant",
                    content: msg.transcript,
                    isFinal: true,
                    timestamp: Date.now(),
                  });
                }
                break;

              // Streaming text response
              case "response.text.delta":
                if (msg.delta) {
                  optionsRef.current.onTranscript?.({
                    id: `assistant-text-${msg.response_id}-${msg.item_id}`,
                    role: "assistant",
                    content: msg.delta,
                    isFinal: false,
                    timestamp: Date.now(),
                  });
                }
                break;

              case "response.text.done":
                if (msg.text) {
                  optionsRef.current.onTranscript?.({
                    id: `assistant-text-${msg.response_id}-${msg.item_id}`,
                    role: "assistant",
                    content: msg.text,
                    isFinal: true,
                    timestamp: Date.now(),
                  });
                }
                break;

              case "response.done":
                setAudioState("idle");
                optionsRef.current.onAudioStateChange?.("idle");
                optionsRef.current.onResponseDone?.();
                break;

              case "error":
                log.error("Error: %o", msg.error);
                const errorMessage: string = msg.error?.message || "Unknown error";
                lastErrorMessage = errorMessage;
                setConnectionState("error");
                connectionStateRef.current = "error";
                optionsRef.current.onConnectionStateChange?.("error");
                optionsRef.current.onError?.(
                  new Error(errorMessage),
                );
                if (!resolved) {
                  resolved = true;
                  reject(new Error(errorMessage));
                }
                break;
            }
          };

          ws.onclose = (closeEvent: CloseEvent) => {
            log.info(
              "WebSocket closed: code=%d reason=%s wasClean=%s",
              closeEvent.code,
              closeEvent.reason || "(none)",
              closeEvent.wasClean,
            );
            log.info("Event summary: %o", getEventSummary());

            const wasConnected = connectionStateRef.current === "connected";
            if (connectionStateRef.current !== "disconnected") {
              setConnectionState("disconnected");
              connectionStateRef.current = "disconnected";
              optionsRef.current.onConnectionStateChange?.("disconnected");
            }
            if (!resolved) {
              resolved = true;
              reject(
                new Error(
                  closeEvent.reason || lastErrorMessage || "WebSocket closed before connected",
                ),
              );
            }

            // Auto-reconnect on unexpected disconnect (max 3 attempts)
            const MAX_RECONNECT = 3;
            if (
              wasConnected &&
              !intentionalCloseRef.current &&
              reconnectAttemptRef.current < MAX_RECONNECT &&
              lastConnectArgsRef.current
            ) {
              reconnectAttemptRef.current++;
              const delay = Math.min(1000 * 2 ** (reconnectAttemptRef.current - 1), 8000);
              log.info(
                "Unexpected disconnect, reconnecting in %dms (attempt %d/%d)",
                delay,
                reconnectAttemptRef.current,
                MAX_RECONNECT,
              );
              setConnectionState("connecting");
              connectionStateRef.current = "connecting";
              optionsRef.current.onConnectionStateChange?.("connecting");
              reconnectTimerRef.current = setTimeout(() => {
                const args = lastConnectArgsRef.current;
                if (args) {
                  void connect({ ...args, isReconnect: true }).catch(() => {
                    // Reconnect failed — will be retried by the next onclose
                  });
                }
              }, delay);
            }
          };

          ws.onerror = () => {
            log.error("WebSocket error");
            setConnectionState("error");
            connectionStateRef.current = "error";
            optionsRef.current.onConnectionStateChange?.("error");
            optionsRef.current.onError?.(
              new Error("WebSocket connection failed"),
            );
            if (!resolved) {
              resolved = true;
              reject(new Error("WebSocket connection failed"));
            }
          };

          wsRef.current = ws;

          // Timeout
          setTimeout(() => {
            if (!resolved) {
              resolved = true;
              ws.close();
              reject(new Error("Connection timeout (30s)"));
            }
          }, 30_000);
        } catch (error) {
          setConnectionState("error");
          connectionStateRef.current = "error";
          optionsRef.current.onConnectionStateChange?.("error");
          optionsRef.current.onError?.(
            error instanceof Error ? error : new Error(String(error)),
          );
          reject(error);
        }
      });
    },
    [],
  );

  const disconnect = useCallback(async () => {
    log.info("disconnect() called, intentional close");
    intentionalCloseRef.current = true;
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setConnectionState("disconnected");
    connectionStateRef.current = "disconnected";
    setAudioState("idle");
    setIsMuted(false);
    optionsRef.current.onConnectionStateChange?.("disconnected");
  }, []);

  const toggleMute = useCallback(() => {
    setIsMuted((prev: boolean) => {
      const next = !prev;
      log.info("toggleMute: muted=%s", next);
      setAudioState(next ? "muted" : "idle");
      optionsRef.current.onAudioStateChange?.(next ? "muted" : "idle");
      return next;
    });
  }, []);

  /** Send a raw message to Azure via the backend WebSocket proxy. */
  const send = useCallback((data: unknown) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(
        typeof data === "string" ? data : JSON.stringify(data),
      );
    } else {
      log.warn(
        "send() dropped: readyState=%s",
        wsRef.current ? wsRef.current.readyState : "null",
      );
    }
  }, []);

  /** Send text message to the conversation. */
  const sendTextMessage = useCallback(
    async (text: string) => {
      log.info("sendTextMessage: len=%d", text.length);
      send({
        type: "conversation.item.create",
        item: {
          type: "message",
          role: "user",
          content: [{ type: "input_text", text }],
        },
      });
      send({ type: "response.create" });
    },
    [send],
  );

  /** Send audio data (PCM16 base64-encoded) to Azure via backend proxy. */
  const sendAudio = useCallback(
    (base64Audio: string) => {
      send({
        type: "input_audio_buffer.append",
        audio: base64Audio,
      });
    },
    [send],
  );

  return {
    connect,
    disconnect,
    toggleMute,
    sendTextMessage,
    sendAudio,
    send,
    isMuted,
    connectionState,
    audioState,
    avatarSdpCallbackRef,
  };
}
