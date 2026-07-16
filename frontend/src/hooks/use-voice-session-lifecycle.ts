import { useCallback, useRef, useState } from "react";
import { encodePcmToBase64 } from "@/lib/voice-utils";
import type { useVoiceLive } from "@/hooks/use-voice-live";
import type { useAvatarStream } from "@/hooks/use-avatar-stream";
import type { useAudioHandler } from "@/hooks/use-audio-handler";
import type { useAudioPlayer } from "@/hooks/use-audio-player";

/** Return types of the hooks this lifecycle hook depends on. */
type VoiceLiveControls = ReturnType<typeof useVoiceLive>;
type AvatarStreamControls = ReturnType<typeof useAvatarStream>;
type AudioHandlerControls = ReturnType<typeof useAudioHandler>;
type AudioPlayerControls = ReturnType<typeof useAudioPlayer> & {
  prepare?: () => Promise<void>;
};

export interface VoiceSessionLifecycleDeps {
  voiceLive: VoiceLiveControls;
  avatarStream: AvatarStreamControls;
  audioHandler: AudioHandlerControls;
  audioPlayer: AudioPlayerControls;
}

export interface StartSessionOptions {
  /** Trusted backend coaching Session identifier for training paths. */
  sessionId?: string;
  hcpProfileId?: string;
  systemPrompt?: string;
  vlInstanceId?: string;
  /** Whether the client wants the Azure Avatar modality. False forces voice-only. */
  enableAvatar?: boolean;
  /** Legacy alias for enableAvatar. */
  avatarEnabled?: boolean;
  /** Called when mic permission is denied. */
  onMicDenied?: () => void;
  /** Called when AudioWorklet fails to load. */
  onAudioWorkletFailed?: () => void;
  /** Called when avatar WebRTC fails (session continues in voice-only mode). */
  onAvatarFailed?: () => void;
  /** Called on general connection failure. */
  onConnectionFailed?: (error: unknown) => void;
}

export interface StartSessionResult {
  avatarEnabled: boolean;
  model: string;
  mode: "agent" | "model";
}

interface VoiceSessionLifecycleControls {
  startSession: (options: StartSessionOptions) => Promise<StartSessionResult | null>;
  stopSession: () => Promise<void>;
  isBusy: boolean;
}

/**
 * Shared voice session init/teardown hook.
 *
 * Provides reentrancy guard (prevents double-start), unmount cancellation
 * via AbortController, and a clean startSession/stopSession interface.
 */
export function useVoiceSessionLifecycle(
  deps: VoiceSessionLifecycleDeps,
): VoiceSessionLifecycleControls {
  const { voiceLive, avatarStream, audioHandler, audioPlayer } = deps;
  const busyRef = useRef<boolean>(false);
  const abortRef = useRef<AbortController | null>(null);
  const [isBusy, setIsBusy] = useState(false);

  const startSession = useCallback(
    async (options: StartSessionOptions): Promise<StartSessionResult | null> => {
      // Reentrancy guard
      if (busyRef.current) return null;
      busyRef.current = true;
      setIsBusy(true);

      // Create abort controller for unmount cancellation
      abortRef.current?.abort();
      const abortController = new AbortController();
      abortRef.current = abortController;

      try {
        // 0. Unlock playback AudioContext within the user-gesture chain so
        //    Chrome's autoplay policy permits playing TTS audio that arrives
        //    asynchronously via WebSocket later.
        try {
          await audioPlayer.prepare?.();
        } catch {
          // Non-fatal: playAudio() will retry resume() on first chunk.
        }

        // 1. Initialize audio (mic permission + AudioWorklet)
        try {
          await audioHandler.initialize();
        } catch (audioError) {
          if (audioError instanceof DOMException && audioError.name === "NotAllowedError") {
            options.onMicDenied?.();
          } else {
            options.onAudioWorkletFailed?.();
          }
          return null;
        }

        if (abortController.signal.aborted) return null;

        // 2. Wire up avatar SDP callback BEFORE connecting
        voiceLive.avatarSdpCallbackRef.current = (serverSdp: string) => {
          void avatarStream.handleServerSdp(serverSdp);
        };

        // 3. Connect via backend WebSocket proxy
        const result = await voiceLive.connect({
          hcpProfileId: options.hcpProfileId,
          systemPrompt: options.systemPrompt,
          vlInstanceId: options.vlInstanceId,
          enableAvatar: options.enableAvatar ?? options.avatarEnabled,
          sessionId: options.sessionId,
        });

        if (abortController.signal.aborted) {
          await voiceLive.disconnect();
          return null;
        }

        // 4. Connect avatar WebRTC if available
        let avatarConnected = result.avatarEnabled;
        if (result.avatarEnabled) {
          try {
            await avatarStream.connect(
              result.iceServers,
              async (clientSdp: string) => {
                voiceLive.send({
                  type: "session.avatar.connect",
                  client_sdp: clientSdp,
                });
              },
            );
          } catch {
            avatarConnected = false;
            options.onAvatarFailed?.();
            // Continue in voice-only mode
          }
        }

        if (abortController.signal.aborted) {
          await voiceLive.disconnect();
          avatarStream.disconnect();
          return null;
        }

        // 5. Start recording mic audio with PCM encoding
        audioHandler.startRecording((audioData: Float32Array) => {
          if (voiceLive.isMuted) return;
          voiceLive.sendAudio(encodePcmToBase64(audioData));
        });

        return {
          avatarEnabled: avatarConnected,
          model: result.model,
          mode: result.mode,
        };
      } catch (error) {
        options.onConnectionFailed?.(error);
        return null;
      } finally {
        busyRef.current = false;
        setIsBusy(false);
      }
    },
    [voiceLive, avatarStream, audioHandler, audioPlayer],
  );

  const stopSession = useCallback(async () => {
    // Cancel any in-progress start
    abortRef.current?.abort();
    abortRef.current = null;

    await voiceLive.disconnect();
    avatarStream.disconnect();
    audioHandler.cleanup();
    audioPlayer.stopAudio();
  }, [voiceLive, avatarStream, audioHandler, audioPlayer]);

  return { startSession, stopSession, isBusy };
}
