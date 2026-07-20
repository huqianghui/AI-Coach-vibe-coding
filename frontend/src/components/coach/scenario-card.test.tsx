import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ScenarioCard } from "./scenario-card";
import type { Scenario } from "@/types/scenario";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { changeLanguage: vi.fn(), language: "en" },
  }),
}));

const mockScenario: Scenario = {
  id: "sc-1",
  name: "Oncology Visit",
  description: "Practice F2F with oncologist",
  product: "DrugX",
  therapeutic_area: "Oncology",
  mode: "f2f",
  difficulty: "medium",
  status: "active",
  hcp_profile_id: "hcp-1",
  hcp_profile: {
    id: "hcp-1",
    name: "Dr. Jane Doe",
    specialty: "Oncology",
    avatar_url: "",
    personality_type: "analytical",
    voice_live_instance_id: null,
    voice_live_instance: null,
  },
  key_messages: ["Efficacy", "Safety"],
  rubric_id: "rubric-1",
  pass_threshold: 70,
  estimated_duration: 20,
  created_by: "admin",
  created_at: "2024-01-01",
  updated_at: "2024-01-01",
  skill_id: null,
  skill_version_id: null,
};

describe("ScenarioCard", () => {
  it("renders HCP name and description", () => {
    render(<ScenarioCard scenario={mockScenario} onStart={vi.fn()} />);
    // Component shows hcp_profile.name as the main heading
    expect(screen.getByText("Dr. Jane Doe")).toBeInTheDocument();
    expect(screen.getByText("Practice F2F with oncologist")).toBeInTheDocument();
  });

  it("renders HCP name and specialty", () => {
    render(<ScenarioCard scenario={mockScenario} onStart={vi.fn()} />);
    expect(screen.getByText("Dr. Jane Doe")).toBeInTheDocument();
    expect(screen.getByText("Oncology")).toBeInTheDocument();
  });

  it("renders difficulty badge", () => {
    render(<ScenarioCard scenario={mockScenario} onStart={vi.fn()} />);
    const badges = screen.getAllByText("medium");
    expect(badges.length).toBeGreaterThan(0);
  });

  it("calls onStart with scenario id and default mode when start button is clicked", async () => {
    const onStart = vi.fn();
    render(<ScenarioCard scenario={mockScenario} onStart={onStart} />);
    await userEvent.click(screen.getByText("scenarioSelection.startButton"));
    expect(onStart).toHaveBeenCalledWith("sc-1", "voice_realtime_model");
  });

  it("uses the provided default mode when it is available", async () => {
    const onStart = vi.fn();
    render(
      <ScenarioCard
        scenario={mockScenario}
        onStart={onStart}
        availableModes={["text", "voice_realtime_model", "digital_human_realtime_model"]}
        defaultMode="digital_human_realtime_model"
      />,
    );
    await userEvent.click(screen.getByText("scenarioSelection.startButton"));
    expect(onStart).toHaveBeenCalledWith("sc-1", "digital_human_realtime_model");
  });

  it("calls onStart with first available mode when default is unavailable", async () => {
    const onStart = vi.fn();
    render(
      <ScenarioCard
        scenario={mockScenario}
        onStart={onStart}
        availableModes={["text"]}
      />,
    );
    await userEvent.click(screen.getByText("scenarioSelection.startButton"));
    // voice_realtime_model is not available, so falls back to first available: text
    expect(onStart).toHaveBeenCalledWith("sc-1", "text");
  });

  it("lets the user start a digital human session when available", async () => {
    const onStart = vi.fn();
    render(
      <ScenarioCard
        scenario={mockScenario}
        onStart={onStart}
        availableModes={["text", "voice_realtime_model", "digital_human_realtime_model"]}
      />,
    );

    await userEvent.click(screen.getByText("scenarioSelection.modeDigitalHuman"));
    await userEvent.click(screen.getByText("scenarioSelection.startButton"));

    expect(onStart).toHaveBeenCalledWith("sc-1", "digital_human_realtime_model");
  });

  it("shows unavailable modes as disabled", () => {
    render(
      <ScenarioCard
        scenario={mockScenario}
        onStart={vi.fn()}
        availableModes={["text"]}
      />,
    );
    expect(screen.getByText("scenarioSelection.modeVoice").closest("button")).toBeDisabled();
    expect(
      screen.getByText("scenarioSelection.modeDigitalHuman").closest("button"),
    ).toBeDisabled();
  });

  it("renders product badge", () => {
    render(<ScenarioCard scenario={mockScenario} onStart={vi.fn()} />);
    expect(screen.getByText("DrugX")).toBeInTheDocument();
  });
});
