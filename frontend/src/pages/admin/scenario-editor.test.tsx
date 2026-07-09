import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import ScenarioEditorPage from "./scenario-editor";
import type { Scenario } from "@/types/scenario";

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

let mockScenarioData: Scenario | undefined;

vi.mock("@/hooks/use-scenarios", () => ({
  useScenario: () => ({ data: mockScenarioData, isLoading: false }),
  useCreateScenario: () => ({ mutate: mockCreateMutate, isPending: false }),
  useUpdateScenario: () => ({ mutate: mockUpdateMutate, isPending: false }),
}));

vi.mock("@/hooks/use-conference-audience", () => ({
  useAudienceHcps: () => ({ data: undefined }),
  useSetAudienceHcps: () => ({ mutate: vi.fn(), isPending: false }),
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
      ],
    },
  }),
}));

vi.mock("@/hooks/use-skills", () => ({
  usePublishedSkills: () => ({
    data: {
      items: [{ id: "sk-1", name: "Skill A", current_version: 1, quality_score: 80 }],
    },
  }),
}));

vi.mock("@/hooks/use-rubrics", () => ({
  useRubrics: () => ({ data: [{ id: "rb-1", name: "Rubric A", dimensions: [] }] }),
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
  });

  it("shows Assigned HCP for f2f mode", async () => {
    renderEditor();

    await userEvent.click(screen.getByRole("tab", { name: /linked config/i }));

    expect(screen.getByText("Assigned HCP")).toBeInTheDocument();
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
});
