import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import PromptEditorPage from "./prompt-editor";
import type { Prompt, PromptVersion } from "@/types/prompt";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      (opts?.defaultValue as string) ?? key,
    i18n: { changeLanguage: vi.fn(), language: "en" },
  }),
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
    useParams: () => ({ key: "hcp.system" }),
  };
});

const mockSaveMutate = vi.fn();
const mockActivateMutate = vi.fn();
const mockMetaMutate = vi.fn();

let mockPromptReturn: { data: Prompt | undefined; isError: boolean };
let mockVersionsReturn: { data: PromptVersion[] | undefined };

vi.mock("@/hooks/use-prompts", () => ({
  usePrompt: () => mockPromptReturn,
  usePromptVersions: () => mockVersionsReturn,
  useSaveVersion: () => ({ mutate: mockSaveMutate, isPending: false }),
  useActivateVersion: () => ({ mutate: mockActivateMutate, isPending: false }),
  useUpdatePromptMeta: () => ({ mutate: mockMetaMutate, isPending: false }),
}));

const makeVersion = (overrides: Partial<PromptVersion> = {}): PromptVersion => ({
  id: "v-2",
  template_id: "t-1",
  version_no: 2,
  content: "current content",
  source: "manual",
  parent_version_id: "v-1",
  note: "",
  created_by: "admin",
  is_active: true,
  created_at: "2026-06-01T00:00:00Z",
  ...overrides,
});

const makePrompt = (overrides: Partial<Prompt> = {}): Prompt => ({
  key: "hcp.system",
  name: "HCP System Prompt",
  category: "hcp",
  description: "",
  is_system: true,
  variables: ["hcp_name", "specialty"],
  active_version: makeVersion(),
  ...overrides,
});

function renderPage() {
  return render(
    <MemoryRouter>
      <PromptEditorPage />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockPromptReturn = { data: makePrompt(), isError: false };
  mockVersionsReturn = {
    data: [
      makeVersion(),
      makeVersion({ id: "v-1", version_no: 1, is_active: false, source: "seed" }),
    ],
  };
});

describe("PromptEditorPage", () => {
  it("renders placeholder chips from variables", () => {
    renderPage();
    expect(screen.getByText("{{hcp_name}}")).toBeInTheDocument();
    expect(screen.getByText("{{specialty}}")).toBeInTheDocument();
  });

  it("Save calls useSaveVersion with the edited content", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(screen.getByTestId("save-version"));
    expect(mockSaveMutate).toHaveBeenCalledWith(
      { content: "current content", note: "" },
      expect.any(Object),
    );
  });

  it("Save changes calls useUpdatePromptMeta with the edited metadata", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.clear(screen.getByTestId("meta-name"));
    await user.type(screen.getByTestId("meta-name"), "Renamed Prompt");
    await user.click(screen.getByTestId("save-meta"));
    expect(mockMetaMutate).toHaveBeenCalledWith(
      expect.objectContaining({
        name: "Renamed Prompt",
        variables: ["hcp_name", "specialty"],
        is_system: true,
      }),
      expect.any(Object),
    );
  });

  it("Rollback calls useActivateVersion with the version number", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(screen.getByTestId("rollback-1"));
    expect(mockActivateMutate).toHaveBeenCalledWith(1, expect.any(Object));
  });

  it("AI Optimize opens the dedicated optimizer page", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByTestId("optimize-open"));

    expect(mockNavigate).toHaveBeenCalledWith("/admin/prompts/hcp.system/optimize", {
      state: expect.objectContaining({
        source: "registry",
        returnTo: "/admin/prompts/hcp.system",
        originalContent: "current content",
        title: "HCP System Prompt",
      }),
    });
  });

  it("shows an error message when the prompt fails to load", () => {
    mockPromptReturn = { data: undefined, isError: true };
    renderPage();
    expect(screen.getByText("editor.loadError")).toBeInTheDocument();
  });

  it("views a historical version's content without changing the active editor", async () => {
    const user = userEvent.setup();
    mockVersionsReturn = {
      data: [
        makeVersion({ content: "current content" }),
        makeVersion({
          id: "v-1",
          version_no: 1,
          is_active: false,
          source: "seed",
          content: "ORIGINAL SEED CONTENT",
        }),
      ],
    };
    renderPage();

    await user.click(screen.getByTestId("version-view-1"));

    const view = screen.getByTestId("version-view-content");
    expect(view).toHaveTextContent("ORIGINAL SEED CONTENT");
    // The editable textarea still shows the active (v2) content, unchanged.
    expect(screen.getByTestId("prompt-content")).toHaveValue("current content");
  });
});
