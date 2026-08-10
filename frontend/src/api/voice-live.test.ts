import { describe, it, expect, vi, beforeEach } from "vitest";
import apiClient from "./client";
import {
  fetchVoiceLiveToken,
  fetchWebRTCSession,
  fetchVoiceLiveStatus,
  fetchVoiceLiveModels,
  fetchAvatarCharacters,
  persistTranscriptMessage,
  fetchVoiceLiveInstances,
  fetchVoiceLiveInstance,
  createVoiceLiveInstance,
  updateVoiceLiveInstance,
  deleteVoiceLiveInstance,
  assignVoiceLiveInstance,
  unassignVoiceLiveInstance,
} from "./voice-live";

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
  put: ReturnType<typeof vi.fn>;
  delete: ReturnType<typeof vi.fn>;
};

beforeEach(() => vi.clearAllMocks());

describe("Voice Live API client", () => {
  describe("fetchWebRTCSession", () => {
    it("omits all optional identifiers when none are supplied", async () => {
      const session = { token: "token", ice_servers: [] };
      mockClient.post.mockResolvedValue({ data: session });

      await expect(fetchWebRTCSession()).resolves.toEqual(session);
      expect(mockClient.post).toHaveBeenCalledWith(
        "/voice-live/webrtc/session",
        null,
        { params: {} },
      );
    });

    it("includes every supplied authority identifier", async () => {
      const session = { token: "token", ice_servers: [] };
      mockClient.post.mockResolvedValue({ data: session });

      await expect(fetchWebRTCSession("hcp-1", "vl-1", "session-1")).resolves.toEqual(
        session,
      );
      expect(mockClient.post).toHaveBeenCalledWith(
        "/voice-live/webrtc/session",
        null,
        {
          params: {
            hcp_profile_id: "hcp-1",
            vl_instance_id: "vl-1",
            session_id: "session-1",
          },
        },
      );
    });

    it.each([
      ["HCP", ["hcp-1", undefined, undefined], { hcp_profile_id: "hcp-1" }],
      ["instance", [undefined, "vl-1", undefined], { vl_instance_id: "vl-1" }],
      ["Session", [undefined, undefined, "session-1"], { session_id: "session-1" }],
    ] as const)("supports only the %s identifier", async (_label, args, params) => {
      mockClient.post.mockResolvedValue({ data: { token: "token" } });

      await fetchWebRTCSession(...args);

      expect(mockClient.post).toHaveBeenCalledWith(
        "/voice-live/webrtc/session",
        null,
        { params },
      );
    });
  });

  describe("fetchVoiceLiveToken", () => {
    it("calls POST /voice-live/token and returns token data", async () => {
      const tokenData = {
        endpoint: "wss://eastus2.api.cognitive.microsoft.com",
        token: "test-token-123",
        region: "eastus2",
        model: "gpt-4o-realtime",
        avatar_enabled: false,
        avatar_character: "lisa",
        voice_name: "en-US-JennyNeural",
      };
      mockClient.post.mockResolvedValue({ data: tokenData });

      const result = await fetchVoiceLiveToken();

      expect(mockClient.post).toHaveBeenCalledWith("/voice-live/token", null, { params: {} });
      expect(result).toEqual(tokenData);
      expect(result.endpoint).toBe("wss://eastus2.api.cognitive.microsoft.com");
      expect(result.avatar_enabled).toBe(false);
    });

    it("propagates errors from apiClient", async () => {
      mockClient.post.mockRejectedValue(new Error("401 Unauthorized"));

      await expect(fetchVoiceLiveToken()).rejects.toThrow("401 Unauthorized");
    });

    it("adds an HCP profile identifier when provided", async () => {
      mockClient.post.mockResolvedValue({ data: { token: "hcp-token" } });

      await fetchVoiceLiveToken("hcp-1");

      expect(mockClient.post).toHaveBeenCalledWith("/voice-live/token", null, {
        params: { hcp_profile_id: "hcp-1" },
      });
    });
  });

  describe("fetchVoiceLiveStatus", () => {
    it("calls GET /voice-live/status and returns status with availability flags", async () => {
      const statusData = {
        voice_live_available: true,
        avatar_available: false,
        voice_name: "en-US-JennyNeural",
        avatar_character: "lisa",
      };
      mockClient.get.mockResolvedValue({ data: statusData });

      const result = await fetchVoiceLiveStatus();

      expect(mockClient.get).toHaveBeenCalledWith("/voice-live/status");
      expect(result).toEqual(statusData);
      expect(result.voice_live_available).toBe(true);
      expect(result.avatar_available).toBe(false);
    });

    it("propagates errors from apiClient", async () => {
      mockClient.get.mockRejectedValue(new Error("500 Internal Server Error"));

      await expect(fetchVoiceLiveStatus()).rejects.toThrow(
        "500 Internal Server Error",
      );
    });
  });

  describe("persistTranscriptMessage", () => {
    it("calls POST /sessions/:id/transcript with correct payload", async () => {
      mockClient.post.mockResolvedValue({ data: undefined });

      await persistTranscriptMessage("sess-123", "user", "Hello doctor");

      expect(mockClient.post).toHaveBeenCalledWith(
        "/sessions/sess-123/transcript",
        {
          message: "Hello doctor",
          role: "user",
        },
      );
    });

    it("propagates errors from apiClient", async () => {
      mockClient.post.mockRejectedValue(new Error("404 Not Found"));

      await expect(
        persistTranscriptMessage("bad-id", "assistant", "Response"),
      ).rejects.toThrow("404 Not Found");
    });
  });

  describe("fetchVoiceLiveModels", () => {
    it("calls GET /voice-live/models and returns models data", async () => {
      const modelsData = {
        models: [
          { id: "gpt-4o-realtime", name: "GPT-4o Realtime", version: "2024-10-01" },
        ],
      };
      mockClient.get.mockResolvedValue({ data: modelsData });

      const result = await fetchVoiceLiveModels();

      expect(mockClient.get).toHaveBeenCalledWith("/voice-live/models");
      expect(result).toEqual(modelsData);
    });

    it("propagates errors from apiClient", async () => {
      mockClient.get.mockRejectedValue(new Error("500 Server Error"));

      await expect(fetchVoiceLiveModels()).rejects.toThrow("500 Server Error");
    });
  });

  describe("fetchAvatarCharacters", () => {
    it("calls GET /voice-live/avatar-characters and returns characters", async () => {
      const charactersData = {
        characters: [
          { id: "lisa", name: "Lisa", thumbnail_url: "https://example.com/lisa.png" },
        ],
      };
      mockClient.get.mockResolvedValue({ data: charactersData });

      const result = await fetchAvatarCharacters();

      expect(mockClient.get).toHaveBeenCalledWith("/voice-live/avatar-characters");
      expect(result).toEqual(charactersData);
    });

    it("propagates errors from apiClient", async () => {
      mockClient.get.mockRejectedValue(new Error("503 Unavailable"));

      await expect(fetchAvatarCharacters()).rejects.toThrow("503 Unavailable");
    });
  });

  describe("fetchVoiceLiveInstances", () => {
    it("calls GET /voice-live/instances with pagination params", async () => {
      const instancesData = {
        items: [{ id: "vl-1", name: "Test Instance" }],
        total: 1,
        page: 1,
        page_size: 20,
        total_pages: 1,
      };
      mockClient.get.mockResolvedValue({ data: instancesData });

      const result = await fetchVoiceLiveInstances({ page: 1, page_size: 20 });

      expect(mockClient.get).toHaveBeenCalledWith("/voice-live/instances", {
        params: { page: 1, page_size: 20 },
      });
      expect(result).toEqual(instancesData);
    });

    it("calls GET /voice-live/instances without params", async () => {
      const instancesData = {
        items: [],
        total: 0,
        page: 1,
        page_size: 20,
        total_pages: 0,
      };
      mockClient.get.mockResolvedValue({ data: instancesData });

      const result = await fetchVoiceLiveInstances();

      expect(mockClient.get).toHaveBeenCalledWith("/voice-live/instances", {
        params: undefined,
      });
      expect(result.items).toHaveLength(0);
    });
  });

  describe("fetchVoiceLiveInstance", () => {
    it("calls GET /voice-live/instances/:id and returns instance", async () => {
      const instance = { id: "vl-1", name: "Test Instance", model_id: "gpt-4o" };
      mockClient.get.mockResolvedValue({ data: instance });

      const result = await fetchVoiceLiveInstance("vl-1");

      expect(mockClient.get).toHaveBeenCalledWith("/voice-live/instances/vl-1");
      expect(result).toEqual(instance);
    });

    it("propagates 404 for missing instance", async () => {
      mockClient.get.mockRejectedValue(new Error("404 Not Found"));

      await expect(fetchVoiceLiveInstance("missing")).rejects.toThrow("404 Not Found");
    });
  });

  describe("createVoiceLiveInstance", () => {
    it("calls POST /voice-live/instances with create data", async () => {
      const createData = { name: "New VL", model_id: "gpt-4o-realtime" };
      const created = { id: "vl-new", ...createData };
      mockClient.post.mockResolvedValue({ data: created });

      const result = await createVoiceLiveInstance(createData as never);

      expect(mockClient.post).toHaveBeenCalledWith("/voice-live/instances", createData);
      expect(result.id).toBe("vl-new");
    });

    it("propagates errors on create", async () => {
      mockClient.post.mockRejectedValue(new Error("422 Validation Error"));

      await expect(
        createVoiceLiveInstance({ name: "" } as never),
      ).rejects.toThrow("422 Validation Error");
    });
  });

  describe("updateVoiceLiveInstance", () => {
    it("calls PUT /voice-live/instances/:id with update data", async () => {
      const updateData = { name: "Updated VL" };
      const updated = { id: "vl-1", name: "Updated VL", model_id: "gpt-4o" };
      mockClient.put.mockResolvedValue({ data: updated });

      const result = await updateVoiceLiveInstance("vl-1", updateData as never);

      expect(mockClient.put).toHaveBeenCalledWith("/voice-live/instances/vl-1", updateData);
      expect(result.name).toBe("Updated VL");
    });

    it("propagates errors on update", async () => {
      mockClient.put.mockRejectedValue(new Error("404 Not Found"));

      await expect(
        updateVoiceLiveInstance("missing", { name: "X" } as never),
      ).rejects.toThrow("404 Not Found");
    });
  });

  describe("deleteVoiceLiveInstance", () => {
    it("calls DELETE /voice-live/instances/:id", async () => {
      mockClient.delete.mockResolvedValue({ status: 204 });

      await deleteVoiceLiveInstance("vl-1");

      expect(mockClient.delete).toHaveBeenCalledWith("/voice-live/instances/vl-1");
    });

    it("propagates errors on delete", async () => {
      mockClient.delete.mockRejectedValue(new Error("403 Forbidden"));

      await expect(deleteVoiceLiveInstance("vl-1")).rejects.toThrow("403 Forbidden");
    });
  });

  describe("assignVoiceLiveInstance", () => {
    it("calls POST /voice-live/instances/:id/assign with hcp_profile_id", async () => {
      const assigned = { id: "vl-1", hcp_profile_id: "hp-1" };
      mockClient.post.mockResolvedValue({ data: assigned });

      const result = await assignVoiceLiveInstance("vl-1", "hp-1");

      expect(mockClient.post).toHaveBeenCalledWith(
        "/voice-live/instances/vl-1/assign",
        { hcp_profile_id: "hp-1" },
      );
      expect(result).toEqual(assigned);
    });

    it("propagates errors on assign", async () => {
      mockClient.post.mockRejectedValue(new Error("409 Conflict"));

      await expect(
        assignVoiceLiveInstance("vl-1", "hp-1"),
      ).rejects.toThrow("409 Conflict");
    });
  });

  describe("unassignVoiceLiveInstance", () => {
    it("calls POST /voice-live/instances/unassign with hcp_profile_id", async () => {
      const unassigned = { hcp_profile_id: "hp-1", voice_live_instance_id: null };
      mockClient.post.mockResolvedValue({ data: unassigned });

      const result = await unassignVoiceLiveInstance("hp-1");

      expect(mockClient.post).toHaveBeenCalledWith(
        "/voice-live/instances/unassign",
        { hcp_profile_id: "hp-1" },
      );
      expect(result).toEqual(unassigned);
      expect(result.voice_live_instance_id).toBeNull();
    });

    it("propagates errors on unassign", async () => {
      mockClient.post.mockRejectedValue(new Error("404 Not Found"));

      await expect(unassignVoiceLiveInstance("hp-bad")).rejects.toThrow("404 Not Found");
    });
  });
});
