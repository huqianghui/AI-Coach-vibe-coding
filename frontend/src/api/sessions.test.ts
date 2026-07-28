import { describe, it, expect, vi, beforeEach } from "vitest";
import apiClient from "./client";
import {
  createSession,
  getUserSessions,
  getSession,
  getSessionMessages,
  endSession,
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
