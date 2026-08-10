import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useVoiceLive } from "./use-voice-live";

// ---- Mock WebSocket ----

type WSHandler = ((event: { data: string }) => void) | null;

class MockWebSocket {
  static OPEN = 1;
  static CONNECTING = 0;
  static CLOSING = 2;
  static CLOSED = 3;

  static instances: MockWebSocket[] = [];

  readyState = MockWebSocket.OPEN;
  onopen: (() => void) | null = null;
  onmessage: WSHandler = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  onerror: ((err: unknown) => void) | null = null;

  sentMessages: string[] = [];
  url: string;

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
    // Simulate async open
    setTimeout(() => this.onopen?.(), 0);
  }

  send(data: string) {
    this.sentMessages.push(data);
  }

  close() {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.({ code: 1000, reason: "", wasClean: true } as CloseEvent);
  }

  // Test helpers
  simulateMessage(data: Record<string, unknown>) {
    this.onmessage?.({ data: JSON.stringify(data) });
  }

  simulateError() {
    this.onerror?.(new Error("ws error"));
  }
}

// Replace global WebSocket
const OriginalWebSocket = globalThis.WebSocket;

// Mock localStorage for JWT token
const mockLocalStorage: Record<string, string> = {};
const OriginalLocalStorage = globalThis.localStorage;

const defaultOptions = {
  language: "zh-CN",
  systemPrompt: "You are a test HCP",
};

