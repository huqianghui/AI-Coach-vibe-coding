import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { toast } from "sonner";
import AzureConfigPage from "./azure-config";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: { defaultValue?: string }) =>
      opts?.defaultValue ?? key,
    i18n: { changeLanguage: vi.fn(), language: "en" },
  }),
}));

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

const mockServiceMutate = vi.fn();
const mockMutateAsync = vi.fn();
const mockFoundryMutate = vi.fn();
const mockTestFoundryMutate = vi.fn();

// Default mock data -- overridden per test
let mockServiceConfigsReturn: {
  data:
    | Array<{
        service_name: string;
        display_name: string;
        endpoint: string;
        masked_key: string;
        model_or_deployment: string;
        region: string;
        is_active: boolean;
        updated_at: string;
      }>
    | undefined;
  isLoading: boolean;
} = {
  data: [
    {
      service_name: "azure_openai",
      display_name: "Azure OpenAI",
      endpoint: "https://test.openai.azure.com",
      masked_key: "sk-****",
      model_or_deployment: "gpt-4o",
      region: "eastus",
      is_active: true,
      updated_at: "2026-03-27T00:00:00Z",
    },
  ],
  isLoading: false,
};

let mockFoundryReturn: {
  data:
    | {
        endpoint: string;
        region: string;
        model_or_deployment: string;
        default_project: string;
        masked_key: string;
      }
    | undefined;
  isLoading: boolean;
} = {
  data: {
    endpoint: "https://foundry.azure.com",
    region: "eastus",
    model_or_deployment: "gpt-4o",
    default_project: "my-project",
    masked_key: "fk-****",
  },
  isLoading: false,
};

vi.mock("@/hooks/use-azure-config", () => ({
  useServiceConfigs: () => mockServiceConfigsReturn,
  useUpdateServiceConfig: () => ({
    mutate: mockServiceMutate,
  }),
  useTestServiceConnection: () => ({
    mutateAsync: mockMutateAsync,
    isPending: false,
  }),
  useAIFoundryConfig: () => mockFoundryReturn,
  useUpdateAIFoundry: () => ({
    mutate: mockFoundryMutate,
    isPending: false,
  }),
  useTestAIFoundry: () => ({
    mutate: mockTestFoundryMutate,
    isPending: false,
  }),
}));

let mockRegionCapsReturn: {
  data:
    | {
        region: string;
        services: Record<string, { available: boolean; note: string }>;
      }
    | undefined;
  isError: boolean;
} = {
  data: undefined,
  isError: false,
};

vi.mock("@/hooks/use-region-capabilities", () => ({
  useRegionCapabilities: () => mockRegionCapsReturn,
}));

function renderWithProviders() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <AzureConfigPage />
    </QueryClientProvider>,
  );
}

