import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import UserManagementPage from "./users";

vi.mock("react-i18next", async () => {
  const { createTestTranslator } = await import("@/test/i18n-mock");
  return {
    useTranslation: (namespace?: string | string[]) => ({
      t: createTestTranslator(namespace),
      i18n: { changeLanguage: vi.fn(), language: "en-US" },
    }),
  };
});

const mockUsers = [
  { id: "u1", username: "awang", email: "alice@example.com", full_name: "Alice Wang", role: "MR", is_active: true, preferred_language: "en", business_unit: "Oncology", created_at: "2025-01-01" },
  { id: "u2", username: "bzhang", email: "bob@example.com", full_name: "Bob Zhang", role: "DM", is_active: true, preferred_language: "en", business_unit: "Hematology", created_at: "2025-02-01" },
  { id: "u3", username: "clee", email: "carol@example.com", full_name: "Carol Lee", role: "Admin", is_active: true, preferred_language: "en", business_unit: "Oncology", created_at: "2025-03-01" },
  { id: "u4", username: "dchen", email: "david@example.com", full_name: "David Chen", role: "MR", is_active: false, preferred_language: "en", business_unit: "Hematology", created_at: "2025-04-01" },
  { id: "u5", username: "ewu", email: "emily@example.com", full_name: "Emily Wu", role: "MR", is_active: true, preferred_language: "en", business_unit: "Oncology", created_at: "2025-05-01" },
  { id: "u6", username: "fli", email: "frank@example.com", full_name: "Frank Li", role: "DM", is_active: true, preferred_language: "en", business_unit: "Immunology", created_at: "2025-06-01" },
  { id: "u7", username: "ghuang", email: "grace@example.com", full_name: "Grace Huang", role: "MR", is_active: false, preferred_language: "en", business_unit: "Hematology", created_at: "2025-07-01" },
  { id: "u8", username: "hzhao", email: "henry@example.com", full_name: "Henry Zhao", role: "MR", is_active: true, preferred_language: "en", business_unit: "Oncology", created_at: "2025-08-01" },
  { id: "u9", username: "ijin", email: "iris@example.com", full_name: "Iris Jin", role: "Admin", is_active: true, preferred_language: "en", business_unit: "Immunology", created_at: "2025-09-01" },
  { id: "u10", username: "jyang", email: "jack@example.com", full_name: "Jack Yang", role: "MR", is_active: true, preferred_language: "en", business_unit: "Neurology", created_at: "2025-10-01" },
  { id: "u11", username: "kxu", email: "karen@example.com", full_name: "Karen Xu", role: "DM", is_active: true, preferred_language: "en", business_unit: "Oncology", created_at: "2025-11-01" },
  { id: "u12", username: "lma", email: "leo@example.com", full_name: "Leo Ma", role: "MR", is_active: false, preferred_language: "en", business_unit: "Hematology", created_at: "2025-12-01" },
];

let mockSearch = "";

vi.mock("@/hooks/use-users", () => ({
  useUsers: (params: { page: number; page_size: number; search?: string }) => {
    mockSearch = params.search ?? "";
    const filtered = mockSearch
      ? mockUsers.filter(
          (u) =>
            u.full_name.toLowerCase().includes(mockSearch.toLowerCase()) ||
            u.email.toLowerCase().includes(mockSearch.toLowerCase()),
        )
      : mockUsers;
    const pageSize = params.page_size;
    const start = (params.page - 1) * pageSize;
    const paged = filtered.slice(start, start + pageSize);
    return {
      data: {
        items: paged,
        total: filtered.length,
        page: params.page,
        page_size: pageSize,
        total_pages: Math.ceil(filtered.length / pageSize),
      },
      isLoading: false,
    };
  },
  useDeleteUser: () => ({ mutate: vi.fn() }),
  useUpdateUser: () => ({ mutate: vi.fn() }),
}));

