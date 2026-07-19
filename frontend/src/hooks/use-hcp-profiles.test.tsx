import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { type ReactNode } from "react";
import type { HcpProfile } from "@/types/hcp";

vi.mock("@/api/hcp-profiles", () => ({
  getHcpProfiles: vi.fn(),
  getHcpProfile: vi.fn(),
  createHcpProfile: vi.fn(),
  updateHcpProfile: vi.fn(),
  deleteHcpProfile: vi.fn(),
  retrySyncHcpProfile: vi.fn(),
  batchSyncAgents: vi.fn(),
  previewInstructions: vi.fn(),
}));

import {
  getHcpProfiles,
  getHcpProfile,
  createHcpProfile,
  updateHcpProfile,
  deleteHcpProfile,
  retrySyncHcpProfile,
  batchSyncAgents,
  previewInstructions,
} from "@/api/hcp-profiles";
import {
  useHcpProfiles,
  useHcpProfile,
  useCreateHcpProfile,
  useUpdateHcpProfile,
  useDeleteHcpProfile,
  useRetrySyncHcpProfile,
  useBatchSyncAgents,
  usePreviewInstructions,
} from "@/hooks/use-hcp-profiles";

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  };
}

const mockProfiles = {
  items: [{ id: "h1", name: "Dr. Wang" } as HcpProfile],
  total: 1,
  page: 1,
  page_size: 20,
  total_pages: 1,
};

describe("useHcpProfiles", () => {
  beforeEach(() => vi.clearAllMocks());

  it("should fetch HCP profiles with params", async () => {
    vi.mocked(getHcpProfiles).mockResolvedValueOnce(mockProfiles);

    const { result } = renderHook(
      () => useHcpProfiles({ page: 1, search: "wang" }),
      { wrapper: createWrapper() },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(getHcpProfiles).toHaveBeenCalledWith({
      page: 1,
      search: "wang",
    });
    expect(result.current.data).toEqual(mockProfiles);
  });

  it("should fetch HCP profiles without params", async () => {
    vi.mocked(getHcpProfiles).mockResolvedValueOnce(mockProfiles);

    const { result } = renderHook(() => useHcpProfiles(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(getHcpProfiles).toHaveBeenCalledWith(undefined);
  });
});

describe("useHcpProfile", () => {
  beforeEach(() => vi.clearAllMocks());

  it("should fetch a single HCP profile", async () => {
    const profile = { id: "h1", name: "Dr. Wang" } as HcpProfile;
    vi.mocked(getHcpProfile).mockResolvedValueOnce(profile);

    const { result } = renderHook(() => useHcpProfile("h1"), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(getHcpProfile).toHaveBeenCalledWith("h1");
  });

  it("should not fetch when id is undefined", () => {
    const { result } = renderHook(() => useHcpProfile(undefined), {
      wrapper: createWrapper(),
    });

    expect(result.current.isFetching).toBe(false);
    expect(getHcpProfile).not.toHaveBeenCalled();
  });
});

describe("useCreateHcpProfile", () => {
  beforeEach(() => vi.clearAllMocks());

  it("should create an HCP profile", async () => {
    const newProfile = { id: "h2", name: "Dr. Li" } as HcpProfile;
    vi.mocked(createHcpProfile).mockResolvedValueOnce(newProfile);

    const { result } = renderHook(() => useCreateHcpProfile(), {
      wrapper: createWrapper(),
    });

    result.current.mutate({
      name: "Dr. Li",
      specialty: "Oncology",
      voice_live_instance_id: "vl-1",
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(createHcpProfile).toHaveBeenCalledWith({
      name: "Dr. Li",
      specialty: "Oncology",
      voice_live_instance_id: "vl-1",
    });
  });
});

describe("useUpdateHcpProfile", () => {
  beforeEach(() => vi.clearAllMocks());

  it("should update an HCP profile", async () => {
    vi.mocked(updateHcpProfile).mockResolvedValueOnce({
      id: "h1",
      name: "Dr. Wang Updated",
    } as HcpProfile);

    const { result } = renderHook(() => useUpdateHcpProfile(), {
      wrapper: createWrapper(),
    });

    result.current.mutate({ id: "h1", data: { name: "Dr. Wang Updated" } });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(updateHcpProfile).toHaveBeenCalledWith("h1", {
      name: "Dr. Wang Updated",
    });
  });
});

describe("useDeleteHcpProfile", () => {
  beforeEach(() => vi.clearAllMocks());

  it("should delete an HCP profile", async () => {
    vi.mocked(deleteHcpProfile).mockResolvedValueOnce(undefined);

    const { result } = renderHook(() => useDeleteHcpProfile(), {
      wrapper: createWrapper(),
    });

    result.current.mutate("h1");

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(deleteHcpProfile).toHaveBeenCalledWith("h1");
  });
});

describe("useRetrySyncHcpProfile", () => {
  beforeEach(() => vi.clearAllMocks());

  it("should retry sync for an HCP profile", async () => {
    const syncedProfile = { id: "h1", name: "Dr. Wang" } as HcpProfile;
    vi.mocked(retrySyncHcpProfile).mockResolvedValueOnce(syncedProfile);

    const { result } = renderHook(() => useRetrySyncHcpProfile(), {
      wrapper: createWrapper(),
    });

    result.current.mutate("h1");

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(retrySyncHcpProfile).toHaveBeenCalledWith("h1");
  });

  it("should invalidate hcp-profiles queries on success", async () => {
    vi.mocked(retrySyncHcpProfile).mockResolvedValueOnce({
      id: "h1",
      name: "Dr. Wang",
    } as HcpProfile);

    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false, gcTime: 0 },
        mutations: { retry: false },
      },
    });
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    function Wrapper({ children }: { children: ReactNode }) {
      return (
        <QueryClientProvider client={queryClient}>
          {children}
        </QueryClientProvider>
      );
    }

    const { result } = renderHook(() => useRetrySyncHcpProfile(), {
      wrapper: Wrapper,
    });

    result.current.mutate("h1");

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ["hcp-profiles"],
    });
  });

  it("should handle retry sync failure", async () => {
    vi.mocked(retrySyncHcpProfile).mockRejectedValueOnce(
      new Error("Sync failed"),
    );

    const { result } = renderHook(() => useRetrySyncHcpProfile(), {
      wrapper: createWrapper(),
    });

    result.current.mutate("h1");

    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});

describe("useBatchSyncAgents", () => {
  beforeEach(() => vi.clearAllMocks());

  it("should trigger batch sync", async () => {
    const syncResult = { synced: 5, failed: 0, total: 5 };
    vi.mocked(batchSyncAgents).mockResolvedValueOnce(syncResult);

    const { result } = renderHook(() => useBatchSyncAgents(), {
      wrapper: createWrapper(),
    });

    result.current.mutate();

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(batchSyncAgents).toHaveBeenCalledTimes(1);
    expect(result.current.data).toEqual(syncResult);
  });

  it("should invalidate hcp-profiles queries on success", async () => {
    vi.mocked(batchSyncAgents).mockResolvedValueOnce({
      synced: 3,
      failed: 1,
      total: 4,
    });

    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false, gcTime: 0 },
        mutations: { retry: false },
      },
    });
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    function Wrapper({ children }: { children: ReactNode }) {
      return (
        <QueryClientProvider client={queryClient}>
          {children}
        </QueryClientProvider>
      );
    }

    const { result } = renderHook(() => useBatchSyncAgents(), {
      wrapper: Wrapper,
    });

    result.current.mutate();

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ["hcp-profiles"],
    });
  });
});

