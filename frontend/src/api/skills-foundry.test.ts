import { beforeEach, describe, expect, it, vi } from "vitest";
import apiClient from "./client";
import { batchFoundrySync, retryFoundrySync } from "./skills";

vi.mock("./client", () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}));

const mockClient = apiClient as unknown as {
  post: ReturnType<typeof vi.fn>;
};

beforeEach(() => vi.clearAllMocks());

describe("Skills Foundry API client", () => {
  it("syncs one Skill through its Foundry endpoint", async () => {
    const skill = { id: "skill-1", foundry_sync_status: "synced" };
    mockClient.post.mockResolvedValue({ data: skill });

    await expect(retryFoundrySync("skill-1")).resolves.toEqual(skill);
    expect(mockClient.post).toHaveBeenCalledWith(
      "/skills/skill-1/foundry-sync",
    );
  });

  it("batch-syncs published non-synced Skills", async () => {
    const summary = { synced: 2, failed: 1, total: 3 };
    mockClient.post.mockResolvedValue({ data: summary });

    await expect(batchFoundrySync()).resolves.toEqual(summary);
    expect(mockClient.post).toHaveBeenCalledWith(
      "/skills/batch-foundry-sync",
    );
  });
});
