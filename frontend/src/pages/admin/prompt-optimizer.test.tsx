import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import PromptOptimizerPage from "./prompt-optimizer";
import type { Prompt } from "@/types/prompt";

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
  usePrompt: () => ({ data: mockPrompt, isError: false }),
  useOptimizePrompt: () => ({ mutate: mockOptimizePromptMutate, isPending: false }),
  useAdoptRun: () => ({ mutate: mockAdoptRunMutate, isPending: false }),
  useOptimizeText: () => ({ mutate: mockOptimizeTextMutate, isPending: false }),
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

describe("PromptOptimizerPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
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
});