import { describe, it, expect, vi, beforeEach } from "vitest";
import apiClient from "./client";
import {
  createConferenceSession,
  getConferenceSession,
  updateSubState,
  endConferenceSession,
  getAudienceHcps,
  setAudienceHcps,
} from "./conference";

vi.mock("./client", () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

const mockClient = apiClient as unknown as {
  get: ReturnType<typeof vi.fn>;
  post: ReturnType<typeof vi.fn>;
  put: ReturnType<typeof vi.fn>;
  patch: ReturnType<typeof vi.fn>;
};

beforeEach(() => vi.clearAllMocks());

describe("Conference API client", () => {
  describe("createConferenceSession", () => {
    it("calls POST /conference/sessions with scenario_id and default mode", async () => {
      const session = {
        id: "cs-1",
        user_id: "u-1",
        scenario_id: "sc-1",
        status: "created",
        mode: "text",
        session_type: "conference",
        sub_state: "presenting",
        presentation_topic: "Topic",
        audience_config: "[]",
        key_messages_status: "[]",
        created_at: "2026-07-01T00:00:00Z",
      };
      mockClient.post.mockResolvedValue({ data: session });

      const result = await createConferenceSession("sc-1");

      expect(mockClient.post).toHaveBeenCalledWith("/conference/sessions", {
        scenario_id: "sc-1",
        mode: "text",
      });
      expect(result.id).toBe("cs-1");
      expect(result.scenarioId).toBe("sc-1");
    });

    it("passes voice mode when provided", async () => {
      const session = {
        id: "cs-1",
        user_id: "u-1",
        scenario_id: "sc-1",
        status: "created",
        mode: "voice_realtime_model",
        session_type: "conference",
        sub_state: "presenting",
        presentation_topic: "Topic",
        audience_config: "[]",
        key_messages_status: "[]",
        created_at: "2026-07-01T00:00:00Z",
      };
      mockClient.post.mockResolvedValue({ data: session });

      await createConferenceSession("sc-1", "voice_realtime_model");

      expect(mockClient.post).toHaveBeenCalledWith("/conference/sessions", {
        scenario_id: "sc-1",
        mode: "voice_realtime_model",
      });
    });

    it("propagates creation errors", async () => {
      mockClient.post.mockRejectedValue(new Error("400 Bad Request"));

      await expect(createConferenceSession("bad")).rejects.toThrow(
        "400 Bad Request",
      );
    });
  });

  describe("getConferenceSession", () => {
    it("calls GET /conference/sessions/:id", async () => {
      const session = {
        id: "cs-1",
        user_id: "u-1",
        scenario_id: "sc-1",
        status: "in_progress",
        mode: "digital_human_realtime_model",
        session_type: "conference",
        sub_state: "presenting",
        presentation_topic: "Topic",
        audience_config: "[{\"hcp_profile_id\":\"hp-1\"}]",
        key_messages_status: "[]",
        created_at: "2026-07-01T00:00:00Z",
      };
      mockClient.get.mockResolvedValue({ data: session });

      const result = await getConferenceSession("cs-1");

      expect(mockClient.get).toHaveBeenCalledWith("/conference/sessions/cs-1");
      expect(result.status).toBe("in_progress");
      expect(result.scenarioId).toBe("sc-1");
      expect(result.audienceConfig).toContain("hp-1");
      expect(result.keyMessagesStatus).toBe("[]");
    });

    it("propagates 404 for missing session", async () => {
      mockClient.get.mockRejectedValue(new Error("404"));

      await expect(getConferenceSession("missing")).rejects.toThrow("404");
    });
  });

  describe("updateSubState", () => {
    it("calls PATCH /conference/sessions/:id/sub-state", async () => {
      mockClient.patch.mockResolvedValue({ data: undefined });

      await updateSubState("cs-1", "qa");

      expect(mockClient.patch).toHaveBeenCalledWith(
        "/conference/sessions/cs-1/sub-state",
        { sub_state: "qa" },
      );
    });
  });

  describe("endConferenceSession", () => {
    it("calls POST /conference/sessions/:id/end", async () => {
      mockClient.post.mockResolvedValue({ data: undefined });

      await endConferenceSession("cs-1");

      expect(mockClient.post).toHaveBeenCalledWith(
        "/conference/sessions/cs-1/end",
      );
    });

    it("propagates errors", async () => {
      mockClient.post.mockRejectedValue(new Error("409"));

      await expect(endConferenceSession("bad")).rejects.toThrow("409");
    });
  });

  describe("getAudienceHcps", () => {
    it("calls GET /conference/scenarios/:id/audience and maps snake_case", async () => {
      const hcps = [
        {
          id: "ah-1",
          scenario_id: "sc-1",
          hcp_profile_id: "hcp-1",
          role_in_conference: "audience",
          voice_id: "voice-a",
          sort_order: 0,
          hcp_name: "Dr. Smith",
          hcp_specialty: "Oncology",
        },
      ];
      mockClient.get.mockResolvedValue({ data: hcps });

      const result = await getAudienceHcps("sc-1");

      expect(mockClient.get).toHaveBeenCalledWith(
        "/conference/scenarios/sc-1/audience",
      );
      expect(result).toHaveLength(1);
      expect(result[0]?.hcpProfileId).toBe("hcp-1");
      expect(result[0]?.hcpName).toBe("Dr. Smith");
      expect(result[0]?.hcpSpecialty).toBe("Oncology");
      expect(result[0]?.roleInConference).toBe("audience");
    });

    it("returns empty array when no audience", async () => {
      mockClient.get.mockResolvedValue({ data: [] });

      const result = await getAudienceHcps("sc-empty");

      expect(result).toHaveLength(0);
    });

    it("defaults optional display metadata for legacy audience rows", async () => {
      mockClient.get.mockResolvedValue({
        data: [
          {
            id: "ah-legacy",
            scenario_id: "sc-1",
            hcp_profile_id: "hcp-legacy",
            role_in_conference: "audience",
            voice_id: "",
            sort_order: 3,
          },
        ],
      });

      const [legacy] = await getAudienceHcps("sc-1");

      expect(legacy).toMatchObject({
        hcpName: "",
        hcpSpecialty: "",
        voiceLiveInstanceId: undefined,
        voiceName: undefined,
        status: "listening",
      });
    });
  });

  describe("setAudienceHcps", () => {
    it("calls PUT /conference/scenarios/:id/audience with snake_case payload", async () => {
      const input = [
        { hcpProfileId: "hp-1" },
        { hcpProfileId: "hp-2", roleInConference: "moderator", sortOrder: 1 },
      ];
      const output = [
        {
          id: "ah-1",
          scenario_id: "sc-1",
          hcp_profile_id: "hp-1",
          role_in_conference: "audience",
          voice_id: "",
          sort_order: 0,
          hcp_name: "Dr. X",
          hcp_specialty: "",
        },
      ];
      mockClient.put.mockResolvedValue({ data: output });

      const result = await setAudienceHcps("sc-1", input);

      expect(mockClient.put).toHaveBeenCalledWith(
        "/conference/scenarios/sc-1/audience",
        [
          {
            hcp_profile_id: "hp-1",
            role_in_conference: "audience",
            voice_id: "",
            sort_order: 0,
          },
          {
            hcp_profile_id: "hp-2",
            role_in_conference: "moderator",
            voice_id: "",
            sort_order: 1,
          },
        ],
      );
      expect(result).toHaveLength(1);
      expect(result[0]?.hcpProfileId).toBe("hp-1");
    });

    it("preserves explicit role, voice, and zero sort order in the payload", async () => {
      mockClient.put.mockResolvedValue({ data: [] });

      await setAudienceHcps("sc-2", [
        {
          hcpProfileId: "hp-9",
          roleInConference: "moderator",
          voiceId: "voice-9",
          sortOrder: 0,
        },
      ]);

      expect(mockClient.put).toHaveBeenCalledWith(
        "/conference/scenarios/sc-2/audience",
        [
          {
            hcp_profile_id: "hp-9",
            role_in_conference: "moderator",
            voice_id: "voice-9",
            sort_order: 0,
          },
        ],
      );
    });
  });
});
