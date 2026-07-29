import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      (opts?.defaultValue as string) ?? key,
    i18n: { language: "en-US" },
  }),
}));

// Mock hooks to avoid real API calls
vi.mock("@/hooks/use-hcp-profiles", () => ({
  useHcpProfiles: () => ({ data: { items: [] } }),
  useHcpProfile: () => ({ data: undefined }),
  useCreateHcpProfile: () => ({ mutate: vi.fn() }),
  useUpdateHcpProfile: () => ({ mutate: vi.fn() }),
  useDeleteHcpProfile: () => ({ mutate: vi.fn() }),
  useRetrySyncHcpProfile: () => ({ mutateAsync: vi.fn() }),
  useBatchSyncAgents: () => ({ mutateAsync: vi.fn() }),
  usePreviewInstructions: () => ({ mutateAsync: vi.fn() }),
}));

vi.mock("@/hooks/use-scenarios", () => ({
  useScenarios: () => ({ data: { items: [] } }),
  useCreateScenario: () => ({ mutate: vi.fn() }),
  useUpdateScenario: () => ({ mutate: vi.fn() }),
  useDeleteScenario: () => ({ mutate: vi.fn() }),
  useCloneScenario: () => ({ mutate: vi.fn() }),
  useTransitionScenarioStatus: () => ({ mutate: vi.fn() }),
}));

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock("@/hooks/use-azure-config", () => ({
  useServiceConfigs: () => ({ data: [], isLoading: false }),
  useUpdateServiceConfig: () => ({ mutate: vi.fn() }),
  useTestServiceConnection: () => ({ mutateAsync: vi.fn() }),
  useAIFoundryConfig: () => ({ data: undefined, isLoading: false }),
  useUpdateAIFoundry: () => ({ mutateAsync: vi.fn() }),
  useTestAIFoundry: () => ({ mutateAsync: vi.fn() }),
}));

vi.mock("@/hooks/use-region-capabilities", () => ({
  useRegionCapabilities: () => ({ data: undefined, isError: false }),
}));

function wrapper({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe("HcpProfilesPage", () => {
  it("renders the HCP profiles page with empty state", async () => {
    const { default: HcpProfilesPage } = await import("./hcp-profiles");
    render(<HcpProfilesPage />, { wrapper });

    // When no profile is selected, shows the empty body message
    // There may be multiple instances (HcpList empty + main area empty)
    const elements = screen.getAllByText("hcp.emptyBody");
    expect(elements.length).toBeGreaterThanOrEqual(1);
  });
});

describe("ScenariosPage", () => {
  it("renders the scenarios page with title and create button", async () => {
    const { default: ScenariosPage } = await import("./scenarios");
    render(<ScenariosPage />, { wrapper });

    expect(screen.getByText("scenarios.title")).toBeInTheDocument();
    expect(screen.getByText("scenarios.createButton")).toBeInTheDocument();
  });

  it("renders status filter options", async () => {
    const { default: ScenariosPage } = await import("./scenarios");
    render(<ScenariosPage />, { wrapper });

    // The "All" select trigger text should be visible
    expect(screen.getByText("all")).toBeInTheDocument();
  });
});

describe("AzureConfigPage", () => {
  it("renders the Azure config page with title", async () => {
    const { default: AzureConfigPage } = await import("./azure-config");
    render(<AzureConfigPage />, { wrapper });

    expect(screen.getByText("azureConfig.title")).toBeInTheDocument();
  });

  it("renders all Azure service cards", async () => {
    const { default: AzureConfigPage } = await import("./azure-config");
    render(<AzureConfigPage />, { wrapper });

    expect(screen.getByText("Azure OpenAI")).toBeInTheDocument();
    expect(screen.getByText("Azure Speech (STT)")).toBeInTheDocument();
    expect(screen.getByText("Azure Speech (TTS)")).toBeInTheDocument();
    expect(screen.getByText("Azure AI Avatar")).toBeInTheDocument();
    expect(
      screen.getByText("Azure Content Understanding"),
    ).toBeInTheDocument();
  });

  it("renders service descriptions", async () => {
    const { default: AzureConfigPage } = await import("./azure-config");
    render(<AzureConfigPage />, { wrapper });

    expect(
      screen.getByText("LLM for AI coaching conversations and scoring"),
    ).toBeInTheDocument();
  });
});