describe("AzureConfigPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockServiceConfigsReturn = {
      data: [
        {
          service_name: "azure_openai",
          display_name: "Azure OpenAI",
          endpoint: "https://test.openai.azure.com",
          masked_key: "sk-****",
          model_or_deployment: "gpt-4o",
          region: "eastus",
          is_active: true,
          updated_at: "2026-03-27T00:00:00Z",
        },
      ],
      isLoading: false,
    };
    mockFoundryReturn = {
      data: {
        endpoint: "https://foundry.azure.com",
        region: "eastus",
        model_or_deployment: "gpt-4o",
        default_project: "my-project",
        masked_key: "fk-****",
      },
      isLoading: false,
    };
    mockRegionCapsReturn = {
      data: undefined,
      isError: false,
    };
  });

  it("renders the page title", () => {
    renderWithProviders();
    expect(screen.getByText("azureConfig.title")).toBeInTheDocument();
  });

  it("renders Test All Services button", () => {
    renderWithProviders();
    expect(screen.getByText("Test All Services")).toBeInTheDocument();
  });

  it("renders AI Foundry master config section", () => {
    renderWithProviders();
    expect(screen.getByText("azureConfig.aiFoundry.title")).toBeInTheDocument();
    expect(screen.getByText("azureConfig.aiFoundry.description")).toBeInTheDocument();
  });

  it("renders all 7 Azure service names", () => {
    renderWithProviders();
    expect(screen.getByText("Azure OpenAI")).toBeInTheDocument();
    expect(screen.getByText("Azure Speech (STT)")).toBeInTheDocument();
    expect(screen.getByText("Azure Speech (TTS)")).toBeInTheDocument();
    expect(screen.getByText("Azure AI Avatar")).toBeInTheDocument();
    expect(screen.getByText("Azure Content Understanding")).toBeInTheDocument();
    expect(screen.getByText("Azure OpenAI Realtime")).toBeInTheDocument();
    expect(screen.getByText("Azure Voice Live API")).toBeInTheDocument();
  });

  it("renders all service descriptions", () => {
    renderWithProviders();
    expect(screen.getByText("LLM for AI coaching conversations and scoring")).toBeInTheDocument();
    expect(screen.getByText("Speech-to-text for voice input recognition")).toBeInTheDocument();
    expect(screen.getByText("Text-to-speech for HCP voice responses")).toBeInTheDocument();
    expect(screen.getByText("Digital human avatar for HCP visualization")).toBeInTheDocument();
    expect(screen.getByText("Multimodal evaluation for training materials")).toBeInTheDocument();
    expect(screen.getByText("Real-time audio streaming for voice conversations")).toBeInTheDocument();
    expect(screen.getByText("Real-time voice coaching with configurable model")).toBeInTheDocument();
  });

  // ---- Loading state ----

  it("shows loading skeleton when configs are loading", () => {
    mockServiceConfigsReturn = { data: undefined, isLoading: true };
    renderWithProviders();
    // Should not show the title when loading
    expect(screen.queryByText("azureConfig.title")).not.toBeInTheDocument();
    // Should not render service cards
    expect(screen.queryByText("Azure OpenAI")).not.toBeInTheDocument();
  });

  it("shows loading skeleton when foundry config is loading", () => {
    mockFoundryReturn = { data: undefined, isLoading: true };
    renderWithProviders();
    expect(screen.queryByText("azureConfig.title")).not.toBeInTheDocument();
  });

  // ---- Toggle service ----

  it("renders toggle switches for each service", () => {
    renderWithProviders();
    // Each service has a switch with aria-label "Enable {name}"
    const switches = screen.getAllByRole("switch");
    expect(switches.length).toBe(7);
  });

  // ---- handleTestAll ----

  it("tests all configured services when Test All is clicked", async () => {
    mockServiceConfigsReturn = {
      data: [
        {
          service_name: "azure_openai",
          display_name: "Azure OpenAI",
          endpoint: "https://test.openai.azure.com",
          masked_key: "sk-****",
          model_or_deployment: "gpt-4o",
          region: "eastus",
          is_active: true,
          updated_at: "2026-03-27T00:00:00Z",
        },
        {
          service_name: "azure_speech_stt",
          display_name: "Azure Speech STT",
          endpoint: "https://speech.azure.com",
          masked_key: "sp-****",
          model_or_deployment: "",
          region: "eastus",
          is_active: true,
          updated_at: "2026-03-27T00:00:00Z",
        },
      ],
      isLoading: false,
    };

    mockMutateAsync
      .mockResolvedValueOnce({
        service_name: "azure_openai",
        success: true,
        message: "Connected",
      })
      .mockResolvedValueOnce({
        service_name: "azure_speech_stt",
        success: false,
        message: "Invalid key",
      });

    renderWithProviders();

    const testAllButton = screen.getByText("Test All Services").closest("button")!;
    await userEvent.click(testAllButton);

    await vi.waitFor(() => {
      expect(mockMutateAsync).toHaveBeenCalledTimes(2);
    });
    expect(toast.success).toHaveBeenCalledWith("Azure OpenAI: Connected");
    expect(toast.error).toHaveBeenCalledWith("Azure Speech STT: Invalid key");
  });

  it("skips inactive services without endpoints in Test All", async () => {
    mockServiceConfigsReturn = {
      data: [
        {
          service_name: "azure_openai",
          display_name: "Azure OpenAI",
          endpoint: "", // No endpoint configured
          masked_key: "",
          model_or_deployment: "",
          region: "",
          is_active: false,
          updated_at: "2026-03-27T00:00:00Z",
        },
      ],
      isLoading: false,
    };

    renderWithProviders();
    await userEvent.click(screen.getByText("Test All Services").closest("button")!);

    await vi.waitFor(() => {
      expect(mockMutateAsync).not.toHaveBeenCalled();
    });
  });

  it("shows error toast when individual test in Test All throws", async () => {
    mockServiceConfigsReturn = {
      data: [
        {
          service_name: "azure_openai",
          display_name: "Azure OpenAI",
          endpoint: "https://test.openai.azure.com",
          masked_key: "sk-****",
          model_or_deployment: "gpt-4o",
          region: "eastus",
          is_active: true,
          updated_at: "2026-03-27T00:00:00Z",
        },
      ],
      isLoading: false,
    };

    mockMutateAsync.mockRejectedValue(new Error("Network error"));

    renderWithProviders();
    await userEvent.click(screen.getByText("Test All Services").closest("button")!);

    await vi.waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith("Azure OpenAI: Connection failed");
    });
  });

  // ---- Region status display ----

  it("renders region available badge when regionCaps shows service available", () => {
    mockRegionCapsReturn = {
      data: {
        region: "eastus",
        services: {
          azure_openai: { available: true, note: "" },
        },
      },
      isError: false,
    };
    renderWithProviders();

    // The RegionBadge with status "available" renders a role="status" span
    const statusBadges = screen.getAllByRole("status");
    expect(statusBadges.length).toBeGreaterThanOrEqual(1);
  });

  it("renders region unavailable badge when regionCaps shows service unavailable", () => {
    mockRegionCapsReturn = {
      data: {
        region: "eastus",
        services: {
          azure_openai: { available: false, note: "" },
        },
      },
      isError: false,
    };
    renderWithProviders();

    const statusBadges = screen.getAllByRole("status");
    expect(statusBadges.length).toBeGreaterThanOrEqual(1);
  });

  it("renders region unknown badge when regionCaps has error", () => {
    mockRegionCapsReturn = {
      data: undefined,
      isError: true,
    };
    renderWithProviders();

    // All services should show "unknown" status
    const statusBadges = screen.getAllByRole("status");
    expect(statusBadges.length).toBeGreaterThanOrEqual(1);
  });

  // ---- AI Foundry save ----

  it("calls foundry update mutation when saving foundry config", async () => {
    renderWithProviders();
    // The "Save" button in AI Foundry section
    const saveButtons = screen.getAllByText("azureConfig.saveConfig");
    expect(saveButtons.length).toBeGreaterThanOrEqual(1);
    await userEvent.click(saveButtons[0]!);

    expect(mockFoundryMutate).toHaveBeenCalledWith(
      expect.objectContaining({
        endpoint: "https://foundry.azure.com",
        region: "eastus",
        model_or_deployment: "gpt-4o",
        default_project: "my-project",
      }),
      expect.objectContaining({
        onSuccess: expect.any(Function),
        onError: expect.any(Function),
      }),
    );
  });

  it("lets admins edit the AI Foundry master region", async () => {
    renderWithProviders();

    const regionInput = screen.getByDisplayValue("eastus");
    await userEvent.clear(regionInput);
    await userEvent.type(regionInput, "eastus2");

    const saveButtons = screen.getAllByText("azureConfig.saveConfig");
    await userEvent.click(saveButtons[0]!);

    expect(mockFoundryMutate).toHaveBeenCalledWith(
      expect.objectContaining({
        region: "eastus2",
      }),
      expect.any(Object),
    );
  });

  it("shows success toast on foundry save success", async () => {
    renderWithProviders();
    const saveButtons = screen.getAllByText("azureConfig.saveConfig");
    await userEvent.click(saveButtons[0]!);

    // Extract and call the onSuccess callback
    const call = mockFoundryMutate.mock.calls[0]!;
    const callbacks = call[1] as { onSuccess: () => void; onError: () => void };
    callbacks.onSuccess();

    expect(toast.success).toHaveBeenCalledWith("AI Foundry configuration saved");
  });

  it("shows error toast on foundry save failure", async () => {
    renderWithProviders();
    const saveButtons = screen.getAllByText("azureConfig.saveConfig");
    await userEvent.click(saveButtons[0]!);

    const call = mockFoundryMutate.mock.calls[0]!;
    const callbacks = call[1] as { onSuccess: () => void; onError: () => void };
    callbacks.onError();

    expect(toast.error).toHaveBeenCalledWith("Failed to save configuration");
  });

  // ---- Toggle service switch ----

  it("calls service update when toggling a switch", async () => {
    renderWithProviders();
    // Find the Azure OpenAI switch (labeled "Enable Azure OpenAI")
    const openaiSwitch = screen.getByLabelText("Enable Azure OpenAI");
    await userEvent.click(openaiSwitch);

    expect(mockServiceMutate).toHaveBeenCalledWith(
      expect.objectContaining({
        serviceName: "azure_openai",
        config: expect.objectContaining({
          is_active: false,
        }),
      }),
    );
  });

  // ---- Expand service row ----

  it("expands a service card when clicked to show config form", async () => {
    renderWithProviders();
    // Click on "Azure OpenAI" text to expand
    const openaiBtn = screen.getByText("Azure OpenAI").closest("button")!;
    await userEvent.click(openaiBtn);

    // The expanded content should show "Model" label and Test/Save buttons
    expect(screen.getByText("azureConfig.model")).toBeInTheDocument();
    expect(screen.getByText("Test Connection")).toBeInTheDocument();
  });

  it("expands a service with endpoint override to show endpoint and api key inputs", async () => {
    // Azure Speech (STT) has allowEndpointOverride
    renderWithProviders();
    const sttBtn = screen
      .getByText("Azure Speech (STT)")
      .closest("button")!;
    await userEvent.click(sttBtn);

    // Expanded content should show endpoint override hint and inputs
    expect(
      screen.getByText(
        "Override if this service uses a different Azure resource than the master endpoint.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Endpoint")).toBeInTheDocument();
    expect(
      screen.getByText("API Key (leave empty to use master)"),
    ).toBeInTheDocument();
  });

  it("saves per-service config when Save Config is clicked in expanded row", async () => {
    renderWithProviders();
    // Expand Azure OpenAI
    await userEvent.click(
      screen.getByText("Azure OpenAI").closest("button")!,
    );

    // Find the save button inside the expanded area (not the foundry save)
    // The expanded content has its own "azureConfig.saveConfig" button
    const saveButtons = screen.getAllByText("azureConfig.saveConfig");
    // The second one is inside the expanded content
    const expandedSave = saveButtons[saveButtons.length - 1]!.closest("button")!;
    await userEvent.click(expandedSave);

    expect(mockServiceMutate).toHaveBeenCalledWith(
      expect.objectContaining({
        serviceName: "azure_openai",
        config: expect.objectContaining({
          model_or_deployment: "gpt-4o",
        }),
      }),
      expect.objectContaining({
        onSuccess: expect.any(Function),
        onError: expect.any(Function),
      }),
    );
  });

  it("shows success toast when per-service config save succeeds", async () => {
    renderWithProviders();
    await userEvent.click(
      screen.getByText("Azure OpenAI").closest("button")!,
    );

    const saveButtons = screen.getAllByText("azureConfig.saveConfig");
    await userEvent.click(saveButtons[saveButtons.length - 1]!.closest("button")!);

    // Get the latest call with onSuccess callback
    const lastCall = mockServiceMutate.mock.calls[
      mockServiceMutate.mock.calls.length - 1
    ]!;
    const callbacks = lastCall[1] as {
      onSuccess: () => void;
      onError: () => void;
    };
    callbacks.onSuccess();

    expect(toast.success).toHaveBeenCalledWith("Configuration saved");
  });

  it("shows error toast when per-service config save fails", async () => {
    renderWithProviders();
    await userEvent.click(
      screen.getByText("Azure OpenAI").closest("button")!,
    );

    const saveButtons = screen.getAllByText("azureConfig.saveConfig");
    await userEvent.click(saveButtons[saveButtons.length - 1]!.closest("button")!);

    const lastCall = mockServiceMutate.mock.calls[
      mockServiceMutate.mock.calls.length - 1
    ]!;
    const callbacks = lastCall[1] as {
      onSuccess: () => void;
      onError: () => void;
    };
    callbacks.onError();

    expect(toast.error).toHaveBeenCalledWith("Failed to save configuration");
  });

  // ---- Test individual service ----

  it("tests individual service connection when Test Connection clicked in expanded row", async () => {
    mockMutateAsync.mockResolvedValue({
      success: true,
      message: "Service OK",
    });
    renderWithProviders();
    await userEvent.click(
      screen.getByText("Azure OpenAI").closest("button")!,
    );

    // The expanded row has its own Test Connection button; the first one is
    // the AI Foundry top-level test, so pick the one inside the expanded area.
    const testButtons = screen.getAllByText("azureConfig.testConnection");
    const expandedTestBtn = testButtons[testButtons.length - 1]!.closest("button")!;
    await userEvent.click(expandedTestBtn);

    await vi.waitFor(() => {
      expect(mockMutateAsync).toHaveBeenCalledWith("azure_openai");
    });
    expect(toast.success).toHaveBeenCalledWith("Service OK");
  });

  it("shows error toast when individual service test returns failure", async () => {
    mockMutateAsync.mockResolvedValue({
      success: false,
      message: "Bad credentials",
    });
    renderWithProviders();
    await userEvent.click(
      screen.getByText("Azure OpenAI").closest("button")!,
    );

    const testButtons = screen.getAllByText("azureConfig.testConnection");
    await userEvent.click(testButtons[testButtons.length - 1]!.closest("button")!);

    await vi.waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith("Bad credentials");
    });
  });

  it("shows connectionFailed toast when individual test throws", async () => {
    mockMutateAsync.mockRejectedValue(new Error("Network"));
    renderWithProviders();
    await userEvent.click(
      screen.getByText("Azure OpenAI").closest("button")!,
    );

    const testButtons = screen.getAllByText("azureConfig.testConnection");
    await userEvent.click(testButtons[testButtons.length - 1]!.closest("button")!);

    await vi.waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith("azureConfig.connectionFailed");
    });
  });

  // ---- Foundry Test Connection flow ----

  it("saves then tests foundry when Test Connection is clicked", async () => {
    renderWithProviders();
    const testBtn = screen.getByText("Test Connection").closest("button")!;
    await userEvent.click(testBtn);

    // First saves
    expect(mockFoundryMutate).toHaveBeenCalled();

    // Simulate save success to trigger test
    const saveCall = mockFoundryMutate.mock.calls[0]!;
    const saveCallbacks = saveCall[1] as { onSuccess: () => void };
    saveCallbacks.onSuccess();

    // Then tests
    expect(mockTestFoundryMutate).toHaveBeenCalled();
  });

  it("shows success toast when foundry test succeeds", async () => {
    renderWithProviders();
    const testBtn = screen.getByText("Test Connection").closest("button")!;
    await userEvent.click(testBtn);

    const saveCall = mockFoundryMutate.mock.calls[0]!;
    (saveCall[1] as { onSuccess: () => void }).onSuccess();

    const testCall = mockTestFoundryMutate.mock.calls[0]!;
    const testCallbacks = testCall[1] as {
      onSuccess: (result: { success: boolean; message: string; region?: string }) => void;
    };
    testCallbacks.onSuccess({
      success: true,
      message: "Connected to AI Foundry",
      region: "westus",
    });

    expect(toast.success).toHaveBeenCalledWith(
      "AI Foundry: Connected to AI Foundry",
    );
  });

  it("shows error toast when foundry test fails", async () => {
    renderWithProviders();
    const testBtn = screen.getByText("Test Connection").closest("button")!;
    await userEvent.click(testBtn);

    const saveCall = mockFoundryMutate.mock.calls[0]!;
    (saveCall[1] as { onSuccess: () => void }).onSuccess();

    const testCall = mockTestFoundryMutate.mock.calls[0]!;
    const testCallbacks = testCall[1] as {
      onSuccess: (result: { success: boolean; message: string }) => void;
    };
    testCallbacks.onSuccess({
      success: false,
      message: "Authentication failed",
    });

    expect(toast.error).toHaveBeenCalledWith(
      "AI Foundry: Authentication failed",
    );
  });

  it("shows error toast when foundry test throws", async () => {
    renderWithProviders();
    const testBtn = screen.getByText("Test Connection").closest("button")!;
    await userEvent.click(testBtn);

    const saveCall = mockFoundryMutate.mock.calls[0]!;
    (saveCall[1] as { onSuccess: () => void }).onSuccess();

    const testCall = mockTestFoundryMutate.mock.calls[0]!;
    const testCallbacks = testCall[1] as { onError: () => void };
    testCallbacks.onError();

    expect(toast.error).toHaveBeenCalledWith(
      "AI Foundry: Connection test failed",
    );
  });

  it("shows error toast when foundry test save step fails", async () => {
    renderWithProviders();
    const testBtn = screen.getByText("Test Connection").closest("button")!;
    await userEvent.click(testBtn);

    const saveCall = mockFoundryMutate.mock.calls[0]!;
    (saveCall[1] as { onError: () => void }).onError();

    expect(toast.error).toHaveBeenCalledWith("Failed to save configuration");
  });

  // ---- API key visibility toggle ----

  it("toggles API key visibility in AI Foundry section", async () => {
    renderWithProviders();
    // Find the password input for API key
    const apiKeyInput = screen.getByPlaceholderText(
      "azureConfig.aiFoundry.apiKeyPlaceholder",
    );
    expect(apiKeyInput).toHaveAttribute("type", "password");

    // Click the visibility toggle button (Eye icon button)
    const toggleButtons = apiKeyInput
      .closest("div")!
      .querySelectorAll("button");
    const toggleBtn = toggleButtons[0]!;
    await userEvent.click(toggleBtn);

    expect(apiKeyInput).toHaveAttribute("type", "text");
  });

  // ---- Masked key display ----

  it("displays masked key when foundry data has one", () => {
    renderWithProviders();
    expect(screen.getByText("Current: fk-****")).toBeInTheDocument();
  });

  // ---- Region display ----

  it("shows auto-detected region input when region exists", () => {
    renderWithProviders();
    expect(
      screen.getByText("Region (auto-detected)"),
    ).toBeInTheDocument();
  });

  // ---- Collapse expanded service ----

  it("collapses expanded service when clicked again", async () => {
    renderWithProviders();
    const openaiBtn = screen.getByText("Azure OpenAI").closest("button")!;

    // Expand
    await userEvent.click(openaiBtn);
    expect(screen.getByText("azureConfig.model")).toBeInTheDocument();

    // Collapse
    await userEvent.click(openaiBtn);
    expect(screen.queryByText("azureConfig.model")).not.toBeInTheDocument();
  });
});
