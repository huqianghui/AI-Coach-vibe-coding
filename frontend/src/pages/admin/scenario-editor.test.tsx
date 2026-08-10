import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import ScenarioEditorPage from "./scenario-editor";
import type { Scenario } from "@/types/scenario";

const { mockNavigate, mockToastError, mockToastSuccess } = vi.hoisted(() => ({
  mockNavigate: vi.fn(),
  mockToastError: vi.fn(),
  mockToastSuccess: vi.fn(),
}));

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => mockNavigate };
});

vi.mock("sonner", () => ({
  toast: { error: mockToastError, success: mockToastSuccess },
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => {
      if (key === "scenarios.editor.fields.hcpProfile") return "Assigned HCP";
      if (key === "scenarios.editor.tabs.linkedConfig") return "Linked Config";
      return key;
    },
    i18n: { changeLanguage: vi.fn(), language: "en" },
  }),
}));

const mockCreateMutate = vi.fn();
const mockUpdateMutate = vi.fn();
const mockSetAudienceMutate = vi.fn();

let mockScenarioData: Scenario | undefined;
let mockScenarioLoading = false;
let mockCreatePending = false;
let mockUpdatePending = false;
let mockPublishedSkills: Array<{
  id: string;
  name: string;
  current_version: number;
  quality_score: number | null;
}>;
let mockAudienceData: Array<{
  hcpProfileId: string;
  roleInConference: string;
  voiceId?: string;
  sortOrder: number;
}> | undefined;
let mockRubricDimensions: Array<{
  name: string;
  weight: number;
  criteria: string[];
}>;

vi.mock("@/hooks/use-scenarios", () => ({
  useScenario: () => ({ data: mockScenarioData, isLoading: mockScenarioLoading }),
  useCreateScenario: () => ({ mutate: mockCreateMutate, isPending: mockCreatePending }),
  useUpdateScenario: () => ({ mutate: mockUpdateMutate, isPending: mockUpdatePending }),
}));

vi.mock("@/hooks/use-conference-audience", () => ({
  useAudienceHcps: () => ({ data: mockAudienceData }),
  useSetAudienceHcps: () => ({ mutate: mockSetAudienceMutate, isPending: false }),
}));

vi.mock("@/components/admin/conference-audience-config", () => ({
  MIN_AUDIENCE: 2,
  MAX_AUDIENCE: 5,
  ConferenceAudienceConfig: ({
    onChange,
  }: {
    onChange: (value: Array<{
      hcpProfileId: string;
      roleInConference: string;
      sortOrder: number;
    }>) => void;
  }) => (
    <div data-testid="conference-audience-config">
      <button type="button" onClick={() => onChange([])}>audience-empty</button>
      <button
        type="button"
        onClick={() => onChange([
          { hcpProfileId: "hcp-1", roleInConference: "moderator", sortOrder: 0 },
          { hcpProfileId: "", roleInConference: "audience", sortOrder: 1 },
        ])}
      >
        audience-missing-hcp
      </button>
      <button
        type="button"
        onClick={() => onChange([
          { hcpProfileId: "hcp-1", roleInConference: "moderator", sortOrder: 0 },
          { hcpProfileId: "hcp-1", roleInConference: "audience", sortOrder: 1 },
        ])}
      >
        audience-duplicate
      </button>
      <button
        type="button"
        onClick={() => onChange([
          { hcpProfileId: "hcp-1", roleInConference: "audience", sortOrder: 0 },
          { hcpProfileId: "hcp-2", roleInConference: "audience", sortOrder: 1 },
        ])}
      >
        audience-no-moderator
      </button>
      <button
        type="button"
        onClick={() => onChange([
          { hcpProfileId: "hcp-1", roleInConference: "moderator", sortOrder: 0 },
          { hcpProfileId: "hcp-2", roleInConference: "audience", sortOrder: 1 },
        ])}
      >
        audience-valid
      </button>
    </div>
  ),
}));

vi.mock("@/components/admin/objection-list", () => ({
  ObjectionList: ({
    items,
    onChange,
  }: {
    items: string[];
    onChange: (items: string[]) => void;
  }) => (
    <div data-testid="key-message-list">
      <span>{items.join("|")}</span>
      <button type="button" onClick={() => onChange(["New message", ""])}>
        set-key-messages
      </button>
    </div>
  ),
}));

