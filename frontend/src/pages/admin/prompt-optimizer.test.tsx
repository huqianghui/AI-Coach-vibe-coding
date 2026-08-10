import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import PromptOptimizerPage from "./prompt-optimizer";
import type { Prompt } from "@/types/prompt";
import { toast } from "sonner";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { changeLanguage: vi.fn(), language: "en" },
  }),
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const mockOptimizePromptMutate = vi.fn();
const mockAdoptRunMutate = vi.fn();
const mockOptimizeTextMutate = vi.fn();
let mockPromptData: Prompt | undefined;
let mockPromptError = false;
let mockOptimizePromptPending = false;
let mockOptimizeTextPending = false;
let mockAdoptPending = false;

const mockPrompt: Prompt = {
  key: "hcp.system",
  name: "HCP System Prompt",
  category: "hcp",
  description: "",
  is_system: true,
  variables: [],
  active_version: {
    id: "v1",
    template_id: "t1",
    version_no: 1,
    content: "Original registry prompt",
    source: "manual",
    parent_version_id: null,
    note: "",
    created_by: "admin",
    is_active: true,
    created_at: "2026-01-01T00:00:00Z",
  },
};

vi.mock("@/hooks/use-prompts", () => ({
  usePrompt: () => ({ data: mockPromptData, isError: mockPromptError }),
  useOptimizePrompt: () => ({
    mutate: mockOptimizePromptMutate,
    isPending: mockOptimizePromptPending,
  }),
  useAdoptRun: () => ({ mutate: mockAdoptRunMutate, isPending: mockAdoptPending }),
  useOptimizeText: () => ({ mutate: mockOptimizeTextMutate, isPending: mockOptimizeTextPending }),
}));

function renderRegistryOptimizer() {
  return render(
    <MemoryRouter
      initialEntries={[
        {
          pathname: "/admin/prompts/hcp.system/optimize",
          state: { source: "registry", returnTo: "/admin/prompts/hcp.system" },
        },
      ]}
    >
      <Routes>
        <Route path="/admin/prompts/:key/optimize" element={<PromptOptimizerPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

function renderTextOptimizer() {
  return render(
    <MemoryRouter
      initialEntries={[
        {
          pathname: "/admin/prompt-optimizer",
          state: {
            source: "text",
            returnTo: "/admin/scoring-rubrics/new",
            resultStorageKey: "promptOptimizer:test",
            content: "Original form prompt",
          },
        },
      ]}
    >
      <Routes>
        <Route path="/admin/prompt-optimizer" element={<PromptOptimizerPage />} />
        <Route path="/admin/scoring-rubrics/new" element={<div>returned</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

function renderStandaloneOptimizer(state?: unknown) {
  return render(
    <MemoryRouter initialEntries={[{ pathname: "/admin/prompt-optimizer", state }]}>
      <Routes>
        <Route path="/admin/prompt-optimizer" element={<PromptOptimizerPage />} />
        <Route path="/admin/prompts" element={<div>prompt-list</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("PromptOptimizerPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    mockPromptData = mockPrompt;
    mockPromptError = false;
    mockOptimizePromptPending = false;
    mockOptimizeTextPending = false;
    mockAdoptPending = false;
  });

  it("optimizes and adopts a registry prompt run", async () => {
    const user = userEvent.setup();
    mockOptimizePromptMutate.mockImplementation((_payload, opts) => {
      opts.onSuccess({ run_id: "run-1", optimized_prompt: "Optimized registry prompt" });
    });

    renderRegistryOptimizer();

    await user.click(screen.getByTestId("run-optimize"));

    expect(mockOptimizePromptMutate).toHaveBeenCalledWith(
      { mode: "system", requirements: null },
      expect.any(Object),
    );
    expect(screen.getByTestId("optimized-text")).toHaveTextContent("Optimized registry prompt");

    await user.click(screen.getByTestId("adopt-run"));

    expect(mockAdoptRunMutate).toHaveBeenCalledWith(
      { run_id: "run-1" },
      expect.any(Object),
    );

    const adoptOptions = mockAdoptRunMutate.mock.calls[0]?.[1] as {
      onSuccess: () => void;
    };
    adoptOptions.onSuccess();
    expect(toast.success).toHaveBeenCalledWith("optimize.adopted");
  });

  it("stores stateless optimized text and returns to the source editor", async () => {
    const user = userEvent.setup();
    mockOptimizeTextMutate.mockImplementation((_payload, opts) => {
      opts.onSuccess({ optimized_prompt: "Optimized form prompt" });
    });

    renderTextOptimizer();

    await user.click(screen.getByTestId("run-optimize"));

    expect(mockOptimizeTextMutate).toHaveBeenCalledWith(
      { prompt: "Original form prompt", mode: "system", requirements: null },
      expect.any(Object),
    );

    await user.click(screen.getByTestId("adopt-run"));

    expect(sessionStorage.getItem("promptOptimizer:test")).toBe("Optimized form prompt");
    await waitFor(() => expect(screen.getByText("returned")).toBeInTheDocument());
  });

  it("requires iteration instructions and sends them when supplied", async () => {
    const user = userEvent.setup();
    renderTextOptimizer();

    await user.click(screen.getByTestId("optimize-mode"));
    await user.click(screen.getByText("optimize.modeIterate"));
    expect(screen.getByTestId("run-optimize")).toBeDisabled();

    await user.type(screen.getByTestId("optimize-requirements"), "Make it concise");
    await user.click(screen.getByTestId("run-optimize"));

    expect(mockOptimizeTextMutate).toHaveBeenCalledWith(
      {
        prompt: "Original form prompt",
        mode: "iterate",
        requirements: "Make it concise",
      },
      expect.any(Object),
    );
  });

  it.each(["registry", "text"])("reports a failed %s optimization", async (kind) => {
    const user = userEvent.setup();
    const mutate = kind === "registry" ? mockOptimizePromptMutate : mockOptimizeTextMutate;
    mutate.mockImplementation((_payload, options) => options.onError());
    if (kind === "registry") renderRegistryOptimizer();
    else renderTextOptimizer();

    await user.click(screen.getByTestId("run-optimize"));

    expect(toast.error).toHaveBeenCalledWith("optimize.failed");
  });

  it("renders the registry load error", () => {
    mockPromptError = true;
    renderRegistryOptimizer();

    expect(screen.getByText("editor.loadError")).toBeInTheDocument();
  });

  it.each([undefined, null, "invalid", {}, { source: "registry" }, { source: "text" }])(
    "rejects malformed standalone state %#",
    (state) => {
      renderStandaloneOptimizer(state);
      expect(screen.getByText("optimize.missingState")).toBeInTheDocument();
    },
  );

  it("returns from missing standalone state to the prompt list", async () => {
    const user = userEvent.setup();
    renderStandaloneOptimizer();

    await user.click(screen.getByRole("button", { name: /optimize.back/i }));

    expect(screen.getByText("prompt-list")).toBeInTheDocument();
  });

  it.each([
    [true, false],
    [false, true],
  ])("shows running while either optimizer mutation is pending", (promptPending, textPending) => {
    mockOptimizePromptPending = promptPending;
    mockOptimizeTextPending = textPending;
    renderTextOptimizer();

    expect(screen.getByTestId("run-optimize")).toBeDisabled();
    expect(screen.getByText("optimize.running")).toBeInTheDocument();
  });
});