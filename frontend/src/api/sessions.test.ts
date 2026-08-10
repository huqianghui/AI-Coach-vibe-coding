import { describe, it, expect, vi, beforeEach } from "vitest";
import apiClient from "./client";
import {
  createSession,
  getActiveSession,
  getUserSessions,
  getSession,
  getSessionMessages,
  endSession,
  streamSessionMessage,
} from "./sessions";

vi.mock("./client", () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}));

const mockClient = apiClient as unknown as {
  get: ReturnType<typeof vi.fn>;
  post: ReturnType<typeof vi.fn>;
};

beforeEach(() => vi.clearAllMocks());

describe("Sessions API client", () => {
  describe("streamSessionMessage", () => {
    it("serializes exactly message and dispatches durable SSE events", async () => {
      localStorage.setItem("access_token", "test-token");
      const body = [
        'event: state\ndata: {"code":"SESSION_TURN_ACCEPTED","status":"in_progress"}\n',
        "event: text\ndata: Hello\n",
        'event: hint\ndata: {"content":"Tip"}\n',
        'event: key_messages\ndata: [{"message":"KM","delivered":true,"detected_at":null}]\n',
        "event: done\ndata: \n",
      ].join("\n");
      const fetchMock = vi
        .spyOn(globalThis, "fetch")
        .mockResolvedValue(new Response(body, { status: 200 }));
      const callbacks = {
        onState: vi.fn(),
        onText: vi.fn(),
        onHint: vi.fn(),
        onKeyMessages: vi.fn(),
        onDone: vi.fn(),
        onError: vi.fn(),
      };

      await streamSessionMessage("session-1", "User text", callbacks);

      const request = fetchMock.mock.calls[0]!;
      expect(request[0]).toBe("/api/v1/sessions/session-1/message");
      const options = request[1] as RequestInit;
      expect(JSON.parse(options.body as string)).toEqual({ message: "User text" });
      expect(Object.keys(JSON.parse(options.body as string))).toEqual(["message"]);
      expect(callbacks.onState).toHaveBeenCalledWith({
        code: "SESSION_TURN_ACCEPTED",
        status: "in_progress",
      });
      expect(callbacks.onText).toHaveBeenCalledWith("Hello");
      expect(callbacks.onHint).toHaveBeenCalledWith({ content: "Tip" });
      expect(callbacks.onKeyMessages).toHaveBeenCalledTimes(1);
      expect(callbacks.onDone).toHaveBeenCalledOnce();
      expect(callbacks.onError).not.toHaveBeenCalled();
    });

    it("parses structured and plain stream errors", async () => {
      vi.spyOn(globalThis, "fetch").mockResolvedValue(
        new Response(
          'event: error\ndata: {"code":"SESSION_TURN_FAILED","message":"Failed"}\n\n' +
            "event: error\ndata: Plain failure\n\n",
          { status: 200 },
        ),
      );
      const onError = vi.fn();
      const callbacks = {
        onState: vi.fn(),
        onText: vi.fn(),
        onHint: vi.fn(),
        onKeyMessages: vi.fn(),
        onDone: vi.fn(),
        onError,
      };

      await streamSessionMessage("session-1", "Hello", callbacks);

      expect(onError).toHaveBeenNthCalledWith(1, {
        code: "SESSION_TURN_FAILED",
        message: "Failed",
      });
      expect(onError).toHaveBeenNthCalledWith(2, { message: "Plain failure" });
    });

    it("fails when the streaming endpoint is unavailable", async () => {
      vi.spyOn(globalThis, "fetch").mockResolvedValue(
        new Response(null, { status: 409 }),
      );
      const callbacks = {
        onState: vi.fn(),
        onText: vi.fn(),
        onHint: vi.fn(),
        onKeyMessages: vi.fn(),
        onDone: vi.fn(),
        onError: vi.fn(),
      };

      await expect(
        streamSessionMessage("session-1", "Hello", callbacks),
      ).rejects.toThrow("Stream failed: 409");
    });

    it("handles fragmented CRLF events, empty chunks, unknown events, and a signal", async () => {
      localStorage.removeItem("access_token");
      const encoder = new TextEncoder();
      const chunks = [
        "event: text\r\nda",
        "ta: Fragmented\r\n\r\nevent: unknown\r\ndata: ignored\r\n\r\n",
      ];
      const body = new ReadableStream<Uint8Array>({
        start(controller) {
          controller.enqueue(new Uint8Array());
          chunks.forEach((chunk) => controller.enqueue(encoder.encode(chunk)));
          controller.close();
        },
      });
      const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
        new Response(body, { status: 200 }),
      );
      const callbacks = {
        onState: vi.fn(),
        onText: vi.fn(),
        onHint: vi.fn(),
        onKeyMessages: vi.fn(),
        onDone: vi.fn(),
        onError: vi.fn(),
      };
      const controller = new AbortController();

      await streamSessionMessage("session-1", "Hello", callbacks, controller.signal);

      expect(callbacks.onText).toHaveBeenCalledWith("Fragmented");
      expect(callbacks.onDone).not.toHaveBeenCalled();
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/sessions/session-1/message",
        expect.objectContaining({
          signal: controller.signal,
          headers: expect.objectContaining({ Authorization: "Bearer null" }),
        }),
      );
    });
  });

  describe("getActiveSession", () => {
    it("calls GET /sessions/active", async () => {
      mockClient.get.mockResolvedValue({ data: { id: "active-1", status: "in_progress" } });

      await expect(getActiveSession()).resolves.toEqual({
        id: "active-1",
        status: "in_progress",
      });
      expect(mockClient.get).toHaveBeenCalledWith("/sessions/active");
    });
  });

  describe("createSession", () => {
    it("calls POST /sessions with scenario_id and defaults to realtime voice", async () => {
      mockClient.post.mockResolvedValue({
        data: { id: "sess-new", status: "created", scenario_id: "sc-1", mode: "text" },
      });

      const result = await createSession("sc-1");

      expect(mockClient.post).toHaveBeenCalledWith("/sessions", {
        scenario_id: "sc-1",
        mode: "voice_realtime_model",
      });
      expect(result.id).toBe("sess-new");
      expect(result.status).toBe("created");
    });

    it("sends mode=voice in request body when provided", async () => {
      mockClient.post.mockResolvedValue({
        data: { id: "sess-voice", status: "created", scenario_id: "sc-1", mode: "voice" },
      });

      const result = await createSession("sc-1", "voice");

      expect(mockClient.post).toHaveBeenCalledWith("/sessions", {
        scenario_id: "sc-1",
        mode: "voice",
      });
      expect(result.mode).toBe("voice");
    });

    it("sends mode=avatar in request body when provided", async () => {
      mockClient.post.mockResolvedValue({
        data: { id: "sess-avatar", status: "created", scenario_id: "sc-1", mode: "avatar" },
      });

      const result = await createSession("sc-1", "avatar");

      expect(mockClient.post).toHaveBeenCalledWith("/sessions", {
        scenario_id: "sc-1",
        mode: "avatar",
      });
      expect(result.mode).toBe("avatar");
    });

    it("propagates creation errors", async () => {
      mockClient.post.mockRejectedValue(new Error("404 Scenario not found"));

      await expect(createSession("bad-sc")).rejects.toThrow(
        "404 Scenario not found",
      );
    });
  });

  describe("getUserSessions", () => {
    it("calls GET /sessions with pagination params", async () => {
      const paginated = {
        items: [{ id: "s1" }],
        total: 1,
        page: 1,
        page_size: 20,
        total_pages: 1,
      };
      mockClient.get.mockResolvedValue({ data: paginated });

      const result = await getUserSessions({ page: 1, page_size: 10 });

      expect(mockClient.get).toHaveBeenCalledWith("/sessions", {
        params: { page: 1, page_size: 10 },
      });
      expect(result.total).toBe(1);
    });

    it("calls GET /sessions without params", async () => {
      mockClient.get.mockResolvedValue({
        data: { items: [], total: 0, page: 1, page_size: 20, total_pages: 0 },
      });

      const result = await getUserSessions();

      expect(mockClient.get).toHaveBeenCalledWith("/sessions", {
        params: undefined,
      });
      expect(result.items).toHaveLength(0);
    });
  });

  describe("getSession", () => {
    it("calls GET /sessions/:id", async () => {
      mockClient.get.mockResolvedValue({
        data: { id: "sess-1", status: "in_progress" },
      });

      const result = await getSession("sess-1");

      expect(mockClient.get).toHaveBeenCalledWith("/sessions/sess-1");
      expect(result.status).toBe("in_progress");
    });

    it("propagates 404 for missing session", async () => {
      mockClient.get.mockRejectedValue(new Error("404"));

      await expect(getSession("missing")).rejects.toThrow("404");
    });
  });

  describe("getSessionMessages", () => {
    it("calls GET /sessions/:id/messages", async () => {
      const messages = [
        { id: "m1", role: "user", content: "Hello", message_index: 0 },
        { id: "m2", role: "assistant", content: "Hi", message_index: 1 },
      ];
      mockClient.get.mockResolvedValue({ data: messages });

      const result = await getSessionMessages("sess-1");

      expect(mockClient.get).toHaveBeenCalledWith(
        "/sessions/sess-1/messages",
      );
      expect(result).toHaveLength(2);
      expect(result[0]?.role).toBe("user");
    });

    it("returns empty array for session with no messages", async () => {
      mockClient.get.mockResolvedValue({ data: [] });

      const result = await getSessionMessages("sess-empty");

      expect(result).toHaveLength(0);
    });
  });

  describe("endSession", () => {
    it("calls POST /sessions/:id/end", async () => {
      mockClient.post.mockResolvedValue({
        data: { id: "sess-1", status: "completed" },
      });

      const result = await endSession("sess-1");

      expect(mockClient.post).toHaveBeenCalledWith("/sessions/sess-1/end");
      expect(result.status).toBe("completed");
    });

    it("propagates 409 for non-in_progress session", async () => {
      mockClient.post.mockRejectedValue(new Error("409 Invalid status"));

      await expect(endSession("sess-bad")).rejects.toThrow("409 Invalid status");
    });
  });
});
