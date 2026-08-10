import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useAvatarStream } from "./use-avatar-stream";

let mockPc: Record<string, unknown>;

beforeEach(() => {
  vi.clearAllMocks();
  vi.spyOn(HTMLAudioElement.prototype, "play").mockResolvedValue(undefined);

  mockPc = {
    addTransceiver: vi.fn(),
    createOffer: vi.fn().mockResolvedValue({ sdp: "mock-sdp", type: "offer" }),
    setLocalDescription: vi.fn(),
    setRemoteDescription: vi.fn(),
    close: vi.fn(),
    getStats: vi.fn().mockResolvedValue(new Map()),
    addEventListener: vi.fn(),
    createDataChannel: vi.fn(),
    localDescription: { sdp: "mock-sdp", type: "offer" },
    ontrack: null as ((event: unknown) => void) | null,
    onicecandidate: null as ((event: unknown) => void) | null,
  };
  vi.stubGlobal("RTCPeerConnection", vi.fn(() => mockPc));
});

afterEach(() => {
  vi.useRealTimers();
  // Clean up any audio elements appended to body by the hook
  document.querySelectorAll("audio").forEach((el) => el.remove());
});

/** Base64 encode SDP the way Azure expects it. */
function encodeAzureSdp(type: string, sdp: string): string {
  return btoa(JSON.stringify({ type, sdp }));
}

/**
 * Helper: creates sendSdpOffer that auto-resolves with base64-encoded server SDP.
 * triggerIceComplete waits for onicecandidate to be set, then fires it.
 */
function createMockSdpExchange(handleServerSdp: (sdp: string) => Promise<void>) {
  const sentSdps: string[] = [];
  const sendSdpOffer = vi.fn(async (sdp: string) => {
    sentSdps.push(sdp);
    // Simulate server answering with base64-encoded SDP
    const answerSdp = encodeAzureSdp("answer", "answer-sdp-raw");
    await handleServerSdp(answerSdp);
  });

  /** Fire onicecandidate(null) — must be called after handler is set. */
  function triggerIceComplete() {
    const handler = mockPc.onicecandidate as ((ev: unknown) => void) | null;
    handler?.({ candidate: null });
  }

  return { sendSdpOffer, sentSdps, triggerIceComplete };
}

/** Wait for onicecandidate to be assigned then trigger ICE complete. */
async function waitAndTriggerIce(triggerIceComplete: () => void) {
  await vi.waitFor(() => expect(mockPc.onicecandidate).toBeTruthy());
  triggerIceComplete();
}

/** Create a mock video element with play() method. */
function createMockVideoElement(): HTMLVideoElement {
  const video = document.createElement("video");
  // Mock play() since jsdom doesn't support it
  video.play = vi.fn().mockResolvedValue(undefined);
  return video;
}

