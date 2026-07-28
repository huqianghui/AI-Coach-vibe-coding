import apiClient from "./client";
import {
  getHcpProfiles,
  getHcpProfile,
  createHcpProfile,
  updateHcpProfile,
  deleteHcpProfile,
} from "./hcp-profiles";
import {
  getScenarios,
  getActiveScenarios,
  getScenario,
  createScenario,
  deleteScenario,
  cloneScenario,
} from "./scenarios";
import {
  createSession,
  getUserSessions,
  getSession,
  getSessionMessages,
  endSession,
} from "./sessions";
import { triggerScoring, getSessionScore } from "./scoring";
import { fetchWebRTCSession } from "./voice-live";

vi.mock("./client", () => {
  const mock = {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  };
  return { default: mock };
});

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const mockClient = apiClient as unknown as {
  get: ReturnType<typeof vi.fn>;
  post: ReturnType<typeof vi.fn>;
  put: ReturnType<typeof vi.fn>;
  delete: ReturnType<typeof vi.fn>;
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe("HCP Profiles API", () => {
  it("getHcpProfiles calls GET /hcp-profiles with params", async () => {
    const data = { items: [], total: 0, page: 1, page_size: 20, total_pages: 0 };
    mockClient.get.mockResolvedValue({ data });

    const result = await getHcpProfiles({ page: 1, search: "test" });
    expect(mockClient.get).toHaveBeenCalledWith("/hcp-profiles", {
      params: { page: 1, search: "test" },
    });
    expect(result).toEqual(data);
  });

  it("getHcpProfile calls GET /hcp-profiles/:id", async () => {
    const profile = { id: "1", name: "Dr. Test" };
    mockClient.get.mockResolvedValue({ data: profile });

    const result = await getHcpProfile("1");
    expect(mockClient.get).toHaveBeenCalledWith("/hcp-profiles/1");
    expect(result).toEqual(profile);
  });

  it("createHcpProfile calls POST /hcp-profiles", async () => {
    const newProfile = {
      name: "New",
      specialty: "Oncology",
      voice_live_instance_id: "vl-1",
    };
    const created = { id: "2", ...newProfile };
    mockClient.post.mockResolvedValue({ data: created });

    const result = await createHcpProfile(newProfile);
    expect(mockClient.post).toHaveBeenCalledWith("/hcp-profiles", newProfile);
    expect(result).toEqual(created);
  });

  it("updateHcpProfile calls PUT /hcp-profiles/:id", async () => {
    const update = { name: "Updated" };
    const updated = { id: "1", name: "Updated" };
    mockClient.put.mockResolvedValue({ data: updated });

    const result = await updateHcpProfile("1", update);
    expect(mockClient.put).toHaveBeenCalledWith("/hcp-profiles/1", update);
    expect(result).toEqual(updated);
  });

  it("deleteHcpProfile calls DELETE /hcp-profiles/:id", async () => {
    mockClient.delete.mockResolvedValue({});

    await deleteHcpProfile("1");
    expect(mockClient.delete).toHaveBeenCalledWith("/hcp-profiles/1");
  });
});

describe("Scenarios API", () => {
  it("getScenarios calls GET /scenarios with params", async () => {
    const data = { items: [], total: 0, page: 1, page_size: 20, total_pages: 0 };
    mockClient.get.mockResolvedValue({ data });

    const result = await getScenarios({ status: "active" });
    expect(mockClient.get).toHaveBeenCalledWith("/scenarios", {
      params: { status: "active" },
    });
    expect(result).toEqual(data);
  });

  it("getActiveScenarios calls GET /scenarios/active", async () => {
    const data: never[] = [];
    mockClient.get.mockResolvedValue({ data });

    const result = await getActiveScenarios();
    expect(mockClient.get).toHaveBeenCalledWith("/scenarios/active", {
      params: undefined,
    });
    expect(result).toEqual(data);
  });

  it("getScenario calls GET /scenarios/:id", async () => {
    const scenario = { id: "sc-1", name: "Test" };
    mockClient.get.mockResolvedValue({ data: scenario });

    const result = await getScenario("sc-1");
    expect(mockClient.get).toHaveBeenCalledWith("/scenarios/sc-1");
    expect(result).toEqual(scenario);
  });

  it("createScenario calls POST /scenarios", async () => {
    const newScenario = { name: "New", product: "Tislelizumab", hcp_profile_id: "hcp-1", rubric_id: "rubric-1" };
    mockClient.post.mockResolvedValue({ data: { id: "sc-2", ...newScenario } });

    const result = await createScenario(newScenario);
    expect(mockClient.post).toHaveBeenCalledWith("/scenarios", newScenario);
    expect(result.id).toBe("sc-2");
  });

  it("deleteScenario calls DELETE /scenarios/:id", async () => {
    mockClient.delete.mockResolvedValue({});

    await deleteScenario("sc-1");
    expect(mockClient.delete).toHaveBeenCalledWith("/scenarios/sc-1");
  });

  it("cloneScenario calls POST /scenarios/:id/clone", async () => {
    mockClient.post.mockResolvedValue({ data: { id: "sc-3" } });

    const result = await cloneScenario("sc-1");
    expect(mockClient.post).toHaveBeenCalledWith("/scenarios/sc-1/clone");
    expect(result.id).toBe("sc-3");
  });
});

describe("Sessions API", () => {
  it("createSession calls POST /sessions with scenario_id", async () => {
    mockClient.post.mockResolvedValue({ data: { id: "sess-1" } });

    const result = await createSession("sc-1");
    expect(mockClient.post).toHaveBeenCalledWith("/sessions", {
      scenario_id: "sc-1",
      mode: "voice_realtime_model",
    });
    expect(result.id).toBe("sess-1");
  });

  it("getUserSessions calls GET /sessions", async () => {
    const data = { items: [], total: 0, page: 1, page_size: 20, total_pages: 0 };
    mockClient.get.mockResolvedValue({ data });

    const result = await getUserSessions({ page: 1 });
    expect(mockClient.get).toHaveBeenCalledWith("/sessions", {
      params: { page: 1 },
    });
    expect(result).toEqual(data);
  });

  it("getSession calls GET /sessions/:id", async () => {
    mockClient.get.mockResolvedValue({ data: { id: "sess-1" } });

    const result = await getSession("sess-1");
    expect(mockClient.get).toHaveBeenCalledWith("/sessions/sess-1");
    expect(result.id).toBe("sess-1");
  });

  it("getSessionMessages calls GET /sessions/:id/messages", async () => {
    mockClient.get.mockResolvedValue({ data: [] });

    const result = await getSessionMessages("sess-1");
    expect(mockClient.get).toHaveBeenCalledWith("/sessions/sess-1/messages");
    expect(result).toEqual([]);
  });

  it("endSession calls POST /sessions/:id/end", async () => {
    mockClient.post.mockResolvedValue({ data: { id: "sess-1", status: "completed" } });

    const result = await endSession("sess-1");
    expect(mockClient.post).toHaveBeenCalledWith("/sessions/sess-1/end");
    expect(result.status).toBe("completed");
  });
});

describe("Scoring API", () => {
  it("triggerScoring calls POST /scoring/sessions/:id/score", async () => {
    mockClient.post.mockResolvedValue({
      data: { session_id: "sess-1", overall_score: 85 },
    });

    const result = await triggerScoring("sess-1");
    expect(mockClient.post).toHaveBeenCalledWith(
      "/scoring/sessions/sess-1/score",
    );
    expect(result.overall_score).toBe(85);
  });

  it("getSessionScore calls GET /scoring/sessions/:id/score", async () => {
    mockClient.get.mockResolvedValue({
      data: { session_id: "sess-1", overall_score: 75 },
    });

    const result = await getSessionScore("sess-1");
    expect(mockClient.get).toHaveBeenCalledWith(
      "/scoring/sessions/sess-1/score",
    );
    expect(result.overall_score).toBe(75);
  });
});

describe("Voice Live WebRTC API", () => {
  it("serializes an optional Unified Training session only as session_id", async () => {
    mockClient.post.mockResolvedValue({ data: { mode: "agent" } });

    await fetchWebRTCSession("hcp-1", "vl-1", "session-1");

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

  it("preserves the standalone query shape when sessionId is absent", async () => {
    mockClient.post.mockResolvedValue({ data: { mode: "model" } });

    await fetchWebRTCSession("hcp-1", "vl-1");

    expect(mockClient.post).toHaveBeenCalledWith(
      "/voice-live/webrtc/session",
      null,
      { params: { hcp_profile_id: "hcp-1", vl_instance_id: "vl-1" } },
    );
  });
});
