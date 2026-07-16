import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useVoiceSessionLifecycle } from "../use-voice-session-lifecycle";

function createMockDeps() {
  return {
    voiceLive: {
      connect: vi.fn().mockResolvedValue({
        avatarEnabled: false,
        model: "gpt-4o",
        mode: "model",
        iceServers: [],
      }),
      disconnect: vi.fn().mockResolvedValue(undefined),
      send: vi.fn(),
      sendAudio: vi.fn(),
      isMuted: false,
      avatarSdpCallbackRef: { current: null } as { current: ((sdp: string) => void) | null },
    },
    audioHandler: {
      initialize: vi.fn().mockResolvedValue(undefined),
      startRecording: vi.fn(),
      cleanup: vi.fn(),
    },
    avatarStream: {
      connect: vi.fn().mockResolvedValue(undefined),
      disconnect: vi.fn(),
      handleServerSdp: vi.fn().mockResolvedValue(undefined),
    },
    audioPlayer: {
      stopAudio: vi.fn(),
    },
  };
}

describe("useVoiceSessionLifecycle", () => {
  let deps: ReturnType<typeof createMockDeps>;

  beforeEach(() => {
    vi.clearAllMocks();
    deps = createMockDeps();
  });

  it("provides startSession, stopSession, and isBusy", () => {
    const { result } = renderHook(() =>
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      useVoiceSessionLifecycle(deps as any),
    );

    expect(typeof result.current.startSession).toBe("function");
    expect(typeof result.current.stopSession).toBe("function");
    expect(result.current.isBusy).toBe(false);
  });

  it("calls initialize, connect, and startRecording in sequence", async () => {
    const { result } = renderHook(() =>
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      useVoiceSessionLifecycle(deps as any),
    );

    await act(async () => {
      await result.current.startSession({});
    });

    expect(deps.audioHandler.initialize).toHaveBeenCalledTimes(1);
    expect(deps.voiceLive.connect).toHaveBeenCalledTimes(1);
    expect(deps.audioHandler.startRecording).toHaveBeenCalledTimes(1);
  });

  it("prevents reentrancy — double startSession results in single init", async () => {
    deps.voiceLive.connect.mockImplementation(
      () =>
        new Promise((resolve) =>
          setTimeout(
            () =>
              resolve({
                avatarEnabled: false,
                model: "gpt-4o",
                mode: "model",
                iceServers: [],
              }),
            100,
          ),
        ),
    );

    const { result } = renderHook(() =>
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      useVoiceSessionLifecycle(deps as any),
    );

    await act(async () => {
      // Fire two starts simultaneously — second should be no-op
      const p1 = result.current.startSession({});
      const p2 = result.current.startSession({});
      await Promise.all([p1, p2]);
    });

    // Only one initialize call despite two startSession calls
    expect(deps.audioHandler.initialize).toHaveBeenCalledTimes(1);
  });

  it("calls onMicDenied when mic permission fails", async () => {
    const micError = new DOMException("Permission denied", "NotAllowedError");
    deps.audioHandler.initialize.mockRejectedValueOnce(micError);

    const onMicDenied = vi.fn();
    const { result } = renderHook(() =>
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      useVoiceSessionLifecycle(deps as any),
    );

    await act(async () => {
      await result.current.startSession({ onMicDenied });
    });

    expect(onMicDenied).toHaveBeenCalledTimes(1);
    expect(deps.voiceLive.connect).not.toHaveBeenCalled();
  });

  it("stopSession calls all cleanup functions", async () => {
    const { result } = renderHook(() =>
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      useVoiceSessionLifecycle(deps as any),
    );

    await act(async () => {
      await result.current.stopSession();
    });

    expect(deps.voiceLive.disconnect).toHaveBeenCalled();
    expect(deps.avatarStream.disconnect).toHaveBeenCalled();
    expect(deps.audioHandler.cleanup).toHaveBeenCalled();
    expect(deps.audioPlayer.stopAudio).toHaveBeenCalled();
  });

  it("isBusy reflects busy state during session start", async () => {
    let resolveFn: ((v: unknown) => void) | null = null;
    deps.voiceLive.connect.mockImplementation(
      () => new Promise((resolve) => { resolveFn = resolve; }),
    );

    const { result } = renderHook(() =>
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      useVoiceSessionLifecycle(deps as any),
    );

    expect(result.current.isBusy).toBe(false);

    let startPromise: Promise<unknown>;
    await act(async () => {
      startPromise = result.current.startSession({});
    });

    // Should be busy while connecting
    expect(result.current.isBusy).toBe(true);

    // Resolve the connect
    await act(async () => {
      resolveFn!({
        avatarEnabled: false,
        model: "gpt-4o",
        mode: "model",
        iceServers: [],
      });
      await startPromise!;
    });

    expect(result.current.isBusy).toBe(false);
  });

  it("connects avatar stream when avatarEnabled is true", async () => {
    deps.voiceLive.connect.mockResolvedValue({
      avatarEnabled: true,
      model: "gpt-4o",
      mode: "model",
      iceServers: [{ urls: "stun:stun.example.com" }],
    });

    const { result } = renderHook(() =>
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      useVoiceSessionLifecycle(deps as any),
    );

    let sessionResult: unknown;
    await act(async () => {
      sessionResult = await result.current.startSession({});
    });

    expect(deps.avatarStream.connect).toHaveBeenCalledTimes(1);
    // Verify iceServers were passed
    expect(deps.avatarStream.connect).toHaveBeenCalledWith(
      [{ urls: "stun:stun.example.com" }],
      expect.any(Function),
    );
    expect(sessionResult).toEqual({
      avatarEnabled: true,
      model: "gpt-4o",
      mode: "model",
    });
  });

  it("calls onAvatarFailed and continues in voice-only mode when avatar connect throws", async () => {
    deps.voiceLive.connect.mockResolvedValue({
      avatarEnabled: true,
      model: "gpt-4o",
      mode: "model",
      iceServers: [],
    });
    deps.avatarStream.connect.mockRejectedValueOnce(new Error("WebRTC failed"));

    const onAvatarFailed = vi.fn();
    const { result } = renderHook(() =>
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      useVoiceSessionLifecycle(deps as any),
    );

    let sessionResult: unknown;
    await act(async () => {
      sessionResult = await result.current.startSession({ onAvatarFailed });
    });

    expect(onAvatarFailed).toHaveBeenCalledTimes(1);
    // Session should still succeed (voice-only mode)
    expect(sessionResult).toEqual({
      avatarEnabled: false,
      model: "gpt-4o",
      mode: "model",
    });
    expect(deps.audioHandler.startRecording).toHaveBeenCalledTimes(1);
  });

  it("calls onAudioWorkletFailed when initialize throws non-NotAllowedError", async () => {
    const workletError = new Error("AudioWorklet loading failed");
    deps.audioHandler.initialize.mockRejectedValueOnce(workletError);

    const onAudioWorkletFailed = vi.fn();
    const { result } = renderHook(() =>
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      useVoiceSessionLifecycle(deps as any),
    );

    const sessionResult = await act(async () => {
      return await result.current.startSession({ onAudioWorkletFailed });
    });

    expect(onAudioWorkletFailed).toHaveBeenCalledTimes(1);
    expect(sessionResult).toBeNull();
    expect(deps.voiceLive.connect).not.toHaveBeenCalled();
  });

  it("calls onConnectionFailed when voiceLive.connect throws", async () => {
    const connectError = new Error("WebSocket connection refused");
    deps.voiceLive.connect.mockRejectedValueOnce(connectError);

    const onConnectionFailed = vi.fn();
    const { result } = renderHook(() =>
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      useVoiceSessionLifecycle(deps as any),
    );

    const sessionResult = await act(async () => {
      return await result.current.startSession({ onConnectionFailed });
    });

    expect(onConnectionFailed).toHaveBeenCalledTimes(1);
    expect(onConnectionFailed).toHaveBeenCalledWith(connectError);
    expect(sessionResult).toBeNull();
    // isBusy should be reset after failure
    expect(result.current.isBusy).toBe(false);
  });

  it("returns null when abort fires during avatar connect phase", async () => {
    deps.voiceLive.connect.mockResolvedValue({
      avatarEnabled: true,
      model: "gpt-4o",
      iceServers: [],
    });
    // Make avatarStream.connect hang so we can abort
    let resolveAvatar: (() => void) | null = null;
    deps.avatarStream.connect.mockImplementation(
      () => new Promise<void>((resolve) => { resolveAvatar = resolve; }),
    );

    const { result } = renderHook(() =>
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      useVoiceSessionLifecycle(deps as any),
    );

    let startPromise: Promise<unknown>;
    await act(async () => {
      startPromise = result.current.startSession({});
    });

    // Now stop (which aborts)
    await act(async () => {
      await result.current.stopSession();
      // Resolve the hanging avatar connect so the promise chain completes
      resolveAvatar?.();
      await startPromise!;
    });

    // disconnect should have been called due to abort
    expect(deps.voiceLive.disconnect).toHaveBeenCalled();
  });

  it("passes sessionId and legacy playground options to voiceLive.connect", async () => {
    const { result } = renderHook(() =>
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      useVoiceSessionLifecycle(deps as any),
    );

    await act(async () => {
      await result.current.startSession({
        sessionId: "session-789",
        hcpProfileId: "hcp-123",
        systemPrompt: "You are a doctor",
        vlInstanceId: "vl-456",
      });
    });

    expect(deps.voiceLive.connect).toHaveBeenCalledWith({
      hcpProfileId: "hcp-123",
      systemPrompt: "You are a doctor",
      vlInstanceId: "vl-456",
      enableAvatar: undefined,
      sessionId: "session-789",
    });
  });

  it("forwards enableAvatar to voiceLive.connect when client picks voice-only mode", async () => {
    const { result } = renderHook(() =>
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      useVoiceSessionLifecycle(deps as any),
    );

    await act(async () => {
      await result.current.startSession({
        hcpProfileId: "hcp-123",
        enableAvatar: false,
      });
    });

    expect(deps.voiceLive.connect).toHaveBeenCalledWith({
      hcpProfileId: "hcp-123",
      systemPrompt: undefined,
      vlInstanceId: undefined,
      enableAvatar: false,
      sessionId: undefined,
    });
  });

  it("startRecording callback sends audio when not muted", async () => {
    let recordingCallback: ((data: Float32Array) => void) | null = null;
    deps.audioHandler.startRecording.mockImplementation((cb: (data: Float32Array) => void) => {
      recordingCallback = cb;
    });

    const { result } = renderHook(() =>
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      useVoiceSessionLifecycle(deps as any),
    );

    await act(async () => {
      await result.current.startSession({});
    });

    expect(recordingCallback).not.toBeNull();
    // Call the recording callback with audio data
    recordingCallback!(new Float32Array([0.5, -0.5]));

    expect(deps.voiceLive.sendAudio).toHaveBeenCalledTimes(1);
  });

  it("startRecording callback skips audio when muted", async () => {
    deps.voiceLive.isMuted = true;
    let recordingCallback: ((data: Float32Array) => void) | null = null;
    deps.audioHandler.startRecording.mockImplementation((cb: (data: Float32Array) => void) => {
      recordingCallback = cb;
    });

    const { result } = renderHook(() =>
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      useVoiceSessionLifecycle(deps as any),
    );

    await act(async () => {
      await result.current.startSession({});
    });

    // Call the recording callback — should NOT send because muted
    recordingCallback!(new Float32Array([0.5]));

    expect(deps.voiceLive.sendAudio).not.toHaveBeenCalled();
  });

  it("sets avatarSdpCallbackRef before connecting", async () => {
    const { result } = renderHook(() =>
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      useVoiceSessionLifecycle(deps as any),
    );

    await act(async () => {
      await result.current.startSession({});
    });

    // avatarSdpCallbackRef should have been set to a function
    expect(typeof deps.voiceLive.avatarSdpCallbackRef.current).toBe("function");

    // Calling it should invoke avatarStream.handleServerSdp
    deps.voiceLive.avatarSdpCallbackRef.current!("test-server-sdp");
    expect(deps.avatarStream.handleServerSdp).toHaveBeenCalledWith("test-server-sdp");
  });

  it("disconnects and returns null when abort fires after connect but before avatar", async () => {
    // This tests the abort check at line 91 (after connect, before avatar)
    deps.voiceLive.connect.mockResolvedValue({
      avatarEnabled: true,
      model: "gpt-4o",
      iceServers: [],
    });

    const { result } = renderHook(() =>
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      useVoiceSessionLifecycle(deps as any),
    );

    // Manually abort right after connect resolves but before avatar connect
    let connectResolve: ((v: unknown) => void) | null = null;
    deps.voiceLive.connect.mockImplementation(() => new Promise((resolve) => { connectResolve = resolve; }));

    let startPromise: Promise<unknown>;
    await act(async () => {
      startPromise = result.current.startSession({});
    });

    // Stop the session (which aborts the controller)
    await act(async () => {
      await result.current.stopSession();
      // Now resolve connect — the abort check should fire
      connectResolve!({ avatarEnabled: true, model: "gpt-4o", iceServers: [] });
      await startPromise!;
    });

    // disconnect should have been called
    expect(deps.voiceLive.disconnect).toHaveBeenCalled();
  });

  it("sends avatar SDP via voiceLive.send when avatar connects", async () => {
    deps.voiceLive.connect.mockResolvedValue({
      avatarEnabled: true,
      model: "gpt-4o",
      iceServers: [],
    });

    // Capture the sendSdpOffer callback passed to avatarStream.connect
    let capturedSdpSender: ((sdp: string) => Promise<void>) | null = null;
    deps.avatarStream.connect.mockImplementation(
      async (_iceServers: unknown, sendSdpOffer: (sdp: string) => Promise<void>) => {
        capturedSdpSender = sendSdpOffer;
      },
    );

    const { result } = renderHook(() =>
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      useVoiceSessionLifecycle(deps as any),
    );

    await act(async () => {
      await result.current.startSession({});
    });

    // Invoke the captured SDP sender callback
    expect(capturedSdpSender).not.toBeNull();
    await capturedSdpSender!("test-sdp-offer");

    expect(deps.voiceLive.send).toHaveBeenCalledWith({
      type: "session.avatar.connect",
      client_sdp: "test-sdp-offer",
    });
  });
});