describe("useAvatarStream", () => {
  it("initial state: isConnected false", () => {
    const ref = { current: null } as React.RefObject<HTMLVideoElement | null>;
    const { result } = renderHook(() => useAvatarStream(ref));
    expect(result.current.isConnected).toBe(false);
  });

  it("connect() creates RTCPeerConnection and does base64 SDP exchange", async () => {
    const video = createMockVideoElement();
    const ref = { current: video } as React.RefObject<HTMLVideoElement | null>;

    const { result } = renderHook(() => useAvatarStream(ref));
    const { sendSdpOffer, triggerIceComplete } = createMockSdpExchange(
      result.current.handleServerSdp,
    );

    await act(async () => {
      const connectPromise = result.current.connect([], sendSdpOffer);
      await waitAndTriggerIce(triggerIceComplete);
      await connectPromise;
    });

    expect(RTCPeerConnection).toHaveBeenCalled();
    expect(mockPc.createOffer).toHaveBeenCalled();
    expect(mockPc.setLocalDescription).toHaveBeenCalled();

    // SDP offer must be base64-encoded JSON (Azure format)
    const expectedEncodedSdp = encodeAzureSdp("offer", "mock-sdp");
    expect(sendSdpOffer).toHaveBeenCalledWith(expectedEncodedSdp);

    // Server SDP answer is decoded from base64 JSON to raw SDP
    expect(mockPc.setRemoteDescription).toHaveBeenCalledWith({
      type: "answer",
      sdp: "answer-sdp-raw",
    });
    expect(result.current.isConnected).toBe(true);
  });

  it("handleServerSdp decodes base64 JSON SDP answer", async () => {
    const video = createMockVideoElement();
    const ref = { current: video } as React.RefObject<HTMLVideoElement | null>;

    const { result } = renderHook(() => useAvatarStream(ref));
    const { sendSdpOffer, triggerIceComplete } = createMockSdpExchange(
      result.current.handleServerSdp,
    );

    await act(async () => {
      const p = result.current.connect([], sendSdpOffer);
      await waitAndTriggerIce(triggerIceComplete);
      await p;
    });

    expect(mockPc.setRemoteDescription).toHaveBeenCalledWith({
      type: "answer",
      sdp: "answer-sdp-raw",
    });
  });

  it("handleServerSdp falls back to raw SDP if not base64 JSON", async () => {
    const video = createMockVideoElement();
    const ref = { current: video } as React.RefObject<HTMLVideoElement | null>;

    const { result } = renderHook(() => useAvatarStream(ref));

    // Override: send raw SDP instead of base64
    const sendSdpOffer = vi.fn(async () => {
      await result.current.handleServerSdp("raw-sdp-answer");
    });

    await act(async () => {
      const p = result.current.connect([], sendSdpOffer);
      await vi.waitFor(() => expect(mockPc.onicecandidate).toBeTruthy());
      const handler = mockPc.onicecandidate as (ev: unknown) => void;
      handler({ candidate: null });
      await p;
    });

    expect(mockPc.setRemoteDescription).toHaveBeenCalledWith({
      type: "answer",
      sdp: "raw-sdp-answer",
    });
  });

  it("disconnect() closes connection and clears video srcObject", async () => {
    const video = createMockVideoElement();
    const ref = { current: video } as React.RefObject<HTMLVideoElement | null>;

    const { result } = renderHook(() => useAvatarStream(ref));
    const { sendSdpOffer, triggerIceComplete } = createMockSdpExchange(
      result.current.handleServerSdp,
    );

    await act(async () => {
      const p = result.current.connect([], sendSdpOffer);
      await waitAndTriggerIce(triggerIceComplete);
      await p;
    });

    act(() => {
      result.current.disconnect();
    });

    expect(mockPc.close).toHaveBeenCalled();
    expect(video.srcObject).toBeNull();
    expect(result.current.isConnected).toBe(false);
  });

  it("disconnect() when not connected is safe", () => {
    const video = createMockVideoElement();
    const ref = { current: video } as React.RefObject<HTMLVideoElement | null>;

    const { result } = renderHook(() => useAvatarStream(ref));

    act(() => {
      result.current.disconnect();
    });

    expect(video.srcObject).toBeNull();
    expect(result.current.isConnected).toBe(false);
  });

  it("disconnect() when video ref is null is safe", () => {
    const ref = { current: null } as React.RefObject<HTMLVideoElement | null>;

    const { result } = renderHook(() => useAvatarStream(ref));

    act(() => {
      result.current.disconnect();
    });

    expect(result.current.isConnected).toBe(false);
  });

  it("ontrack sets video srcObject and calls play()", async () => {
    const video = createMockVideoElement();
    const ref = { current: video } as React.RefObject<HTMLVideoElement | null>;

    const { result } = renderHook(() => useAvatarStream(ref));
    const { sendSdpOffer, triggerIceComplete } = createMockSdpExchange(
      result.current.handleServerSdp,
    );

    await act(async () => {
      const p = result.current.connect([], sendSdpOffer);
      await waitAndTriggerIce(triggerIceComplete);
      await p;
    });

    const ontrack = mockPc.ontrack as (event: unknown) => void;
    expect(ontrack).toBeTruthy();

    const mockMediaStream = {};
    act(() => {
      ontrack({
        track: { kind: "video" },
        streams: [mockMediaStream],
      });
    });

    // Video srcObject should be set on the ref element
    expect(video.srcObject).toBe(mockMediaStream);
    // play() should be called explicitly
    expect(video.play).toHaveBeenCalled();
  });

  it("ontrack creates hidden audio element on document.body", async () => {
    const video = createMockVideoElement();
    const ref = { current: video } as React.RefObject<HTMLVideoElement | null>;

    const { result } = renderHook(() => useAvatarStream(ref));
    const { sendSdpOffer, triggerIceComplete } = createMockSdpExchange(
      result.current.handleServerSdp,
    );

    await act(async () => {
      const p = result.current.connect([], sendSdpOffer);
      await waitAndTriggerIce(triggerIceComplete);
      await p;
    });

    const ontrack = mockPc.ontrack as (event: unknown) => void;
    const mockAudioStream = {};

    act(() => {
      ontrack({
        track: { kind: "audio" },
        streams: [mockAudioStream],
      });
    });

    // Audio element should be appended to document.body
    const audioEl = document.querySelector("audio");
    expect(audioEl).toBeTruthy();
    expect(audioEl?.srcObject).toBe(mockAudioStream);
    expect(audioEl?.autoplay).toBe(true);
    expect(audioEl?.style.display).toBe("none");
  });

  it("ontrack handles empty streams array using null", async () => {
    const video = createMockVideoElement();
    const ref = { current: video } as React.RefObject<HTMLVideoElement | null>;

    const { result } = renderHook(() => useAvatarStream(ref));
    const { sendSdpOffer, triggerIceComplete } = createMockSdpExchange(
      result.current.handleServerSdp,
    );

    await act(async () => {
      const p = result.current.connect([], sendSdpOffer);
      await waitAndTriggerIce(triggerIceComplete);
      await p;
    });

    const ontrack = mockPc.ontrack as (event: unknown) => void;

    act(() => {
      ontrack({ track: { kind: "video" }, streams: [] });
    });

    expect(video.srcObject).toBeNull();
  });

  it("ontrack does nothing for video when videoRef.current is null", async () => {
    const video = createMockVideoElement();
    const ref = { current: video } as React.MutableRefObject<HTMLVideoElement | null>;

    const { result } = renderHook(() => useAvatarStream(ref));
    const { sendSdpOffer, triggerIceComplete } = createMockSdpExchange(
      result.current.handleServerSdp,
    );

    await act(async () => {
      const p = result.current.connect([], sendSdpOffer);
      await waitAndTriggerIce(triggerIceComplete);
      await p;
    });

    const ontrack = mockPc.ontrack as (event: unknown) => void;
    ref.current = null;

    act(() => {
      ontrack({ track: { kind: "video" }, streams: [{}] });
    });
    // No error thrown, video not assigned
  });

  it("connect() adds recvonly transceivers", async () => {
    const video = createMockVideoElement();
    const ref = { current: video } as React.RefObject<HTMLVideoElement | null>;

    const { result } = renderHook(() => useAvatarStream(ref));
    const { sendSdpOffer, triggerIceComplete } = createMockSdpExchange(
      result.current.handleServerSdp,
    );

    await act(async () => {
      const p = result.current.connect([], sendSdpOffer);
      await waitAndTriggerIce(triggerIceComplete);
      await p;
    });

    expect(mockPc.addTransceiver).toHaveBeenCalledWith("video", {
      direction: "recvonly",
    });
    expect(mockPc.addTransceiver).toHaveBeenCalledWith("audio", {
      direction: "recvonly",
    });
  });

  it("connect() passes ICE servers and bundlePolicy to RTCPeerConnection", async () => {
    const video = createMockVideoElement();
    const ref = { current: video } as React.RefObject<HTMLVideoElement | null>;

    const iceServers: RTCIceServer[] = [
      { urls: "stun:stun.azure.com:3478" },
      { urls: "turn:turn.azure.com:3478", username: "user", credential: "pass" },
    ];

    const { result } = renderHook(() => useAvatarStream(ref));
    const { sendSdpOffer, triggerIceComplete } = createMockSdpExchange(
      result.current.handleServerSdp,
    );

    await act(async () => {
      const p = result.current.connect(iceServers, sendSdpOffer);
      await waitAndTriggerIce(triggerIceComplete);
      await p;
    });

    expect(RTCPeerConnection).toHaveBeenCalledWith({
      iceServers,
      bundlePolicy: "max-bundle",
    });
    expect(result.current.isConnected).toBe(true);
  });

  it("connect() with empty ICE servers uses undefined config", async () => {
    const video = createMockVideoElement();
    const ref = { current: video } as React.RefObject<HTMLVideoElement | null>;

    const { result } = renderHook(() => useAvatarStream(ref));
    const { sendSdpOffer, triggerIceComplete } = createMockSdpExchange(
      result.current.handleServerSdp,
    );

    await act(async () => {
      const p = result.current.connect([], sendSdpOffer);
      await waitAndTriggerIce(triggerIceComplete);
      await p;
    });

    expect(RTCPeerConnection).toHaveBeenCalledWith({
      iceServers: undefined,
      bundlePolicy: "max-bundle",
    });
    expect(result.current.isConnected).toBe(true);
  });

  it("connect() with Azure TURN ICE servers passes credentials", async () => {
    const video = createMockVideoElement();
    const ref = { current: video } as React.RefObject<HTMLVideoElement | null>;

    const azureIceServers: RTCIceServer[] = [
      {
        urls: "turn:relay.communication.microsoft.com:3478",
        username: "azure-turn-user",
        credential: "azure-turn-credential",
      },
    ];

    const { result } = renderHook(() => useAvatarStream(ref));
    const { sendSdpOffer, triggerIceComplete } = createMockSdpExchange(
      result.current.handleServerSdp,
    );

    await act(async () => {
      const p = result.current.connect(azureIceServers, sendSdpOffer);
      await waitAndTriggerIce(triggerIceComplete);
      await p;
    });

    expect(RTCPeerConnection).toHaveBeenCalledWith({
      iceServers: azureIceServers,
      bundlePolicy: "max-bundle",
    });
    expect(result.current.isConnected).toBe(true);
  });

  it("disconnect() removes dynamically created audio element from body", async () => {
    const video = createMockVideoElement();
    const ref = { current: video } as React.RefObject<HTMLVideoElement | null>;

    const { result } = renderHook(() => useAvatarStream(ref));
    const { sendSdpOffer, triggerIceComplete } = createMockSdpExchange(
      result.current.handleServerSdp,
    );

    await act(async () => {
      const p = result.current.connect([], sendSdpOffer);
      await waitAndTriggerIce(triggerIceComplete);
      await p;
    });

    // Simulate audio track arriving
    const ontrack = mockPc.ontrack as (event: unknown) => void;
    act(() => {
      ontrack({
        track: { kind: "audio" },
        streams: [{}],
      });
    });

    // Audio element should exist in body
    expect(document.querySelector("audio")).toBeTruthy();

    // Disconnect should remove it
    act(() => {
      result.current.disconnect();
    });

    expect(document.querySelector("audio")).toBeNull();
  });

  it("connect() resets video srcObject before new connection", async () => {
    const video = createMockVideoElement();
    video.srcObject = {} as MediaStream; // Simulate previous stream
    const ref = { current: video } as React.RefObject<HTMLVideoElement | null>;

    const { result } = renderHook(() => useAvatarStream(ref));
    const { sendSdpOffer, triggerIceComplete } = createMockSdpExchange(
      result.current.handleServerSdp,
    );

    await act(async () => {
      const p = result.current.connect([], sendSdpOffer);
      // At this point srcObject should be reset to null
      expect(video.srcObject).toBeNull();
      await waitAndTriggerIce(triggerIceComplete);
      await p;
    });
  });

  it("ICE candidate with a real candidate is logged (branch coverage)", async () => {
    const video = createMockVideoElement();
    const ref = { current: video } as React.RefObject<HTMLVideoElement | null>;

    const { result } = renderHook(() => useAvatarStream(ref));
    const { sendSdpOffer } = createMockSdpExchange(result.current.handleServerSdp);

    await act(async () => {
      const p = result.current.connect([], sendSdpOffer);
      // Wait for onicecandidate to be set
      await vi.waitFor(() => expect(mockPc.onicecandidate).toBeTruthy());
      const handler = mockPc.onicecandidate as (ev: unknown) => void;

      // Fire a real ICE candidate (not the null end-of-candidates signal)
      handler({ candidate: { type: "host", protocol: "udp" } });

      // Then fire the null candidate to complete
      handler({ candidate: null });
      await p;
    });

    expect(result.current.isConnected).toBe(true);
  });

  it("onicegatheringstatechange fires and resolves SDP offer when 'complete'", async () => {
    const video = createMockVideoElement();
    const ref = { current: video } as React.RefObject<HTMLVideoElement | null>;

    const { result } = renderHook(() => useAvatarStream(ref));
    const { sendSdpOffer } = createMockSdpExchange(result.current.handleServerSdp);

    await act(async () => {
      const p = result.current.connect([], sendSdpOffer);
      await vi.waitFor(() => expect(mockPc.onicegatheringstatechange).toBeTruthy());

      // Simulate iceGatheringState changing to "complete"
      Object.defineProperty(mockPc, "iceGatheringState", { value: "complete", writable: true });
      const handler = mockPc.onicegatheringstatechange as () => void;
      handler();

      await p;
    });

    expect(result.current.isConnected).toBe(true);
    expect(sendSdpOffer).toHaveBeenCalled();
  });

  it("ICE gathering timeout (8s) sends SDP if neither null-candidate nor statechange fired", async () => {
    vi.useFakeTimers();
    const video = createMockVideoElement();
    const ref = { current: video } as React.RefObject<HTMLVideoElement | null>;

    const { result } = renderHook(() => useAvatarStream(ref));
    const { sendSdpOffer } = createMockSdpExchange(result.current.handleServerSdp);

    let connectPromise: Promise<void>;
    await act(async () => {
      connectPromise = result.current.connect([], sendSdpOffer);
    });

    // Advance past the 8s ICE gathering timeout
    await act(async () => {
      vi.advanceTimersByTime(8500);
    });

    await act(async () => {
      await connectPromise!;
    });

    expect(sendSdpOffer).toHaveBeenCalled();
    expect(result.current.isConnected).toBe(true);
    vi.useRealTimers();
  });

  it("connectionState handlers are set on the peer connection", async () => {
    const video = createMockVideoElement();
    const ref = { current: video } as React.RefObject<HTMLVideoElement | null>;

    const { result } = renderHook(() => useAvatarStream(ref));
    const { sendSdpOffer, triggerIceComplete } = createMockSdpExchange(
      result.current.handleServerSdp,
    );

    await act(async () => {
      const p = result.current.connect([], sendSdpOffer);
      await waitAndTriggerIce(triggerIceComplete);
      await p;
    });

    // Verify connection state change handlers are set
    expect(mockPc.onconnectionstatechange).toBeTruthy();
    expect(mockPc.oniceconnectionstatechange).toBeTruthy();
    expect(mockPc.onsignalingstatechange).toBeTruthy();

    // Exercise the handlers without error (covers log branches)
    const connHandler = mockPc.onconnectionstatechange as () => void;
    const iceConnHandler = mockPc.oniceconnectionstatechange as () => void;
    const sigHandler = mockPc.onsignalingstatechange as () => void;

    // Simulate "connected"
    Object.defineProperty(mockPc, "connectionState", { value: "connected", writable: true, configurable: true });
    connHandler();

    // Simulate "failed"
    Object.defineProperty(mockPc, "connectionState", { value: "failed", writable: true, configurable: true });
    connHandler();

    // ICE connection states
    Object.defineProperty(mockPc, "iceConnectionState", { value: "checking", writable: true, configurable: true });
    iceConnHandler();

    Object.defineProperty(mockPc, "iceConnectionState", { value: "failed", writable: true, configurable: true });
    iceConnHandler();

    Object.defineProperty(mockPc, "iceConnectionState", { value: "disconnected", writable: true, configurable: true });
    iceConnHandler();

    // Signaling state
    Object.defineProperty(mockPc, "signalingState", { value: "stable", writable: true, configurable: true });
    sigHandler();
  });

  it("logs disconnected and closed connection diagnostics even when stats fail", async () => {
    const video = createMockVideoElement();
    const ref = { current: video } as React.RefObject<HTMLVideoElement | null>;
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    const error = new Error("stats unavailable");
    mockPc.getStats = vi.fn().mockRejectedValue(error);

    const { result } = renderHook(() => useAvatarStream(ref));
    const { sendSdpOffer, triggerIceComplete } = createMockSdpExchange(
      result.current.handleServerSdp,
    );
    await act(async () => {
      const pending = result.current.connect([], sendSdpOffer);
      await waitAndTriggerIce(triggerIceComplete);
      await pending;
      await Promise.resolve();
    });

    const connectionChanged = mockPc.onconnectionstatechange as () => void;
    for (const state of ["disconnected", "closed"]) {
      Object.defineProperty(mockPc, "connectionState", {
        value: state,
        writable: true,
        configurable: true,
      });
      connectionChanged();
    }
    await act(async () => {
      await Promise.resolve();
    });

    expect(warnSpy).toHaveBeenCalledWith(
      expect.stringContaining("[AvatarStream]"),
      expect.stringContaining("getStats() failed"),
      expect.any(String),
      error,
    );
  });

  it("stats interval is started after connect and cleared on disconnect", async () => {
    vi.useFakeTimers();
    const video = createMockVideoElement();
    const ref = { current: video } as React.RefObject<HTMLVideoElement | null>;

    const mockStats = new Map<string, unknown>();
    mockPc.getStats = vi.fn().mockResolvedValue(mockStats);

    const { result } = renderHook(() => useAvatarStream(ref));
    const { sendSdpOffer, triggerIceComplete } = createMockSdpExchange(
      result.current.handleServerSdp,
    );

    await act(async () => {
      const p = result.current.connect([], sendSdpOffer);
      await waitAndTriggerIce(triggerIceComplete);
      await p;
    });

    // Advance 5s to trigger the stats interval
    await act(async () => {
      vi.advanceTimersByTime(5500);
    });

    expect(mockPc.getStats).toHaveBeenCalled();

    // Disconnect should clear the interval
    act(() => {
      result.current.disconnect();
    });

    vi.useRealTimers();
  });

  it("stats interval processes inbound-rtp and candidate-pair reports", async () => {
    vi.useFakeTimers();
    const video = createMockVideoElement();
    const ref = { current: video } as React.RefObject<HTMLVideoElement | null>;

    const statsMap = new Map<string, Record<string, unknown>>();
    statsMap.set("video-rtp", {
      type: "inbound-rtp",
      kind: "video",
      framesPerSecond: 30,
      packetsLost: 0,
      packetsReceived: 100,
      jitter: 0.001,
      bytesReceived: 50000,
    });
    statsMap.set("audio-rtp", {
      type: "inbound-rtp",
      kind: "audio",
      packetsLost: 1,
      packetsReceived: 200,
      jitter: 0.002,
    });
    statsMap.set("pair-1", {
      type: "candidate-pair",
      state: "succeeded",
      currentRoundTripTime: 0.05,
    });

    mockPc.getStats = vi.fn().mockResolvedValue(statsMap);

    const { result } = renderHook(() => useAvatarStream(ref));
    const { sendSdpOffer, triggerIceComplete } = createMockSdpExchange(
      result.current.handleServerSdp,
    );

    await act(async () => {
      const p = result.current.connect([], sendSdpOffer);
      await waitAndTriggerIce(triggerIceComplete);
      await p;
    });

    await act(async () => {
      vi.advanceTimersByTime(5500);
      // Let the promise resolve
      await Promise.resolve();
    });

    expect(mockPc.getStats).toHaveBeenCalled();

    act(() => {
      result.current.disconnect();
    });
    vi.useRealTimers();
  });

  it("selects transport and fallback candidate pairs and reports byte stalls", async () => {
    vi.useFakeTimers();
    const video = createMockVideoElement();
    const ref = { current: video } as React.RefObject<HTMLVideoElement | null>;
    const selected = new Map<string, Record<string, unknown>>([
      ["video", {
        id: "video",
        type: "inbound-rtp",
        kind: "video",
        framesPerSecond: 30,
        packetsLost: 0,
        packetsReceived: 10,
        bytesReceived: 100,
      }],
      ["audio", {
        id: "audio",
        type: "inbound-rtp",
        kind: "audio",
        packetsLost: 0,
        packetsReceived: 10,
        bytesReceived: 50,
      }],
      ["local", {
        id: "local",
        type: "local-candidate",
        candidateType: "relay",
        protocol: "udp",
        networkType: "wifi",
        relayProtocol: "tls",
        address: "10.0.0.1",
        port: 3478,
      }],
      ["remote", {
        id: "remote",
        type: "remote-candidate",
        candidateType: "host",
        protocol: "tcp",
        ip: "10.0.0.2",
      }],
      ["selected", {
        id: "selected",
        type: "candidate-pair",
        state: "succeeded",
        nominated: true,
        localCandidateId: "local",
        remoteCandidateId: "remote",
        currentRoundTripTime: 0.1,
        availableIncomingBitrate: 1000,
        availableOutgoingBitrate: 500,
      }],
      ["transport", {
        id: "transport",
        type: "transport",
        selectedCandidatePairId: "selected",
        dtlsState: "connected",
        iceState: "connected",
      }],
    ]);
    const nominatedFallback = new Map<string, Record<string, unknown>>([
      ["nominated", {
        id: "nominated",
        type: "candidate-pair",
        state: "succeeded",
        nominated: true,
      }],
    ]);
    const succeededFallback = new Map<string, Record<string, unknown>>([
      ["failed", { id: "failed", type: "candidate-pair", state: "failed" }],
      ["succeeded", { id: "succeeded", type: "candidate-pair", state: "succeeded" }],
    ]);
    mockPc.getStats = vi.fn()
      .mockResolvedValueOnce(new Map())
      .mockResolvedValueOnce(selected)
      .mockResolvedValueOnce(selected)
      .mockResolvedValueOnce(nominatedFallback)
      .mockResolvedValueOnce(succeededFallback);

    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    const { result } = renderHook(() => useAvatarStream(ref));
    const { sendSdpOffer, triggerIceComplete } = createMockSdpExchange(
      result.current.handleServerSdp,
    );
    await act(async () => {
      const pending = result.current.connect([], sendSdpOffer);
      await waitAndTriggerIce(triggerIceComplete);
      await pending;
      await Promise.resolve();
    });

    for (let tick = 0; tick < 4; tick += 1) {
      await act(async () => {
        vi.advanceTimersByTime(5000);
        await Promise.resolve();
      });
    }

    expect(mockPc.getStats).toHaveBeenCalledTimes(5);
    expect(warnSpy).toHaveBeenCalledWith(
      expect.stringContaining("[AvatarStream]"),
      expect.stringContaining("video bytes stalled"),
    );
    expect(warnSpy).toHaveBeenCalledWith(
      expect.stringContaining("[AvatarStream]"),
      expect.stringContaining("audio bytes stalled"),
    );
    act(() => result.current.disconnect());
  });

  it("stats interval detects video packet loss anomaly (>5%)", async () => {
    vi.useFakeTimers();
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    const video = createMockVideoElement();
    const ref = { current: video } as React.RefObject<HTMLVideoElement | null>;

    const statsMap = new Map<string, Record<string, unknown>>();
    statsMap.set("video-rtp", {
      type: "inbound-rtp",
      kind: "video",
      framesPerSecond: 25,
      packetsLost: 10,
      packetsReceived: 90,
      jitter: 0.01,
      bytesReceived: 10000,
    });

    mockPc.getStats = vi.fn().mockResolvedValue(statsMap);

    const { result } = renderHook(() => useAvatarStream(ref));
    const { sendSdpOffer, triggerIceComplete } = createMockSdpExchange(
      result.current.handleServerSdp,
    );

    await act(async () => {
      const p = result.current.connect([], sendSdpOffer);
      await waitAndTriggerIce(triggerIceComplete);
      await p;
    });

    await act(async () => {
      vi.advanceTimersByTime(5500);
      await Promise.resolve();
    });

    expect(warnSpy).toHaveBeenCalledWith(
      expect.stringContaining("[AvatarStream]"),
      expect.stringContaining("ANOMALY: video packet loss"),
      expect.any(Number),
    );

    act(() => { result.current.disconnect(); });
    warnSpy.mockRestore();
    vi.useRealTimers();
  });

  it("stats interval detects low video fps anomaly (<10)", async () => {
    vi.useFakeTimers();
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    const video = createMockVideoElement();
    const ref = { current: video } as React.RefObject<HTMLVideoElement | null>;

    const statsMap = new Map<string, Record<string, unknown>>();
    statsMap.set("video-rtp", {
      type: "inbound-rtp",
      kind: "video",
      framesPerSecond: 5,
      packetsLost: 0,
      packetsReceived: 100,
      jitter: 0.01,
      bytesReceived: 5000,
    });

    mockPc.getStats = vi.fn().mockResolvedValue(statsMap);

    const { result } = renderHook(() => useAvatarStream(ref));
    const { sendSdpOffer, triggerIceComplete } = createMockSdpExchange(
      result.current.handleServerSdp,
    );

    await act(async () => {
      const p = result.current.connect([], sendSdpOffer);
      await waitAndTriggerIce(triggerIceComplete);
      await p;
    });

    await act(async () => {
      vi.advanceTimersByTime(5500);
      await Promise.resolve();
    });

    expect(warnSpy).toHaveBeenCalledWith(
      expect.stringContaining("[AvatarStream]"),
      expect.stringContaining("ANOMALY: video fps"),
      expect.any(Number),
    );

    act(() => { result.current.disconnect(); });
    warnSpy.mockRestore();
    vi.useRealTimers();
  });

  it("stats interval detects audio packet loss anomaly (>5%)", async () => {
    vi.useFakeTimers();
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    const video = createMockVideoElement();
    const ref = { current: video } as React.RefObject<HTMLVideoElement | null>;

    const statsMap = new Map<string, Record<string, unknown>>();
    statsMap.set("audio-rtp", {
      type: "inbound-rtp",
      kind: "audio",
      packetsLost: 15,
      packetsReceived: 85,
      jitter: 0.05,
    });

    mockPc.getStats = vi.fn().mockResolvedValue(statsMap);

    const { result } = renderHook(() => useAvatarStream(ref));
    const { sendSdpOffer, triggerIceComplete } = createMockSdpExchange(
      result.current.handleServerSdp,
    );

    await act(async () => {
      const p = result.current.connect([], sendSdpOffer);
      await waitAndTriggerIce(triggerIceComplete);
      await p;
    });

    await act(async () => {
      vi.advanceTimersByTime(5500);
      await Promise.resolve();
    });

    expect(warnSpy).toHaveBeenCalledWith(
      expect.stringContaining("[AvatarStream]"),
      expect.stringContaining("ANOMALY: audio packet loss"),
      expect.any(Number),
    );

    act(() => { result.current.disconnect(); });
    warnSpy.mockRestore();
    vi.useRealTimers();
  });

  it("ontrack video play() failure is caught gracefully", async () => {
    const video = createMockVideoElement();
    (video.play as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new Error("play() not allowed"),
    );
    const ref = { current: video } as React.RefObject<HTMLVideoElement | null>;

    const { result } = renderHook(() => useAvatarStream(ref));
    const { sendSdpOffer, triggerIceComplete } = createMockSdpExchange(
      result.current.handleServerSdp,
    );

    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});

    await act(async () => {
      const p = result.current.connect([], sendSdpOffer);
      await waitAndTriggerIce(triggerIceComplete);
      await p;
    });

    const ontrack = mockPc.ontrack as (event: unknown) => void;
    await act(async () => {
      ontrack({
        track: { kind: "video" },
        streams: [{}],
      });
      // Wait for the play() rejection to be handled
      await new Promise((r) => setTimeout(r, 0));
    });

    expect(warnSpy).toHaveBeenCalledWith(
      expect.stringContaining("[AvatarStream]"),
      expect.stringContaining("Video play() failed"),
      expect.any(Error),
    );
    warnSpy.mockRestore();
  });

  it("ontrack audio handles an empty stream and play rejection", async () => {
    const video = createMockVideoElement();
    const ref = { current: video } as React.RefObject<HTMLVideoElement | null>;
    const error = new Error("audio autoplay blocked");
    vi.spyOn(HTMLAudioElement.prototype, "play").mockRejectedValueOnce(error);
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});

    const { result } = renderHook(() => useAvatarStream(ref));
    const { sendSdpOffer, triggerIceComplete } = createMockSdpExchange(
      result.current.handleServerSdp,
    );
    await act(async () => {
      const pending = result.current.connect([], sendSdpOffer);
      await waitAndTriggerIce(triggerIceComplete);
      await pending;
    });

    const ontrack = mockPc.ontrack as (event: unknown) => void;
    await act(async () => {
      ontrack({ track: { kind: "audio", readyState: "live" }, streams: [] });
      await Promise.resolve();
    });

    expect(document.querySelector("audio")?.srcObject).toBeNull();
    expect(warnSpy).toHaveBeenCalledWith(
      expect.stringContaining("[AvatarStream]"),
      expect.stringContaining("Audio play() failed"),
      error,
    );
  });
});