vi.mock("@/hooks/use-hcp-profiles", () => ({
  useHcpProfiles: () => ({
    data: {
      items: [
        {
          id: "hcp-1",
          name: "Dr. Wang",
          avatar_url: "",
          specialty: "Oncology",
        },
        {
          id: "hcp-2",
          name: "Dr. Li",
          avatar_url: "",
          specialty: "Hematology",
        },
      ],
    },
  }),
}));

vi.mock("@/hooks/use-skills", () => ({
  usePublishedSkills: () => ({
    data: { items: mockPublishedSkills },
  }),
}));

vi.mock("@/hooks/use-rubrics", () => ({
  useRubrics: () => ({
    data: [{ id: "rb-1", name: "Rubric A", dimensions: mockRubricDimensions }],
  }),
}));

function renderEditor() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/admin/scenarios/new"]}>
        <Routes>
          <Route path="/admin/scenarios/new" element={<ScenarioEditorPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function renderEditEditor() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/admin/scenarios/sc-1/edit"]}>
        <Routes>
          <Route path="/admin/scenarios/:id/edit" element={<ScenarioEditorPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const MOCK_ACTIVE_SCENARIO: Scenario = {
  id: "sc-1",
  name: "Active Scenario",
  description: "old description",
  tags: ["tag:a"],
  mode: "f2f",
  difficulty: "medium",
  status: "active",
  hcp_profile_id: "hcp-1",
  key_messages: ["msg-1"],
  conference_prompt_config: {
    speaker_order_policy: "Default policy",
    audience_prompt_template: "Default template",
    moderator_remarks: {
      invite: { zh: "invite zh", en: "invite en" },
      opening: { zh: "opening zh", en: "opening en" },
      handoff: { zh: "handoff zh", en: "handoff en" },
      closing: { zh: "closing zh", en: "closing en" },
    },
  },
  skill_id: "sk-1",
  skill_version_id: "v1",
  rubric_id: "rb-1",
  pass_threshold: 70,
  created_by: "u1",
  created_at: "2026-01-01",
  updated_at: "2026-01-01",
};

describe("ScenarioEditorPage - HCP field visibility", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    mockScenarioData = undefined;
    mockScenarioLoading = false;
    mockCreatePending = false;
    mockUpdatePending = false;
    mockPublishedSkills = [
      { id: "sk-1", name: "Skill A", current_version: 1, quality_score: 80 },
    ];
    mockAudienceData = undefined;
    mockRubricDimensions = [];
  });

  it("shows Assigned HCP for f2f mode", async () => {
    renderEditor();

    await userEvent.click(screen.getByRole("tab", { name: /linked config/i }));

    expect(screen.getByText("Assigned HCP")).toBeInTheDocument();
  });

  it("creates a complete F2F scenario, normalizes messages, and handles both callbacks", async () => {
    const user = userEvent.setup();
    renderEditor();

    await user.type(screen.getByLabelText("scenarios.editor.fields.name"), "New F2F");
    await user.click(screen.getByRole("button", { name: "set-key-messages" }));
    await user.click(screen.getByRole("tab", { name: /linked config/i }));

    const linkedComboboxes = screen.getAllByRole("combobox");
    await user.click(linkedComboboxes[0]!);
    await user.click(await screen.findByRole("option", { name: /Dr\. Wang/i }));
    await user.click(screen.getAllByRole("combobox").at(-1)!);
    await user.click(await screen.findByRole("option", { name: /Skill A/i }));

    await user.click(screen.getByRole("tab", { name: /scoringRules/i }));
    await user.click(screen.getByRole("combobox"));
    await user.click(await screen.findByRole("option", { name: /Rubric A/i }));
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(mockCreateMutate).toHaveBeenCalledTimes(1));
    const [payload, options] = mockCreateMutate.mock.calls[0] as [
      Record<string, unknown>,
      { onSuccess: (created: { id: string }) => void; onError: () => void },
    ];
    expect(payload).toMatchObject({
      name: "New F2F",
      mode: "f2f",
      hcp_profile_id: "hcp-1",
      skill_id: "sk-1",
      rubric_id: "rb-1",
      key_messages: ["New message"],
    });
    expect(payload).not.toHaveProperty("conference_prompt_config");

    options.onError();
    expect(mockToastError).toHaveBeenCalledWith("scenarios.saveFailed");
    options.onSuccess({ id: "created-1" });
    expect(mockSetAudienceMutate).not.toHaveBeenCalled();
    expect(mockToastSuccess).toHaveBeenCalledWith("admin:scenarios.saved");
    expect(mockNavigate).toHaveBeenCalledWith("/admin/scenarios");
  });

  it("creates a conference scenario with its first audience HCP and saves the audience", async () => {
    const user = userEvent.setup();
    renderEditor();

    await user.type(screen.getByLabelText("scenarios.editor.fields.name"), "New Conference");
    await user.click(screen.getByRole("radio", { name: /conference/i }));
    await user.click(screen.getByRole("tab", { name: /linked config/i }));
    await user.click(screen.getByRole("button", { name: "audience-valid" }));

    const skillCombobox = screen.getAllByRole("combobox").at(-1)!;
    await user.click(skillCombobox);
    await user.click(await screen.findByRole("option", { name: /Skill A/i }));
    await user.click(screen.getByRole("tab", { name: /scoringRules/i }));
    await user.click(screen.getByRole("combobox"));
    await user.click(await screen.findByRole("option", { name: /Rubric A/i }));
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(mockCreateMutate).toHaveBeenCalledTimes(1));
    const [payload, createOptions] = mockCreateMutate.mock.calls[0] as [
      Record<string, unknown>,
      { onSuccess: (created: { id: string }) => void },
    ];
    expect(payload).toMatchObject({
      name: "New Conference",
      mode: "conference",
      hcp_profile_id: "hcp-1",
      skill_id: "sk-1",
      rubric_id: "rb-1",
    });
    expect(payload).toHaveProperty("conference_prompt_config");

    createOptions.onSuccess({ id: "conference-new" });
    expect(mockSetAudienceMutate).toHaveBeenCalledWith(
      {
        scenarioId: "conference-new",
        hcps: [
          { hcpProfileId: "hcp-1", roleInConference: "moderator", sortOrder: 0 },
          { hcpProfileId: "hcp-2", roleInConference: "audience", sortOrder: 1 },
        ],
      },
      expect.objectContaining({ onSuccess: expect.any(Function), onError: expect.any(Function) }),
    );
  });

  it("hides Assigned HCP for conference mode", async () => {
    renderEditor();

    await userEvent.click(screen.getByRole("radio", { name: /conference/i }));
    await userEvent.click(screen.getByRole("tab", { name: /linked config/i }));

    expect(screen.queryByText("Assigned HCP")).not.toBeInTheDocument();
  });

  it("updates active scenario with only changed non-protected fields", async () => {
    mockScenarioData = MOCK_ACTIVE_SCENARIO;
    renderEditEditor();

    const nameInput = screen.getByDisplayValue("Active Scenario");
    await userEvent.clear(nameInput);
    await userEvent.type(nameInput, "Active Scenario Updated");

    const saveButton = screen.getByRole("button", { name: /save/i });
    await userEvent.click(saveButton);

    await waitFor(() => expect(mockUpdateMutate).toHaveBeenCalledTimes(1));

    const mutateArg = mockUpdateMutate.mock.calls[0]?.[0] as {
      id: string;
      data: Record<string, unknown>;
    };

    expect(mutateArg.id).toBe("sc-1");
    expect(mutateArg.data).toEqual({ name: "Active Scenario Updated" });
    expect(mutateArg.data).not.toHaveProperty("hcp_profile_id");
    expect(mutateArg.data).not.toHaveProperty("skill_id");
    expect(mutateArg.data).not.toHaveProperty("rubric_id");
    expect(mutateArg.data).not.toHaveProperty("key_messages");

    const updateOptions = mockUpdateMutate.mock.calls[0]?.[1] as { onSuccess: () => void };
    updateOptions.onSuccess();
    expect(mockSetAudienceMutate).not.toHaveBeenCalled();
    expect(mockToastSuccess).toHaveBeenCalledWith("admin:scenarios.saved");
    expect(mockNavigate).toHaveBeenCalledWith("/admin/scenarios");
  });

  it("submits every changed F2F linked field and strips blank key messages", async () => {
    const user = userEvent.setup();
    mockScenarioData = MOCK_ACTIVE_SCENARIO;
    mockPublishedSkills = [
      { id: "sk-1", name: "Skill A", current_version: 1, quality_score: 80 },
      { id: "sk-2", name: "Skill B", current_version: 2, quality_score: 90 },
    ];
    renderEditEditor();

    await user.click(screen.getByRole("button", { name: "set-key-messages" }));
    await user.click(screen.getByRole("tab", { name: /linked config/i }));

    const linkedComboboxes = screen.getAllByRole("combobox");
    await user.click(linkedComboboxes[0]!);
    await user.click(await screen.findByRole("option", { name: /Dr\. Li/i }));
    await user.click(screen.getAllByRole("combobox").at(-1)!);
    await user.click(await screen.findByRole("option", { name: /Skill B/i }));

    await user.click(screen.getByRole("tab", { name: /scoringRules/i }));
    await user.click(screen.getByRole("combobox"));
    await user.click(await screen.findByRole("option", { name: /Rubric A/i }));
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(mockUpdateMutate).toHaveBeenCalledTimes(1));
    expect(mockUpdateMutate.mock.calls[0]?.[0]).toEqual({
      id: "sc-1",
      data: {
        skill_id: "sk-2",
        hcp_profile_id: "hcp-2",
        key_messages: ["New message"],
      },
    });
  });

  it("submits changed mode, rubric, and cleared optional values", async () => {
    const user = userEvent.setup();
    mockScenarioData = {
      ...MOCK_ACTIVE_SCENARIO,
      description: "description to clear",
      tags: ["product:Tislelizumab"],
      rubric_id: "rb-old",
    };
    renderEditEditor();

    await user.clear(screen.getByDisplayValue("description to clear"));
    await user.click(screen.getByRole("button", { name: "Tislelizumab" }));
    await user.click(screen.getByRole("radio", { name: /easy/i }));
    await user.click(screen.getByRole("radio", { name: /conference/i }));
    await user.click(screen.getByRole("tab", { name: /linked config/i }));
    await user.click(screen.getByRole("button", { name: "audience-valid" }));
    await user.click(screen.getByRole("tab", { name: /scoringRules/i }));
    await user.click(screen.getByRole("combobox"));
    await user.click(await screen.findByRole("option", { name: /Rubric A/i }));
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(mockUpdateMutate).toHaveBeenCalledTimes(1));
    expect(mockUpdateMutate.mock.calls[0]?.[0]).toEqual({
      id: "sc-1",
      data: {
        description: "",
        tags: [],
        mode: "conference",
        difficulty: "easy",
        rubric_id: "rb-1",
      },
    });
  });

  it("keeps an optimizer result while an edit scenario has not loaded", () => {
    sessionStorage.setItem(
      "promptOptimizer:scenario:audiencePrompt",
      "Do not consume yet",
    );

    renderEditEditor();

    expect(sessionStorage.getItem("promptOptimizer:scenario:audiencePrompt")).toBe(
      "Do not consume yet",
    );
  });

  it("consumes an optimizer result immediately for a new conference scenario", async () => {
    sessionStorage.setItem(
      "promptOptimizer:scenario:audiencePrompt",
      "New optimized audience template",
    );

    renderEditor();
    await userEvent.click(screen.getByRole("radio", { name: /conference/i }));
    await userEvent.click(screen.getByRole("tab", { name: /linked config/i }));

    expect(screen.getByDisplayValue("New optimized audience template")).toBeInTheDocument();
    expect(sessionStorage.getItem("promptOptimizer:scenario:audiencePrompt")).toBeNull();
  });

  it("shows the required HCP validation when an f2f scenario has no assigned profile", async () => {
    mockScenarioData = { ...MOCK_ACTIVE_SCENARIO, hcp_profile_id: "" };
    renderEditEditor();

    await userEvent.click(screen.getByRole("button", { name: /save/i }));
    await userEvent.click(screen.getByRole("tab", { name: /linked config/i }));

    expect(await screen.findAllByText("Assigned HCP")).toHaveLength(2);
    expect(mockUpdateMutate).not.toHaveBeenCalled();
  });

  it.each([
    ["create", true, false],
    ["update", false, true],
  ])("shows the saving state for a pending %s", (_kind, createPending, updatePending) => {
    mockCreatePending = createPending;
    mockUpdatePending = updatePending;
    if (updatePending) mockScenarioData = MOCK_ACTIVE_SCENARIO;

    if (updatePending) renderEditEditor();
    else renderEditor();

    const saveButton = screen.getByRole("button", { name: /common:saving/i });
    expect(saveButton).toBeDisabled();
  });

  it("supports header and rubric-management navigation", async () => {
    renderEditor();

    const buttons = screen.getAllByRole("button");
    await userEvent.click(buttons[0]!);
    expect(mockNavigate).toHaveBeenCalledWith("/admin/scenarios");

    await userEvent.click(screen.getByRole("tab", { name: /scoringRules/i }));
    await userEvent.click(screen.getByRole("button", { name: /manageRubrics/i }));
    expect(mockNavigate).toHaveBeenCalledWith("/admin/scoring-rubrics");
  });

  it("adds, normalizes, deduplicates, and removes tags", async () => {
    renderEditor();

    const tagInput = screen.getByPlaceholderText("scenarios.editor.fields.tagsPlaceholder");
    const addButton = screen.getByRole("button", { name: /addTag/i });

    await userEvent.click(addButton);
    expect(screen.queryByText("custom:")).not.toBeInTheDocument();

    await userEvent.type(tagInput, "  focused  {Enter}");
    expect(screen.getByText("focused")).toBeInTheDocument();

    await userEvent.type(tagInput, "domain:special{Enter}");
    expect(screen.getByText("special")).toBeInTheDocument();

    await userEvent.type(tagInput, "focused{Enter}");
    expect(screen.getAllByText("focused")).toHaveLength(1);

    await userEvent.click(screen.getByRole("button", { name: "Tislelizumab" }));
    expect(screen.getAllByText("Tislelizumab")).toHaveLength(2);
    await userEvent.click(screen.getAllByRole("button", { name: "Tislelizumab" })[0]!);
    expect(screen.getAllByText("Tislelizumab")).toHaveLength(1);
  });

  it("resets a changed conference prompt policy to the defaults", async () => {
    mockScenarioData = { ...MOCK_ACTIVE_SCENARIO, mode: "conference" };
    renderEditEditor();

    await userEvent.click(screen.getByRole("tab", { name: /linked config/i }));
    const policyInput = screen.getByDisplayValue("Default policy");
    await userEvent.clear(policyInput);
    await userEvent.type(policyInput, "Temporary policy");
    await userEvent.click(screen.getByRole("button", { name: /useDefault/i }));

    expect(screen.queryByDisplayValue("Temporary policy")).not.toBeInTheDocument();
    expect(screen.getByDisplayValue(/Use the configured audience order/)).toBeInTheDocument();
  });

  it("warns when the selected skill is no longer published", async () => {
    mockScenarioData = MOCK_ACTIVE_SCENARIO;
    mockPublishedSkills = [];
    renderEditEditor();

    await userEvent.click(screen.getByRole("tab", { name: /linked config/i }));

    expect(screen.getByText("scenarios.editor.fields.noPublishedSkills")).toBeInTheDocument();
    expect(screen.getByText("scenarios.editor.fields.skillArchived")).toBeInTheDocument();
  });

  it("does not warn when the edit scenario still references a published skill", async () => {
    mockScenarioData = MOCK_ACTIVE_SCENARIO;
    renderEditEditor();

    await userEvent.click(screen.getByRole("tab", { name: /linked config/i }));

    expect(screen.queryByText("scenarios.editor.fields.skillArchived")).not.toBeInTheDocument();
  });

  it("omits the quality badge when a published skill has no quality score", async () => {
    mockScenarioData = MOCK_ACTIVE_SCENARIO;
    mockPublishedSkills = [
      { id: "sk-1", name: "Skill A", current_version: 1, quality_score: null },
    ];
    renderEditEditor();

    await userEvent.click(screen.getByRole("tab", { name: /linked config/i }));
    await userEvent.click(screen.getAllByRole("combobox").at(-1)!);

    expect(await screen.findAllByText("Skill A")).not.toHaveLength(0);
    expect(screen.queryByText(/^Q:/)).not.toBeInTheDocument();
  });

  it("renders rubric dimensions with criteria and without optional criteria", async () => {
    mockScenarioData = MOCK_ACTIVE_SCENARIO;
    mockRubricDimensions = [
      { name: "Knowledge", weight: 60, criteria: ["Accurate evidence", "Clear explanation"] },
      { name: "Rapport", weight: 40, criteria: [] },
    ];
    renderEditEditor();

    await userEvent.click(screen.getByRole("tab", { name: /scoringRules/i }));

    expect(screen.getByText("Knowledge")).toBeInTheDocument();
    expect(screen.getByText("Rapport")).toBeInTheDocument();
    expect(screen.getByText("Accurate evidence; Clear explanation")).toBeInTheDocument();
  });

  it("restores optimized conference audience prompt after returning from optimizer", async () => {
    sessionStorage.setItem(
      "promptOptimizer:scenario:audiencePrompt",
      "Optimized audience template",
    );
    mockScenarioData = { ...MOCK_ACTIVE_SCENARIO, mode: "conference" };

    renderEditEditor();

    await userEvent.click(screen.getByRole("tab", { name: /linked config/i }));

    await waitFor(() => {
      expect(screen.getByDisplayValue("Optimized audience template")).toBeInTheDocument();
    });
    expect(sessionStorage.getItem("promptOptimizer:scenario:audiencePrompt")).toBeNull();
  });

  it.each([
    ["audience-empty", "admin:scenarios.editor.audience.invalidCount"],
    ["audience-missing-hcp", "admin:scenarios.editor.audience.emptyHcp"],
    ["audience-duplicate", "admin:scenarios.editor.audience.duplicate"],
    ["audience-no-moderator", "admin:scenarios.editor.audience.moderatorRequired"],
  ])("rejects invalid conference audience state %s", async (audienceButton, errorKey) => {
    mockScenarioData = { ...MOCK_ACTIVE_SCENARIO, mode: "conference" };
    renderEditEditor();

    await userEvent.click(screen.getByRole("tab", { name: /linked config/i }));
    await userEvent.click(screen.getByRole("button", { name: audienceButton }));
    await userEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(mockToastError).toHaveBeenCalledWith(errorKey));
    expect(mockUpdateMutate).not.toHaveBeenCalled();
  });

  it("navigates to the prompt optimizer with the current template and return location", async () => {
    mockScenarioData = { ...MOCK_ACTIVE_SCENARIO, mode: "conference" };
    renderEditEditor();

    await userEvent.click(screen.getByRole("tab", { name: /linked config/i }));
    await userEvent.click(screen.getByTestId("optimize-audience-prompt"));

    expect(mockNavigate).toHaveBeenCalledWith("/admin/prompt-optimizer", {
      state: {
        source: "text",
        returnTo: "/admin/scenarios/sc-1/edit",
        resultStorageKey: "promptOptimizer:scenario:audiencePrompt",
        content: "Default template",
        title: "admin:scenarios.editor.conferencePrompt.hcpTemplateSection",
      },
    });
  });

  it("saves a valid conference audience and finishes after the audience request succeeds", async () => {
    mockScenarioData = { ...MOCK_ACTIVE_SCENARIO, mode: "conference" };
    renderEditEditor();

    await userEvent.click(screen.getByRole("tab", { name: /linked config/i }));
    await userEvent.click(screen.getByRole("button", { name: "audience-valid" }));
    await userEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() => expect(mockUpdateMutate).toHaveBeenCalledTimes(1));

    const updateOptions = mockUpdateMutate.mock.calls[0]?.[1] as { onSuccess: () => void };
    updateOptions.onSuccess();

    expect(mockSetAudienceMutate).toHaveBeenCalledWith(
      {
        scenarioId: "sc-1",
        hcps: [
          { hcpProfileId: "hcp-1", roleInConference: "moderator", sortOrder: 0 },
          { hcpProfileId: "hcp-2", roleInConference: "audience", sortOrder: 1 },
        ],
      },
      expect.objectContaining({ onSuccess: expect.any(Function), onError: expect.any(Function) }),
    );

    const audienceOptions = mockSetAudienceMutate.mock.calls[0]?.[1] as {
      onSuccess: () => void;
    };
    audienceOptions.onSuccess();
    expect(mockToastSuccess).toHaveBeenCalledWith("admin:scenarios.saved");
    expect(mockNavigate).toHaveBeenCalledWith("/admin/scenarios");
  });

  it("reports both scenario and conference audience save failures", async () => {
    mockScenarioData = { ...MOCK_ACTIVE_SCENARIO, mode: "conference" };
    renderEditEditor();

    await userEvent.click(screen.getByRole("tab", { name: /linked config/i }));
    await userEvent.click(screen.getByRole("button", { name: "audience-valid" }));
    await userEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() => expect(mockUpdateMutate).toHaveBeenCalledTimes(1));

    const updateOptions = mockUpdateMutate.mock.calls[0]?.[1] as {
      onSuccess: () => void;
      onError: () => void;
    };
    updateOptions.onError();
    expect(mockToastError).toHaveBeenCalledWith("scenarios.saveFailed");

    updateOptions.onSuccess();
    const audienceOptions = mockSetAudienceMutate.mock.calls[0]?.[1] as { onError: () => void };
    audienceOptions.onError();
    expect(mockToastError).toHaveBeenCalledWith(
      "admin:scenarios.editor.audience.saveFailed",
    );
  });

  it("submits only changed scalar, array, and conference prompt fields", async () => {
    mockScenarioData = { ...MOCK_ACTIVE_SCENARIO, mode: "conference" };
    mockAudienceData = [
      { hcpProfileId: "hcp-1", roleInConference: "moderator", sortOrder: 0 },
      { hcpProfileId: "hcp-2", roleInConference: "audience", sortOrder: 1 },
    ];
    renderEditEditor();

    const nameInput = screen.getByDisplayValue("Active Scenario");
    await userEvent.clear(nameInput);
    await userEvent.type(nameInput, "Changed name");
    const descriptionInput = screen.getByDisplayValue("old description");
    await userEvent.clear(descriptionInput);
    await userEvent.type(descriptionInput, "Changed description");
    await userEvent.click(screen.getByRole("radio", { name: /hard/i }));
    await userEvent.click(screen.getByRole("button", { name: "Tislelizumab" }));

    await userEvent.click(screen.getByRole("tab", { name: /linked config/i }));
    const policyInput = screen.getByDisplayValue("Default policy");
    await userEvent.clear(policyInput);
    await userEvent.type(policyInput, "Changed policy");

    await userEvent.click(screen.getByRole("tab", { name: /scoringRules/i }));
    const thresholdInput = screen.getByRole("spinbutton");
    fireEvent.change(thresholdInput, { target: { value: "85" } });
    await userEvent.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(mockUpdateMutate).toHaveBeenCalledTimes(1));
    expect(mockUpdateMutate.mock.calls[0]?.[0]).toEqual({
      id: "sc-1",
      data: {
        name: "Changed name",
        description: "Changed description",
        tags: ["tag:a", "product:Tislelizumab"],
        difficulty: "hard",
        pass_threshold: 85,
        conference_prompt_config: {
          ...MOCK_ACTIVE_SCENARIO.conference_prompt_config,
          speaker_order_policy: "Changed policy",
        },
      },
    });
  });

  it("shows archived state and disables all submission controls", async () => {
    mockScenarioData = { ...MOCK_ACTIVE_SCENARIO, status: "archived" };
    const { container } = renderEditEditor();

    expect(screen.getByText("scenarios.editor.archivedBanner")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /save/i })).toBeDisabled();
    expect(container.querySelector("fieldset")).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: /save/i }));
    expect(mockUpdateMutate).not.toHaveBeenCalled();
  });

  it("renders the edit loading state before scenario data is available", () => {
    mockScenarioLoading = true;
    const { container } = renderEditEditor();

    expect(container.querySelector(".animate-spin")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /save/i })).not.toBeInTheDocument();
  });
});
