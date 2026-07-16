import { useCallback, useRef } from "react";
import { createVoiceLogger } from "@/lib/voice-logger";

const log = createVoiceLogger("AudioPlayer");

/**
 * Audio playback hook for Azure Voice Live response audio.
 *
 * Decodes base64-encoded PCM16 audio chunks (24kHz mono) from
 * `response.audio.delta` events and plays them back via Web Audio API
 * with gapless scheduling.
 *
 * An AnalyserNode is inserted in the playback chain so that consumers
 * (e.g. useVolumeLevel) can read frequency data for output-audio-reactive
 * visualizations such as the AudioOrb.
 *
 * Pattern matches the reference implementation (useAudioPlayer.ts):
 *   base64 → Uint8Array → Int16Array → Float32Array → AudioBufferSourceNode
 */
export function useAudioPlayer() {
  const audioCtxRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const nextPlayTimeRef = useRef(0);

  /** Ensure AudioContext + AnalyserNode are created. */
  const ensureAudioPipeline = useCallback(() => {
    if (!audioCtxRef.current) {
      const ctx = new AudioContext({ sampleRate: 24000 });
      audioCtxRef.current = ctx;

      const analyser = ctx.createAnalyser();
      analyser.fftSize = 256;
      analyser.connect(ctx.destination);
      analyserRef.current = analyser;

      log.info("AudioContext created, sampleRate=%d", ctx.sampleRate);
    }
    return {
      audioCtx: audioCtxRef.current,
      analyser: analyserRef.current!,
    };
  }, []);

  const chunkCountRef = useRef(0);

  /** Decode base64 PCM16 and schedule for gapless playback. */
  const playAudio = useCallback(
    (base64Audio: string) => {
      const { audioCtx, analyser } = ensureAudioPipeline();
      chunkCountRef.current += 1;

      // Resume if suspended (browser autoplay policy)
      if (audioCtx.state === "suspended") {
        log.info("AudioContext suspended, resuming");
        void audioCtx.resume();
      }

      // Log first chunk and every 50th to verify the playback pipeline.
      if (chunkCountRef.current === 1 || chunkCountRef.current % 50 === 0) {
        log.info(
          "playAudio chunk #%d, ctx.state=%s, base64Len=%d",
          chunkCountRef.current,
          audioCtx.state,
          base64Audio.length,
        );
      }

      // Decode: base64 → bytes → Int16 PCM → Float32 normalized [-1, 1]
      const binaryStr = atob(base64Audio);
      const bytes = new Uint8Array(binaryStr.length);
      for (let i = 0; i < binaryStr.length; i++) {
        bytes[i] = binaryStr.charCodeAt(i);
      }
      const int16 = new Int16Array(bytes.buffer);
      const float32 = new Float32Array(int16.length);
      for (let i = 0; i < int16.length; i++) {
        float32[i] = (int16[i] ?? 0) / 32768;
      }

      // Create AudioBuffer and schedule for gapless playback.
      // Route through AnalyserNode so output volume can be measured.
      const buffer = audioCtx.createBuffer(1, float32.length, 24000);
      buffer.getChannelData(0).set(float32);
      const src = audioCtx.createBufferSource();
      src.buffer = buffer;
      src.connect(analyser); // analyser → destination (connected once in ensureAudioPipeline)

      // Schedule: each chunk starts when the previous ends
      nextPlayTimeRef.current = Math.max(
        nextPlayTimeRef.current,
        audioCtx.currentTime,
      );
      src.start(nextPlayTimeRef.current);
      nextPlayTimeRef.current += buffer.duration;
    },
    [ensureAudioPipeline],
  );

  /** Stop all pending audio and reset the schedule. */
  const stopAudio = useCallback(() => {
    log.info("stopAudio");
    if (audioCtxRef.current) {
      void audioCtxRef.current.close();
      audioCtxRef.current = null;
    }
    analyserRef.current = null;
    nextPlayTimeRef.current = 0;
    chunkCountRef.current = 0;
  }, []);

  /**
   * Pre-create and resume the AudioContext within a user-gesture handler
   * (e.g. the click that starts a session). This satisfies Chrome's
   * autoplay policy so that subsequent `playAudio()` calls -- which are
   * triggered asynchronously by WebSocket events -- can play audio.
   */
  const prepare = useCallback(async () => {
    const { audioCtx } = ensureAudioPipeline();
    if (audioCtx.state === "suspended") {
      try {
        await audioCtx.resume();
        log.info("AudioContext resumed via user gesture, state=%s", audioCtx.state);
      } catch (err) {
        log.warn("AudioContext resume() failed: %o", err);
      }
    }
  }, [ensureAudioPipeline]);

  return { playAudio, stopAudio, prepare, analyserRef };
}