describe("usePreviewInstructions", () => {
  beforeEach(() => vi.clearAllMocks());

  it("should preview instructions with profile data", async () => {
    const previewResult = {
      instructions: "You are Dr. Wang, an oncologist...",
      is_override: false,
    };
    vi.mocked(previewInstructions).mockResolvedValueOnce(previewResult);

    const { result } = renderHook(() => usePreviewInstructions(), {
      wrapper: createWrapper(),
    });

    result.current.mutate({
      name: "Dr. Wang",
      specialty: "Oncology",
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(previewInstructions).toHaveBeenCalledWith({
      name: "Dr. Wang",
      specialty: "Oncology",
    });
    expect(result.current.data).toEqual(previewResult);
  });

  it("should handle preview failure", async () => {
    vi.mocked(previewInstructions).mockRejectedValueOnce(
      new Error("Preview failed"),
    );

    const { result } = renderHook(() => usePreviewInstructions(), {
      wrapper: createWrapper(),
    });

    result.current.mutate({ name: "Test" });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });

  it("should preview with override instructions", async () => {
    const previewResult = {
      instructions: "Custom override text",
      is_override: true,
    };
    vi.mocked(previewInstructions).mockResolvedValueOnce(previewResult);

    const { result } = renderHook(() => usePreviewInstructions(), {
      wrapper: createWrapper(),
    });

    result.current.mutate({
      agent_instructions_override: "Custom override text",
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.is_override).toBe(true);
  });
});
