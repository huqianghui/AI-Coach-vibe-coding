import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HcpEditor } from "./hcp-editor";
import type { HcpProfile } from "@/types/hcp";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en-US" },
  }),
}));

const mockProfile: HcpProfile = {
  id: "hcp-1",
  name: "Dr. Smith",
  specialty: "Oncology",
  hospital: "Beijing Hospital",
  title: "Chief Oncologist",
  avatar_url: "",
  personality_type: "skeptical",
  emotional_state: 50,
  communication_style: 70,
  expertise_areas: ["Lung Cancer", "Immunotherapy"],
  prescribing_habits: "Conservative",
  concerns: "Side effects",
  objections: ["Cost is too high"],
  probe_topics: ["Clinical trials"],
  difficulty: "hard",
  is_active: true,
  created_by: "admin-1",
  created_at: "2024-01-01",
  updated_at: "2024-01-02",
  agent_id: "",
  agent_version: "",
  agent_sync_status: "none",
  agent_sync_error: "",
  agent_instructions_override: "",
  knowledge_config_count: 0,
  voice_live_instance_id: null,
};

describe("HcpEditor", () => {
  const defaultProps = {
    profile: null as HcpProfile | null,
    onSave: vi.fn(),
    onTestChat: vi.fn(),
    onDiscard: vi.fn(),
    isNew: true,
  };

  it("renders form with default values when creating new profile", () => {
    render(<HcpEditor {...defaultProps} />);

    expect(screen.getByText("hcp.identity")).toBeInTheDocument();
    expect(screen.getByText("hcp.save")).toBeInTheDocument();
    expect(screen.getByText("hcp.testChat")).toBeInTheDocument();
    expect(screen.getByText("hcp.discardChanges")).toBeInTheDocument();
  });

  it("populates form with profile data when editing", async () => {
    render(
      <HcpEditor {...defaultProps} profile={mockProfile} isNew={false} />,
    );

    await waitFor(() => {
      const nameInput = screen.getByRole("textbox", { name: /name/i });
      expect(nameInput).toHaveValue("Dr. Smith");
    });
  });

  it("shows avatar initials from the name field", () => {
    render(
      <HcpEditor {...defaultProps} profile={mockProfile} isNew={false} />,
    );

    // "Dr. Smith" => "DS"
    expect(screen.getByText("DS")).toBeInTheDocument();
  });

  it("calls onTestChat when test chat button is clicked", async () => {
    const user = userEvent.setup();
    const onTestChat = vi.fn();

    render(<HcpEditor {...defaultProps} onTestChat={onTestChat} />);

    await user.click(screen.getByText("hcp.testChat"));
    expect(onTestChat).toHaveBeenCalledTimes(1);
  });

  it("calls onDiscard when discard button is clicked", async () => {
    const user = userEvent.setup();
    const onDiscard = vi.fn();

    render(<HcpEditor {...defaultProps} onDiscard={onDiscard} />);

    await user.click(screen.getByText("hcp.discardChanges"));
    expect(onDiscard).toHaveBeenCalledTimes(1);
  });

  it("validates that name is required on submit", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn();

    render(<HcpEditor {...defaultProps} onSave={onSave} />);

    // Submit without filling name
    await user.click(screen.getByText("hcp.save"));

    // onSave should not be called when validation fails
    await waitFor(() => {
      expect(screen.getByText("Name is required")).toBeInTheDocument();
    });
    expect(onSave).not.toHaveBeenCalled();
  });
});