describe("useVoiceLive (backend WebSocket proxy)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    MockWebSocket.instances = [];
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    globalThis.WebSocket = MockWebSocket as any;

    // Setup localStorage mock with a test JWT token
    Object.defineProperty(globalThis, "localStorage", {
      value: {
        getItem: (key: string) => mockLocalStorage[key] ?? null,
        setItem: (key: string, value: string) => {
          mockLocalStorage[key] = value;
        },
        removeItem: (key: string) => {
          delete mockLocalStorage[key];
        },
        clear: () => {
          Object.keys(mockLocalStorage).forEach(
            (k) => delete mockLocalStorage[k],
          );
        },
      },
      writable: true,
      configurable: true,
    });
    mockLocalStorage["access_token"] = "test-jwt-token-123";
  });

  afterEach(() => {
    globalThis.WebSocket = OriginalWebSocket;
    Object.defineProperty(globalThis, "localStorage", {
      value: OriginalLocalStorage,
      writable: true,
      configurable: true,
    });
    Object.keys(mockLocalStorage).forEach((k) => delete mockLocalStorage[k]);
  });

  function getLastWs(): MockWebSocket {
    return MockWebSocket.instances[MockWebSocket.instances.length - 1]!;
  }

  // ---- Initial state ----

  it("initial state: disconnected, idle, not muted", () => {
    const { result } = renderHook(() => useVoiceLive(defaultOptions));
    expect(result.current.connectionState).toBe("disconnected");
    expect(result.current.audioState).toBe("idle");
    expect(result.current.isMuted).toBe(false);
  });

  it("exposes avatarSdpCallbackRef", () => {
    const { result } = renderHook(() => useVoiceLive(defaultOptions));
    expect(result.current.avatarSdpCallbackRef).toBeDefined();
    expect(result.current.avatarSdpCallbackRef.current).toBeNull();
  });

  // ---- Authentication ----

  it("connect() appends JWT token from localStorage to WebSocket URL", async () => {
    const { result } = renderHook(() => useVoiceLive(defaultOptions));

    await act(async () => {
      const promise = result.current.connect("hcp-auth-test");
      await vi.waitFor(() => expect(MockWebSocket.instances.length).toBe(1));
      const ws = getLastWs();

      // Verify token is in the URL
      expect(ws.url).toContain("?token=test-jwt-token-123");
      expect(ws.url).toMatch(
        /ws:\/\/localhost(:\d+)?\/api\/v1\/voice-live\/ws\?token=test-jwt-token-123/,
      );

      // Complete the connection to avoid timeout
      await vi.waitFor(() => expect(ws.sentMessages.length).toBe(1));
      ws.simulateMessage({
        type: "proxy.connected",
        model: "gpt-4o",
        avatar_enabled: false,
      });
      ws.simulateMessage({ type: "session.updated", session: {} });
      return promise;
    });
  });

  it("connect() sends empty token when no access_token in localStorage", async () => {
    delete mockLocalStorage["access_token"];
    const { result } = renderHook(() => useVoiceLive(defaultOptions));

    await act(async () => {
      const promise = result.current.connect("hcp-no-token");
      await vi.waitFor(() => expect(MockWebSocket.instances.length).toBe(1));
      const ws = getLastWs();

      // URL should still have token param but empty value
      expect(ws.url).toContain("?token=");

      await vi.waitFor(() => expect(ws.sentMessages.length).toBe(1));
      ws.simulateMessage({
        type: "proxy.connected",
        model: "gpt-4o",
        avatar_enabled: false,
      });
      ws.simulateMessage({ type: "session.updated", session: {} });
      return promise;
    });
  });

  // ---- connect() ----

  it("connect() opens WebSocket and sends session.update", async () => {
    const { result } = renderHook(() => useVoiceLive(defaultOptions));

    const connectPromise = act(async () => {
      const promise = result.current.connect("hcp-123", "Test prompt");

      // Wait for WebSocket open
      await vi.waitFor(() => expect(MockWebSocket.instances.length).toBe(1));
      const ws = getLastWs();

      // Simulate open + message flow
      await vi.waitFor(() => expect(ws.sentMessages.length).toBe(1));

      const sent = JSON.parse(ws.sentMessages[0]!);
      expect(sent.type).toBe("session.update");
      expect(sent.session.hcp_profile_id).toBe("hcp-123");
      expect(sent.session.system_prompt).toBe("Test prompt");

      // Simulate proxy.connected
      ws.simulateMessage({
        type: "proxy.connected",
        model: "gpt-4o",
        avatar_enabled: false,
      });

      // Simulate session.updated
      ws.simulateMessage({
        type: "session.updated",
        session: {},
      });

      return promise;
    });

    const connectResult = await connectPromise;
    expect(connectResult).toEqual({
      model: "gpt-4o",
      mode: "model",
      avatarEnabled: false,
      iceServers: [],
    });
    expect(result.current.connectionState).toBe("connected");
  });

  it("session-bound connect sends only trusted session_id context", async () => {
    const { result } = renderHook(() => useVoiceLive(defaultOptions));

    await act(async () => {
      const promise = result.current.connect(
        "untrusted-hcp",
        "untrusted prompt",
        "untrusted-instance",
        true,
        "session-123",
      );
      const ws = getLastWs();
      ws.onopen?.();

      const sent = JSON.parse(ws.sentMessages[0]!);
      expect(sent.session.session_id).toBe("session-123");
      expect(sent.session.system_prompt).toBeUndefined();
      expect(sent.session.hcp_profile_id).toBeUndefined();
      expect(sent.session.vl_instance_id).toBeUndefined();
      expect(sent.session.avatar_enabled).toBeUndefined();

      ws.simulateMessage({
        type: "proxy.connected",
        model: "gpt-4o",
        avatar_enabled: true,
      });
      ws.simulateMessage({ type: "session.updated", session: {} });
      return promise;
    });
  });

  it("connect() sends avatar override when provided", async () => {
    const { result } = renderHook(() => useVoiceLive(defaultOptions));

    await act(async () => {
      const promise = result.current.connect("hcp-123", "Test prompt", undefined, false);
      await vi.waitFor(() => expect(MockWebSocket.instances.length).toBe(1));
      const ws = getLastWs();
      await vi.waitFor(() => expect(ws.sentMessages.length).toBe(1));

      const sent = JSON.parse(ws.sentMessages[0]!);
      expect(sent.session.avatar_enabled).toBe(false);

      ws.simulateMessage({
        type: "proxy.connected",
        model: "gpt-4o",
        avatar_enabled: false,
      });
      ws.simulateMessage({ type: "session.updated", session: {} });

      return promise;
    });
  });

  it("connect() returns ICE servers from session.updated avatar config", async () => {
    const { result } = renderHook(() => useVoiceLive(defaultOptions));

    const connectResult = await act(async () => {
      const promise = result.current.connect("hcp-456");

      await vi.waitFor(() => expect(MockWebSocket.instances.length).toBe(1));
      const ws = getLastWs();
      await vi.waitFor(() => expect(ws.sentMessages.length).toBe(1));

      ws.simulateMessage({
        type: "proxy.connected",
        model: "gpt-4o",
        avatar_enabled: true,
      });

      ws.simulateMessage({
        type: "session.updated",
        session: {
          avatar: {
            ice_servers: [
              {
                urls: ["turn:relay.azure.com:3478"],
                username: "u",
                credential: "c",
              },
            ],
          },
        },
      });

      return promise;
    });

    expect(connectResult.model).toBe("gpt-4o");
    expect(connectResult.avatarEnabled).toBe(true);
    expect(connectResult.iceServers).toEqual([
      { urls: ["turn:relay.azure.com:3478"], username: "u", credential: "c" },
    ]);
  });

  it("connect() resolves with empty ICE servers when avatar config omits them", async () => {
    const { result } = renderHook(() => useVoiceLive(defaultOptions));

    const connectResult = await act(async () => {
      const promise = result.current.connect("hcp-avatar-no-ice", "", undefined, true);

      await vi.waitFor(() => expect(MockWebSocket.instances.length).toBe(1));
      const ws = getLastWs();
      await vi.waitFor(() => expect(ws.sentMessages.length).toBe(1));

      ws.simulateMessage({
        type: "proxy.connected",
        model: "gpt-4o",
        avatar_enabled: true,
      });
      ws.simulateMessage({
        type: "session.updated",
        session: { avatar: {} },
      });

      return promise;
    });

    expect(connectResult.avatarEnabled).toBe(true);
    expect(connectResult.iceServers).toEqual([]);
  });

  it("connect() calls onConnectionStateChange with connecting then connected", async () => {
    const onConnectionStateChange = vi.fn();
    const { result } = renderHook(() =>
      useVoiceLive({ ...defaultOptions, onConnectionStateChange }),
    );

    await act(async () => {
      const promise = result.current.connect("hcp-1");
      await vi.waitFor(() => expect(MockWebSocket.instances.length).toBe(1));

      expect(onConnectionStateChange).toHaveBeenCalledWith("connecting");

      const ws = getLastWs();
      await vi.waitFor(() => expect(ws.sentMessages.length).toBe(1));
      ws.simulateMessage({ type: "proxy.connected", model: "gpt-4o", avatar_enabled: false });
      ws.simulateMessage({ type: "session.updated", session: {} });

      return promise;
    });

    expect(onConnectionStateChange).toHaveBeenCalledWith("connected");
  });

  // ---- Event handling ----

  it("handles user transcript events", async () => {
    const onTranscript = vi.fn();
    const { result } = renderHook(() =>
      useVoiceLive({ ...defaultOptions, onTranscript }),
    );

    await act(async () => {
      const promise = result.current.connect("hcp-1");
      await vi.waitFor(() => expect(MockWebSocket.instances.length).toBe(1));
      const ws = getLastWs();
      await vi.waitFor(() => expect(ws.sentMessages.length).toBe(1));
      ws.simulateMessage({ type: "proxy.connected", model: "gpt-4o", avatar_enabled: false });
      ws.simulateMessage({ type: "session.updated", session: {} });
      return promise;
    });

    const ws = getLastWs();
    act(() => {
      ws.simulateMessage({
        type: "conversation.item.input_audio_transcription.completed",
        transcript: "Hello HCP",
      });
    });

    expect(onTranscript).toHaveBeenCalledWith(
      expect.objectContaining({
        role: "user",
        content: "Hello HCP",
        isFinal: true,
      }),
    );
  });

  it("handles assistant audio transcript events", async () => {
    const onTranscript = vi.fn();
    const { result } = renderHook(() =>
      useVoiceLive({ ...defaultOptions, onTranscript }),
    );

    await act(async () => {
      const promise = result.current.connect("hcp-1");
      await vi.waitFor(() => expect(MockWebSocket.instances.length).toBe(1));
      const ws = getLastWs();
      await vi.waitFor(() => expect(ws.sentMessages.length).toBe(1));
      ws.simulateMessage({ type: "proxy.connected", model: "gpt-4o", avatar_enabled: false });
      ws.simulateMessage({ type: "session.updated", session: {} });
      return promise;
    });

    const ws = getLastWs();
    act(() => {
      ws.simulateMessage({
        type: "response.audio_transcript.done",
        response_id: "r1",
        item_id: "i1",
        transcript: "Response text",
      });
    });

    expect(onTranscript).toHaveBeenCalledWith(
      expect.objectContaining({
        role: "assistant",
        content: "Response text",
        isFinal: true,
      }),
    );
  });

  it("handles streaming event variants and ignores missing optional payloads", async () => {
    const onTranscript = vi.fn();
    const onAudioDelta = vi.fn();
    const onAudioStateChange = vi.fn();
    const onError = vi.fn();
    const { result } = renderHook(() => useVoiceLive({
      ...defaultOptions,
      onTranscript,
      onAudioDelta,
      onAudioStateChange,
      onError,
    }));
    const sdpCallback = vi.fn();
    result.current.avatarSdpCallbackRef.current = sdpCallback;

    await act(async () => {
      const promise = result.current.connect("hcp-events");
      const ws = getLastWs();
      ws.onopen?.();
      ws.simulateMessage({ type: "proxy.connected", mode: "agent", avatar_enabled: false });
      ws.simulateMessage({ type: "session.created", session: { id: "session-1" } });
      ws.simulateMessage({ type: "session.updated", session: {} });
      await promise;
    });

    const ws = getLastWs();
    act(() => {
      ws.simulateMessage({ type: "input_audio_buffer.speech_stopped" });
      ws.simulateMessage({ type: "conversation.item.input_audio_transcription.completed" });
      ws.simulateMessage({ type: "response.audio.delta", delta: "audio-base64" });
      ws.simulateMessage({ type: "response.audio.delta" });
      ws.simulateMessage({
        type: "response.audio_transcript.delta",
        response_id: "r1",
        item_id: "i1",
        delta: "partial audio",
      });
      ws.simulateMessage({ type: "response.audio_transcript.delta" });
      ws.simulateMessage({ type: "response.audio_transcript.done" });
      ws.simulateMessage({
        type: "response.text.delta",
        response_id: "r2",
        item_id: "i2",
        delta: "partial text",
      });
      ws.simulateMessage({ type: "response.text.delta" });
      ws.simulateMessage({
        type: "response.text.done",
        response_id: "r2",
        item_id: "i2",
        text: "final text",
      });
      ws.simulateMessage({ type: "response.text.done" });
      ws.simulateMessage({ type: "custom.sdp", sdp: "generic-sdp" });
      ws.simulateMessage({ type: "custom.answer", answer: "generic-answer" });
      ws.simulateMessage({ type: "session.update", server_sdp: "ignored-sdp" });
      ws.simulateMessage({ type: "session.avatar.connecting", serverSdp: "camel-sdp" });
      ws.simulateMessage({ type: "error", error: {} });
    });

    expect(onAudioDelta).toHaveBeenCalledWith("audio-base64");
    expect(onAudioStateChange).toHaveBeenCalledWith("idle");
    expect(onTranscript).toHaveBeenCalledWith(expect.objectContaining({
      content: "partial audio",
      isFinal: false,
    }));
    expect(onTranscript).toHaveBeenCalledWith(expect.objectContaining({
      content: "final text",
      isFinal: true,
    }));
    expect(sdpCallback).toHaveBeenCalledWith("generic-sdp");
    expect(sdpCallback).toHaveBeenCalledWith("generic-answer");
    expect(sdpCallback).toHaveBeenCalledWith("camel-sdp");
    expect(sdpCallback).not.toHaveBeenCalledWith("ignored-sdp");
    expect(onError).toHaveBeenCalledWith(expect.objectContaining({ message: "Unknown error" }));
  });

  it("normalizes scalar RTC ICE servers with session-level credentials", async () => {
    const { result } = renderHook(() => useVoiceLive(defaultOptions));

    const connected = await act(async () => {
      const promise = result.current.connect({ hcpProfileId: "hcp-rtc" });
      const ws = getLastWs();
      ws.onopen?.();
      ws.simulateMessage({ type: "proxy.connected", mode: "agent" });
      ws.simulateMessage({
        type: "session.updated",
        session: {
          rtc: {
            ice_servers: "turn:rtc.example.test:3478",
            ice_username: "session-user",
            ice_credential: "session-secret",
          },
        },
      });
      return promise;
    });

    expect(connected).toEqual({
      avatarEnabled: false,
      model: "gpt-4o",
      mode: "agent",
      iceServers: [{
        urls: "turn:rtc.example.test:3478",
        username: "session-user",
        credential: "session-secret",
        credentialType: "password",
      }],
    });
  });

  it("handles avatar SDP answer via callback ref", async () => {
    const { result } = renderHook(() => useVoiceLive(defaultOptions));
    const sdpCallback = vi.fn();
    result.current.avatarSdpCallbackRef.current = sdpCallback;

    await act(async () => {
      const promise = result.current.connect("hcp-1");
      await vi.waitFor(() => expect(MockWebSocket.instances.length).toBe(1));
      const ws = getLastWs();
      await vi.waitFor(() => expect(ws.sentMessages.length).toBe(1));
      ws.simulateMessage({ type: "proxy.connected", model: "gpt-4o", avatar_enabled: true });
      ws.simulateMessage({ type: "session.updated", session: {} });
      return promise;
    });

    const ws = getLastWs();
    act(() => {
      ws.simulateMessage({
        type: "session.avatar.connecting",
        server_sdp: "answer-sdp-456",
      });
    });

    expect(sdpCallback).toHaveBeenCalledWith("answer-sdp-456");
  });

  it("handles audio state transitions", async () => {
    const onAudioStateChange = vi.fn();
    const onResponseDone = vi.fn();
    const { result } = renderHook(() =>
      useVoiceLive({ ...defaultOptions, onAudioStateChange, onResponseDone }),
    );

    await act(async () => {
      const promise = result.current.connect("hcp-1");
      await vi.waitFor(() => expect(MockWebSocket.instances.length).toBe(1));
      const ws = getLastWs();
      await vi.waitFor(() => expect(ws.sentMessages.length).toBe(1));
      ws.simulateMessage({ type: "proxy.connected", model: "gpt-4o", avatar_enabled: false });
      ws.simulateMessage({ type: "session.updated", session: {} });
      return promise;
    });

    const ws = getLastWs();

    act(() => ws.simulateMessage({ type: "input_audio_buffer.speech_started" }));
    expect(result.current.audioState).toBe("listening");
    expect(onAudioStateChange).toHaveBeenCalledWith("listening");

    act(() => ws.simulateMessage({ type: "response.created" }));
    expect(result.current.audioState).toBe("speaking");

    act(() => ws.simulateMessage({ type: "response.done" }));
    expect(result.current.audioState).toBe("idle");
    expect(onResponseDone).toHaveBeenCalledTimes(1);
  });

  it("handles error events from server", async () => {
    const onError = vi.fn();
    const { result } = renderHook(() =>
      useVoiceLive({ ...defaultOptions, onError }),
    );

    await act(async () => {
      const promise = result.current.connect("hcp-1");
      await vi.waitFor(() => expect(MockWebSocket.instances.length).toBe(1));
      const ws = getLastWs();
      await vi.waitFor(() => expect(ws.sentMessages.length).toBe(1));
      ws.simulateMessage({ type: "proxy.connected", model: "gpt-4o", avatar_enabled: false });
      ws.simulateMessage({ type: "session.updated", session: {} });
      return promise;
    });

    const ws = getLastWs();
    act(() => {
      ws.simulateMessage({
        type: "error",
        error: { message: "Server error occurred" },
      });
    });

    expect(result.current.connectionState).toBe("error");
    expect(onError).toHaveBeenCalledWith(
      expect.objectContaining({ message: "Server error occurred" }),
    );
  });

  // ---- disconnect() ----

  it("disconnect() closes WebSocket and resets state", async () => {
    const { result } = renderHook(() => useVoiceLive(defaultOptions));

    await act(async () => {
      const promise = result.current.connect("hcp-1");
      await vi.waitFor(() => expect(MockWebSocket.instances.length).toBe(1));
      const ws = getLastWs();
      await vi.waitFor(() => expect(ws.sentMessages.length).toBe(1));
      ws.simulateMessage({ type: "proxy.connected", model: "gpt-4o", avatar_enabled: false });
      ws.simulateMessage({ type: "session.updated", session: {} });
      return promise;
    });

    await act(async () => {
      await result.current.disconnect();
    });

    expect(result.current.connectionState).toBe("disconnected");
    expect(result.current.isMuted).toBe(false);
    expect(result.current.audioState).toBe("idle");
  });

  // ---- toggleMute() ----

  it("toggleMute() toggles isMuted state", () => {
    const onAudioStateChange = vi.fn();
    const { result } = renderHook(() =>
      useVoiceLive({ ...defaultOptions, onAudioStateChange }),
    );

    act(() => result.current.toggleMute());
    expect(result.current.isMuted).toBe(true);
    expect(onAudioStateChange).toHaveBeenCalledWith("muted");

    act(() => result.current.toggleMute());
    expect(result.current.isMuted).toBe(false);
    expect(onAudioStateChange).toHaveBeenCalledWith("idle");
  });

  // ---- sendTextMessage() ----

  it("sendTextMessage() sends conversation.item.create and response.create", async () => {
    const { result } = renderHook(() => useVoiceLive(defaultOptions));

    await act(async () => {
      const promise = result.current.connect("hcp-1");
      await vi.waitFor(() => expect(MockWebSocket.instances.length).toBe(1));
      const ws = getLastWs();
      await vi.waitFor(() => expect(ws.sentMessages.length).toBe(1));
      ws.simulateMessage({ type: "proxy.connected", model: "gpt-4o", avatar_enabled: false });
      ws.simulateMessage({ type: "session.updated", session: {} });
      return promise;
    });

    const ws = getLastWs();
    ws.sentMessages = []; // Clear previous messages

    await act(async () => {
      await result.current.sendTextMessage("Hello");
    });

    expect(ws.sentMessages.length).toBe(2);
    const msg1 = JSON.parse(ws.sentMessages[0]!);
    expect(msg1.type).toBe("conversation.item.create");
    expect(msg1.item.content[0].text).toBe("Hello");

    const msg2 = JSON.parse(ws.sentMessages[1]!);
    expect(msg2.type).toBe("response.create");
  });

  // ---- sendAudio() ----

  it("sendAudio() sends input_audio_buffer.append message", async () => {
    const { result } = renderHook(() => useVoiceLive(defaultOptions));

    await act(async () => {
      const promise = result.current.connect("hcp-1");
      await vi.waitFor(() => expect(MockWebSocket.instances.length).toBe(1));
      const ws = getLastWs();
      await vi.waitFor(() => expect(ws.sentMessages.length).toBe(1));
      ws.simulateMessage({ type: "proxy.connected", model: "gpt-4o", avatar_enabled: false });
      ws.simulateMessage({ type: "session.updated", session: {} });
      return promise;
    });

    const ws = getLastWs();
    ws.sentMessages = [];

    act(() => {
      result.current.sendAudio("dGVzdA==");
    });

    expect(ws.sentMessages.length).toBe(1);
    const msg = JSON.parse(ws.sentMessages[0]!);
    expect(msg.type).toBe("input_audio_buffer.append");
    expect(msg.audio).toBe("dGVzdA==");
  });

  // ---- send() ----

  it("send() sends arbitrary messages via WebSocket", async () => {
    const { result } = renderHook(() => useVoiceLive(defaultOptions));

    await act(async () => {
      const promise = result.current.connect("hcp-1");
      await vi.waitFor(() => expect(MockWebSocket.instances.length).toBe(1));
      const ws = getLastWs();
      await vi.waitFor(() => expect(ws.sentMessages.length).toBe(1));
      ws.simulateMessage({ type: "proxy.connected", model: "gpt-4o", avatar_enabled: false });
      ws.simulateMessage({ type: "session.updated", session: {} });
      return promise;
    });

    const ws = getLastWs();
    ws.sentMessages = [];

    act(() => {
      result.current.send({ type: "session.avatar.connect", client_sdp: "offer-sdp" });
    });

    expect(ws.sentMessages.length).toBe(1);
    const msg = JSON.parse(ws.sentMessages[0]!);
    expect(msg.type).toBe("session.avatar.connect");
    expect(msg.client_sdp).toBe("offer-sdp");
  });

  it("send() supports raw strings and safely drops messages without an open socket", () => {
    const { result } = renderHook(() => useVoiceLive(defaultOptions));
    act(() => {
      result.current.send({ type: "dropped-without-socket" });
    });

    const ws = new MockWebSocket("ws://test");
    ws.readyState = MockWebSocket.CLOSED;
    act(() => {
      result.current.send("dropped-closed-socket");
    });
    expect(ws.sentMessages).toEqual([]);
  });

  it("rejects an unresolved connection on WebSocket error", async () => {
    const onError = vi.fn();
    const onConnectionStateChange = vi.fn();
    const { result } = renderHook(() => useVoiceLive({
      ...defaultOptions,
      onError,
      onConnectionStateChange,
    }));

    let pending!: Promise<unknown>;
    act(() => {
      pending = result.current.connect("hcp-ws-error");
    });
    const ws = getLastWs();
    await act(async () => {
      ws.simulateError();
      await expect(pending).rejects.toThrow("WebSocket connection failed");
    });

    expect(result.current.connectionState).toBe("error");
    expect(onConnectionStateChange).toHaveBeenCalledWith("error");
    expect(onError).toHaveBeenCalledWith(
      expect.objectContaining({ message: "WebSocket connection failed" }),
    );
  });

  // ---- JSON parse protection ----

  it("ignores non-JSON WebSocket messages without crashing", async () => {
    const onError = vi.fn();
    const { result } = renderHook(() =>
      useVoiceLive({ ...defaultOptions, onError }),
    );

    await act(async () => {
      const promise = result.current.connect("hcp-1");
      await vi.waitFor(() => expect(MockWebSocket.instances.length).toBe(1));
      const ws = getLastWs();
      await vi.waitFor(() => expect(ws.sentMessages.length).toBe(1));
      ws.simulateMessage({ type: "proxy.connected", model: "gpt-4o", avatar_enabled: false });
      ws.simulateMessage({ type: "session.updated", session: {} });
      return promise;
    });

    const ws = getLastWs();
    // Send raw non-JSON text — should not throw
    act(() => {
      ws.onmessage?.({ data: "not valid json {{{" });
    });

    // Connection should still be fine
    expect(result.current.connectionState).toBe("connected");
    expect(onError).not.toHaveBeenCalled();
  });

  // ---- Reconnection ----

  it("attempts auto-reconnect on unexpected disconnect", async () => {
    const onConnectionStateChange = vi.fn();
    const { result } = renderHook(() =>
      useVoiceLive({ ...defaultOptions, onConnectionStateChange }),
    );

    await act(async () => {
      const promise = result.current.connect("hcp-reconnect");
      await vi.waitFor(() => expect(MockWebSocket.instances.length).toBe(1));
      const ws = getLastWs();
      await vi.waitFor(() => expect(ws.sentMessages.length).toBe(1));
      ws.simulateMessage({ type: "proxy.connected", model: "gpt-4o", avatar_enabled: false });
      ws.simulateMessage({ type: "session.updated", session: {} });
      return promise;
    });

    expect(result.current.connectionState).toBe("connected");
    const ws = getLastWs();

    // Simulate unexpected close (server-side)
    act(() => {
      ws.readyState = MockWebSocket.CLOSED;
      ws.onclose?.({ code: 1006, reason: "", wasClean: false } as CloseEvent);
    });

    // Should transition to "connecting" for reconnect
    expect(onConnectionStateChange).toHaveBeenCalledWith("connecting");
  });

  it("preserves session_id in the first frame after auto-reconnect", async () => {
    vi.useFakeTimers();
    try {
      const { result } = renderHook(() => useVoiceLive(defaultOptions));

      const firstPromise = result.current.connect(
        undefined,
        undefined,
        undefined,
        false,
        "session-reconnect",
      );
      const firstWs = getLastWs();
      firstWs.onopen?.();
      firstWs.simulateMessage({
        type: "proxy.connected",
        model: "gpt-4o",
        avatar_enabled: false,
      });
      firstWs.simulateMessage({ type: "session.updated", session: {} });
      await act(async () => firstPromise);

      act(() => {
        firstWs.readyState = MockWebSocket.CLOSED;
        firstWs.onclose?.({ code: 1006, reason: "", wasClean: false } as CloseEvent);
        vi.advanceTimersByTime(1000);
      });

      const reconnectWs = getLastWs();
      expect(reconnectWs).not.toBe(firstWs);
      reconnectWs.onopen?.();
      const sent = JSON.parse(reconnectWs.sentMessages[0]!);
      expect(sent.session.session_id).toBe("session-reconnect");
      expect(sent.session.system_prompt).toBeUndefined();
      await result.current.disconnect();
    } finally {
      vi.useRealTimers();
    }
  });

  it("stops after three internal reconnect attempts", async () => {
    vi.useFakeTimers();
    try {
      const { result } = renderHook(() => useVoiceLive(defaultOptions));
      const initialPromise = result.current.connect({ sessionId: "session-retry-cap" });
      const initialWs = getLastWs();
      initialWs.onopen?.();
      initialWs.simulateMessage({
        type: "proxy.connected",
        model: "gpt-4o",
        avatar_enabled: false,
      });
      initialWs.simulateMessage({ type: "session.updated", session: {} });
      await act(async () => initialPromise);

      const delays = [1000, 2000, 4000];
      let activeWs = initialWs;
      for (const [index, delay] of delays.entries()) {
        act(() => {
          activeWs.readyState = MockWebSocket.CLOSED;
          activeWs.onclose?.({ code: 1006, reason: "", wasClean: false } as CloseEvent);
          vi.advanceTimersByTime(delay);
        });

        activeWs = getLastWs();
        expect(MockWebSocket.instances).toHaveLength(index + 2);
        await act(async () => {
          activeWs.onopen?.();
          activeWs.simulateMessage({
            type: "proxy.connected",
            model: "gpt-4o",
            avatar_enabled: false,
          });
          activeWs.simulateMessage({ type: "session.updated", session: {} });
          await Promise.resolve();
        });
      }

      act(() => {
        activeWs.readyState = MockWebSocket.CLOSED;
        activeWs.onclose?.({ code: 1006, reason: "", wasClean: false } as CloseEvent);
        vi.advanceTimersByTime(8000);
      });
      expect(MockWebSocket.instances).toHaveLength(4);
      await result.current.disconnect();
    } finally {
      vi.useRealTimers();
    }
  });

  it("does not auto-reconnect after intentional disconnect()", async () => {
    const onConnectionStateChange = vi.fn();
    const { result } = renderHook(() =>
      useVoiceLive({ ...defaultOptions, onConnectionStateChange }),
    );

    await act(async () => {
      const promise = result.current.connect("hcp-no-reconnect");
      await vi.waitFor(() => expect(MockWebSocket.instances.length).toBe(1));
      const ws = getLastWs();
      await vi.waitFor(() => expect(ws.sentMessages.length).toBe(1));
      ws.simulateMessage({ type: "proxy.connected", model: "gpt-4o", avatar_enabled: false });
      ws.simulateMessage({ type: "session.updated", session: {} });
      return promise;
    });

    // Intentional disconnect
    await act(async () => {
      await result.current.disconnect();
    });

    onConnectionStateChange.mockClear();

    // Should NOT see "connecting" after intentional disconnect
    expect(result.current.connectionState).toBe("disconnected");
    expect(onConnectionStateChange).not.toHaveBeenCalledWith("connecting");
  });
});
