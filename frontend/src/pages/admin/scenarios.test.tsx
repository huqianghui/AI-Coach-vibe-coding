import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import ScenariosPage from "./scenarios";

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

const mockDeleteMutate = vi.fn();
const mockCloneMutate = vi.fn();
const mockCreateGroupMutate = vi.fn();
const mockUpdateGroupMutate = vi.fn();
const mockTransitionGroupMutate = vi.fn();
const mockDeleteGroupMutate = vi.fn();
const mockNavigate = vi.fn();

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: { defaultValue?: string }) => opts?.defaultValue ?? key,
    i18n: { changeLanguage: vi.fn(), language: "en" },
  }),
}));

const scenarios = [
  { id: "s1", name: "Test Scenario", product: "ProductA", status: "active" },
];

vi.mock("@/hooks/use-scenarios", () => ({
  useScenarios: () => ({ data: { items: scenarios, total: 1 } }),
  useDeleteScenario: () => ({ mutate: mockDeleteMutate }),
  useCloneScenario: () => ({ mutate: mockCloneMutate }),
  useTransitionScenarioStatus: () => ({ mutate: vi.fn() }),
}));

vi.mock("@/hooks/use-scenario-groups", () => ({
  useScenarioGroups: () => ({ data: { items: [], total: 0 } }),
  useCreateScenarioGroup: () => ({ mutate: mockCreateGroupMutate, isPending: false }),
  useUpdateScenarioGroup: () => ({ mutate: mockUpdateGroupMutate, isPending: false }),
  useTransitionScenarioGroupStatus: () => ({ mutate: mockTransitionGroupMutate }),
  useDeleteScenarioGroup: () => ({ mutate: mockDeleteGroupMutate }),
}));

vi.mock("@/components/admin/scenario-table", () => ({
  ScenarioTable: (props: {
    scenarios: unknown[];
    onDelete: (id: string) => void;
    onClone: (id: string) => void;
  }) => (
    <div data-testid="scenario-table">
      <button onClick={() => props.onDelete("s1")}>Delete</button>
      <button onClick={() => props.onClone("s1")}>Clone</button>
    </div>
  ),
}));

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ScenariosPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ScenariosPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockDeleteMutate.mockReset();
    mockCloneMutate.mockReset();
    mockCreateGroupMutate.mockReset();
    mockUpdateGroupMutate.mockReset();
    mockTransitionGroupMutate.mockReset();
    mockDeleteGroupMutate.mockReset();
    mockNavigate.mockReset();
  });

  it("renders title and create button", () => {
    renderPage();
    expect(screen.getByText("scenarios.title")).toBeInTheDocument();
    expect(screen.getByText("scenarios.createButton")).toBeInTheDocument();
  });

  it("renders scenario table", () => {
    renderPage();
    expect(screen.getByTestId("scenario-table")).toBeInTheDocument();
  });

  it("navigates to create page", async () => {
    renderPage();
    await userEvent.setup().click(screen.getByText("scenarios.createButton"));
    expect(mockNavigate).toHaveBeenCalledWith("/admin/scenarios/new");
  });

  it("shows delete confirmation dialog", async () => {
    renderPage();
    await userEvent.setup().click(screen.getByText("Delete"));
    expect(screen.getByText("scenarios.deleteTitle")).toBeInTheDocument();
    expect(screen.getByText("scenarios.deleteConfirm")).toBeInTheDocument();
  });

  it("confirms delete and calls mutation", async () => {
    renderPage();
    const user = userEvent.setup();
    await user.click(screen.getByText("Delete"));
    const deleteButtons = screen.getAllByText("delete");
    const confirmBtn = deleteButtons.find((b) => b.closest("[role='dialog']"));
    if (confirmBtn) await user.click(confirmBtn);
    expect(mockDeleteMutate).toHaveBeenCalledWith("s1", expect.anything());
  });

  it("cancels delete dialog", async () => {
    renderPage();
    const user = userEvent.setup();
    await user.click(screen.getByText("Delete"));
    expect(screen.getByText("scenarios.deleteTitle")).toBeInTheDocument();
    await user.click(screen.getByText("cancel"));
    expect(screen.queryByText("scenarios.deleteTitle")).not.toBeInTheDocument();
  });

  it("calls clone mutation", async () => {
    renderPage();
    await userEvent.setup().click(screen.getByText("Clone"));
    expect(mockCloneMutate).toHaveBeenCalledWith("s1", expect.anything());
  });

  it("renders group scenario management", () => {
    renderPage();
    expect(screen.getByText("合并场景")).toBeInTheDocument();
    expect(screen.getByText("创建组合场景")).toBeInTheDocument();
  });

  it("triggers delete onSuccess callback", async () => {
    mockDeleteMutate.mockImplementation((_id: string, opts: { onSuccess?: () => void }) => {
      opts?.onSuccess?.();
    });
    renderPage();
    const user = userEvent.setup();
    await user.click(screen.getByText("Delete"));
    const deleteButtons = screen.getAllByText("delete");
    const confirmBtn = deleteButtons.find((b) => b.closest("[role='dialog']"));
    if (confirmBtn) await user.click(confirmBtn);
    // Dialog should be closed after success
    expect(screen.queryByText("scenarios.deleteTitle")).not.toBeInTheDocument();
  });
});
