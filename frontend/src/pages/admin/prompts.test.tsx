import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { AxiosError } from "axios";
import { toast } from "sonner";
import PromptsPage from "./prompts";
import type { PromptSummary } from "@/types/prompt";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      (opts?.defaultValue as string) ?? key,
    i18n: { changeLanguage: vi.fn(), language: "en" },
  }),
}));

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return { ...actual, useNavigate: () => mockNavigate };
});

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const { mockCreateAsync } = vi.hoisted(() => ({ mockCreateAsync: vi.fn() }));
let mockPromptsReturn: { data: PromptSummary[] | undefined };
vi.mock("@/hooks/use-prompts", () => ({
  usePrompts: () => mockPromptsReturn,
  useCreatePrompt: () => ({ mutateAsync: mockCreateAsync, isPending: false }),
}));

const makeSummary = (overrides: Partial<PromptSummary> = {}): PromptSummary => ({
  key: "hcp.system",
  name: "HCP System Prompt",
  category: "hcp",
  is_system: true,
  active_version_no: 1,
  updated_at: "2026-06-01T00:00:00Z",
  last_optimized_at: null,
  ...overrides,
});

function renderPage() {
  return render(
    <MemoryRouter>
      <PromptsPage />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockPromptsReturn = { data: [makeSummary()] };
});

describe("PromptsPage", () => {
  it("renders a row per prompt", () => {
    mockPromptsReturn = {
      data: [makeSummary(), makeSummary({ key: "scoring.base", name: "Scoring" })],
    };
    renderPage();
    expect(screen.getByTestId("prompt-row-hcp.system")).toBeInTheDocument();
    expect(screen.getByTestId("prompt-row-scoring.base")).toBeInTheDocument();
    expect(screen.getByText("HCP System Prompt")).toBeInTheDocument();
  });

  it("shows an empty message when there are no prompts", () => {
    mockPromptsReturn = { data: [] };
    renderPage();
    expect(screen.getByText("list.empty")).toBeInTheDocument();
  });

  it("navigates to the editor when a row is clicked", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(screen.getByTestId("prompt-row-hcp.system"));
    expect(mockNavigate).toHaveBeenCalledWith("/admin/prompts/hcp.system");
  });

  it("shows the active version number", () => {
    mockPromptsReturn = { data: [makeSummary({ active_version_no: 3 })] };
    renderPage();
    expect(screen.getByText("v3")).toBeInTheDocument();
  });

  it("creates a new prompt and navigates to its editor", async () => {
    const user = userEvent.setup();
    mockCreateAsync.mockResolvedValue({ key: "custom.hello" });
    renderPage();

    await user.click(screen.getByTestId("prompt-create-open"));
    await user.type(screen.getByTestId("create-key"), "custom.hello");
    await user.type(screen.getByTestId("create-name"), "Hello");
    await user.type(screen.getByTestId("create-content"), "Hi there");
    await user.type(screen.getByTestId("create-variables"), "name, product");
    await user.click(screen.getByTestId("create-submit"));

    expect(mockCreateAsync).toHaveBeenCalledWith(
      expect.objectContaining({
        key: "custom.hello",
        name: "Hello",
        content: "Hi there",
        variables: ["name", "product"],
        is_system: false,
      }),
    );
    expect(vi.mocked(toast.success)).toHaveBeenCalled();
    expect(mockNavigate).toHaveBeenCalledWith("/admin/prompts/custom.hello");
  });

  it("renders category and system-prompt selects in the create dialog", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(screen.getByTestId("prompt-create-open"));
    expect(screen.getByTestId("create-category")).toBeInTheDocument();
    expect(screen.getByTestId("create-is-system")).toBeInTheDocument();
  });

  it("keeps submit disabled until required fields are filled", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(screen.getByTestId("prompt-create-open"));
    expect(screen.getByTestId("create-submit")).toBeDisabled();
    await user.type(screen.getByTestId("create-key"), "custom.x");
    await user.type(screen.getByTestId("create-name"), "X");
    await user.type(screen.getByTestId("create-content"), "body");
    expect(screen.getByTestId("create-submit")).toBeEnabled();
  });

  it("shows a duplicate-key error toast on 409", async () => {
    const user = userEvent.setup();
    mockCreateAsync.mockRejectedValue(
      Object.assign(new AxiosError("conflict"), { response: { status: 409 } }),
    );
    renderPage();
    await user.click(screen.getByTestId("prompt-create-open"));
    await user.type(screen.getByTestId("create-key"), "hcp.system");
    await user.type(screen.getByTestId("create-name"), "Dup");
    await user.type(screen.getByTestId("create-content"), "body");
    await user.click(screen.getByTestId("create-submit"));
    expect(vi.mocked(toast.error)).toHaveBeenCalledWith("create.errorDuplicate");
    expect(mockNavigate).not.toHaveBeenCalled();
  });
});