describe("UserManagementPage", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders the page title and description", () => {
    render(<UserManagementPage />);
    expect(screen.getByText("User Management")).toBeInTheDocument();
    expect(
      screen.getByText("Manage platform users, roles and permissions"),
    ).toBeInTheDocument();
  });

  it("renders filter controls", () => {
    render(<UserManagementPage />);
    // Source has search input and role/status filter selects
    expect(screen.getByPlaceholderText("Search by name or email...")).toBeInTheDocument();
  });

  it("renders the table header columns", () => {
    render(<UserManagementPage />);
    expect(screen.getByText("Name")).toBeInTheDocument();
    expect(screen.getByText("Email")).toBeInTheDocument();
    expect(screen.getByText("Role")).toBeInTheDocument();
    expect(screen.getByText("BU")).toBeInTheDocument();
    expect(screen.getByText("Status")).toBeInTheDocument();
  });

  it("renders first page of users (10 users)", () => {
    render(<UserManagementPage />);
    // With 12 mock users and PAGE_SIZE=10, page 1 shows first 10
    expect(screen.getByText("Alice Wang")).toBeInTheDocument();
    expect(screen.getByText("Jack Yang")).toBeInTheDocument();
    // Users 11 and 12 should NOT be on page 1
    expect(screen.queryByText("Karen Xu")).not.toBeInTheDocument();
    expect(screen.queryByText("Leo Ma")).not.toBeInTheDocument();
  });

  it("shows pagination controls", () => {
    render(<UserManagementPage />);
    expect(screen.getByText("Previous")).toBeInTheDocument();
    expect(screen.getByText("Next")).toBeInTheDocument();
    expect(screen.getByText("1 / 2")).toBeInTheDocument();
  });

  it("navigates to page 2", async () => {
    render(<UserManagementPage />);
    const user = userEvent.setup();
    await user.click(screen.getByText("Next"));
    // Page 2 should show remaining users
    expect(screen.getByText("Karen Xu")).toBeInTheDocument();
    expect(screen.getByText("Leo Ma")).toBeInTheDocument();
    // Page 1 users should no longer be visible
    expect(screen.queryByText("Alice Wang")).not.toBeInTheDocument();
  });

  it("Previous button is disabled on page 1", () => {
    render(<UserManagementPage />);
    const prevBtn = screen.getByText("Previous").closest("button");
    expect(prevBtn).toBeDisabled();
  });

  it("filters users by search query", async () => {
    render(<UserManagementPage />);
    const user = userEvent.setup();
    const searchInput = screen.getByPlaceholderText(
      "Search by name or email...",
    );
    await user.type(searchInput, "Alice");
    expect(screen.getByText("Alice Wang")).toBeInTheDocument();
    expect(screen.queryByText("Bob Zhang")).not.toBeInTheDocument();
  });

  it("shows 'No users found' when search yields no results", async () => {
    render(<UserManagementPage />);
    const user = userEvent.setup();
    const searchInput = screen.getByPlaceholderText(
      "Search by name or email...",
    );
    await user.type(searchInput, "zzzzzznotfound");
    expect(screen.getByText("No users found")).toBeInTheDocument();
  });

  it("renders user avatar initials", () => {
    render(<UserManagementPage />);
    expect(screen.getByText("AW")).toBeInTheDocument(); // Alice Wang
    expect(screen.getByText("BZ")).toBeInTheDocument(); // Bob Zhang
  });

  it("renders role badges", () => {
    render(<UserManagementPage />);
    // Multiple MR badges exist
    const mrBadges = screen.getAllByText("MR");
    expect(mrBadges.length).toBeGreaterThan(0);
    expect(screen.getAllByText("DM").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Admin").length).toBeGreaterThan(0);
  });

  it("renders status indicators", () => {
    render(<UserManagementPage />);
    // Active and Inactive statuses should appear
    const activeStatuses = screen.getAllByText("Active");
    const inactiveStatuses = screen.getAllByText("Inactive");
    expect(activeStatuses.length).toBeGreaterThan(0);
    expect(inactiveStatuses.length).toBeGreaterThan(0);
  });

  it("resets page to 1 when search changes", async () => {
    render(<UserManagementPage />);
    const user = userEvent.setup();
    // Navigate to page 2 first
    await user.click(screen.getByText("Next"));
    expect(screen.getByText("2 / 2")).toBeInTheDocument();
    // Type in search
    const searchInput = screen.getByPlaceholderText(
      "Search by name or email...",
    );
    await user.type(searchInput, "A");
    // Page should reset (pagination may or may not show depending on filtered count)
    // Just verify the search works
    expect(screen.queryByText("2 / 2")).not.toBeInTheDocument();
  });
});
