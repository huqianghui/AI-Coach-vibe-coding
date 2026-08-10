import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// Declare mock values that tests can change
let mockToken: string | null = null;
let mockUser: { role: string; full_name: string } | null = null;
let mockIsLoading = false;

vi.mock("@/stores/auth-store", () => ({
  useAuthStore: () => ({
    token: mockToken,
    user: mockUser,
    isAuthenticated: !!mockToken,
    setAuth: vi.fn(),
    clearAuth: vi.fn(),
  }),
}));

vi.mock("@/hooks/use-auth", () => ({
  useMe: () => ({
    isLoading: mockIsLoading,
    data: mockUser,
  }),
}));


describe("ProtectedRoute", () => {
  it("redirects to /login when no token is present", async () => {
    mockToken = null;
    mockUser = null;
    mockIsLoading = false;

    const { ProtectedRoute } = await import("./auth-guard");

    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter initialEntries={["/user/dashboard"]}>
          <Routes>
            <Route element={<ProtectedRoute />}>
              <Route path="/user/dashboard" element={<div>Dashboard</div>} />
            </Route>
            <Route path="/login" element={<div>Login Page</div>} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(screen.getByText("Login Page")).toBeInTheDocument();
  });

  it("shows loading state when token exists but user is loading", async () => {
    mockToken = "valid-token";
    mockUser = null;
    mockIsLoading = true;

    const { ProtectedRoute } = await import("./auth-guard");

    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter initialEntries={["/user/dashboard"]}>
          <Routes>
            <Route element={<ProtectedRoute />}>
              <Route path="/user/dashboard" element={<div>Dashboard</div>} />
            </Route>
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(screen.getByText("Loading...")).toBeInTheDocument();
  });

  it("renders child route when authenticated and loaded", async () => {
    mockToken = "valid-token";
    mockUser = { role: "user", full_name: "Test" };
    mockIsLoading = false;

    const { ProtectedRoute } = await import("./auth-guard");

    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter initialEntries={["/user/dashboard"]}>
          <Routes>
            <Route element={<ProtectedRoute />}>
              <Route path="/user/dashboard" element={<div>Dashboard</div>} />
            </Route>
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(screen.getByText("Dashboard")).toBeInTheDocument();
  });
});

describe("AdminRoute", () => {
  it("redirects when the authenticated user profile is missing", async () => {
    mockToken = "valid-token";
    mockUser = null;
    mockIsLoading = false;

    const { AdminRoute } = await import("./auth-guard");
    render(
      <MemoryRouter initialEntries={["/admin/dashboard"]}>
        <Routes>
          <Route element={<AdminRoute />}>
            <Route path="/admin/dashboard" element={<div>Admin Dashboard</div>} />
          </Route>
          <Route path="/user/dashboard" element={<div>User Dashboard</div>} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText("User Dashboard")).toBeInTheDocument();
  });

  it("redirects non-admin users to /user/dashboard", async () => {
    mockToken = "valid-token";
    mockUser = { role: "user", full_name: "Regular User" };
    mockIsLoading = false;

    const { AdminRoute } = await import("./auth-guard");

    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter initialEntries={["/admin/dashboard"]}>
          <Routes>
            <Route element={<AdminRoute />}>
              <Route path="/admin/dashboard" element={<div>Admin Dashboard</div>} />
            </Route>
            <Route path="/user/dashboard" element={<div>User Dashboard</div>} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(screen.getByText("User Dashboard")).toBeInTheDocument();
  });

  it("renders admin route for admin users", async () => {
    mockToken = "valid-token";
    mockUser = { role: "admin", full_name: "Admin User" };
    mockIsLoading = false;

    const { AdminRoute } = await import("./auth-guard");

    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter initialEntries={["/admin/dashboard"]}>
          <Routes>
            <Route element={<AdminRoute />}>
              <Route path="/admin/dashboard" element={<div>Admin Dashboard</div>} />
            </Route>
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(screen.getByText("Admin Dashboard")).toBeInTheDocument();
  });
});

describe("GuestRoute", () => {
  it("renders child routes when not authenticated", async () => {
    mockToken = null;
    mockUser = null;
    mockIsLoading = false;

    const { GuestRoute } = await import("./auth-guard");

    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter initialEntries={["/login"]}>
          <Routes>
            <Route element={<GuestRoute />}>
              <Route path="/login" element={<div>Login Form</div>} />
            </Route>
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(screen.getByText("Login Form")).toBeInTheDocument();
  });

  it("redirects admin users to /admin/dashboard", async () => {
    mockToken = "valid-token";
    mockUser = { role: "admin", full_name: "Admin" };
    mockIsLoading = false;

    const { GuestRoute } = await import("./auth-guard");

    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter initialEntries={["/login"]}>
          <Routes>
            <Route element={<GuestRoute />}>
              <Route path="/login" element={<div>Login Form</div>} />
            </Route>
            <Route path="/admin/dashboard" element={<div>Admin Dashboard</div>} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(screen.getByText("Admin Dashboard")).toBeInTheDocument();
  });

  it("redirects regular users to /user/dashboard", async () => {
    mockToken = "valid-token";
    mockUser = { role: "user", full_name: "User" };
    mockIsLoading = false;

    const { GuestRoute } = await import("./auth-guard");

    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter initialEntries={["/login"]}>
          <Routes>
            <Route element={<GuestRoute />}>
              <Route path="/login" element={<div>Login Form</div>} />
            </Route>
            <Route path="/user/dashboard" element={<div>User Dashboard</div>} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(screen.getByText("User Dashboard")).toBeInTheDocument();
  });
});
