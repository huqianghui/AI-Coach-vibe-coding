import { beforeEach, describe, expect, it, vi } from "vitest";
import apiClient from "./client";
import { deleteUser, getUsers, updateUser } from "./users";

vi.mock("./client", () => ({
  default: { get: vi.fn(), patch: vi.fn(), delete: vi.fn() },
}));

const client = apiClient as unknown as {
  get: ReturnType<typeof vi.fn>;
  patch: ReturnType<typeof vi.fn>;
  delete: ReturnType<typeof vi.fn>;
};

describe("Users API client", () => {
  beforeEach(() => vi.clearAllMocks());

  it("lists users with and without filters", async () => {
    const response = { items: [], total: 0, page: 1, page_size: 20, total_pages: 0 };
    client.get.mockResolvedValue({ data: response });

    await expect(getUsers()).resolves.toEqual(response);
    expect(client.get).toHaveBeenLastCalledWith("/users", { params: undefined });

    const params = { page: 2, search: "alice", role: "admin", is_active: false };
    await expect(getUsers(params)).resolves.toEqual(response);
    expect(client.get).toHaveBeenLastCalledWith("/users", { params });
  });

  it("updates and deletes a user", async () => {
    const updated = { id: "u1", full_name: "Alice", is_active: false };
    client.patch.mockResolvedValue({ data: updated });
    client.delete.mockResolvedValue({ status: 204 });

    await expect(updateUser("u1", { is_active: false })).resolves.toEqual(updated);
    expect(client.patch).toHaveBeenCalledWith("/users/u1", { is_active: false });

    await expect(deleteUser("u1")).resolves.toBeUndefined();
    expect(client.delete).toHaveBeenCalledWith("/users/u1");
  });

  it("propagates transport failures", async () => {
    client.get.mockRejectedValueOnce(new Error("list failed"));
    client.patch.mockRejectedValueOnce(new Error("update failed"));
    client.delete.mockRejectedValueOnce(new Error("delete failed"));

    await expect(getUsers()).rejects.toThrow("list failed");
    await expect(updateUser("u1", {})).rejects.toThrow("update failed");
    await expect(deleteUser("u1")).rejects.toThrow("delete failed");
  });
});
