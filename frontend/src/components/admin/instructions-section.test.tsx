import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useForm, FormProvider } from "react-hook-form";
import type { HcpFormValues } from "@/pages/admin/hcp-profile-editor";

// ---- Mocks ----

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en-US" },
  }),
}));

vi.mock("sonner", () => ({
  toast: { error: vi.fn(), warning: vi.fn(), success: vi.fn(), info: vi.fn() },
}));

const mockPreviewInstructions = vi.fn();
vi.mock("@/api/hcp-profiles", () => ({
  previewInstructions: (...args: unknown[]) => mockPreviewInstructions(...args),
}));

// Import after mocks
import { InstructionsSection } from "./instructions-section";

function TestWrapper({
  profileId,
  isNew = false,
  overrideValue = "",
  onAutoInstructionsChange,
}: {
  profileId?: string;
  isNew?: boolean;
  overrideValue?: string;
  onAutoInstructionsChange?: (instructions: string) => void;
}) {
  const form = useForm<HcpFormValues>({
    defaultValues: {
      name: "Dr. Test",
      specialty: "Oncology",
      hospital: "",
      title: "",
      personality_type: "friendly",
      emotional_state: 50,
      communication_style: 50,
      expertise_areas: [],
      prescribing_habits: "",
      concerns: "",
      objections: [],
      probe_topics: [],
      difficulty: "medium",
      voice_live_instance_id: null,
      agent_instructions_override: overrideValue,
    },
  });

  return (
    <FormProvider {...form}>
      <InstructionsSection
        form={form}
        profileId={profileId}
        isNew={isNew}
        onAutoInstructionsChange={onAutoInstructionsChange}
      />
    </FormProvider>
  );
}

describe("InstructionsSection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockPreviewInstructions.mockReset();
  });

  it("renders card title", () => {
    render(<TestWrapper isNew={true} />);
    expect(screen.getByText("admin:hcp.autoInstructions")).toBeInTheDocument();
  });

  it("renders generate button", () => {
    render(<TestWrapper isNew={true} />);
    expect(screen.getByText("common:generate")).toBeInTheDocument();
  });

  it("shows hint text when no auto-instructions are loaded", () => {
    render(<TestWrapper isNew={true} />);
    expect(screen.getByText("admin:hcp.instructionsHint")).toBeInTheDocument();
  });

  it("renders override textarea", () => {
    render(<TestWrapper isNew={true} />);
    expect(
      screen.getByPlaceholderText("admin:hcp.overridePlaceholder"),
    ).toBeInTheDocument();
  });

  it("renders override label", () => {
    render(<TestWrapper isNew={true} />);
    expect(
      screen.getByText("admin:hcp.overrideInstructions"),
    ).toBeInTheDocument();
  });

  it("shows override warning when override text is provided", () => {
    render(<TestWrapper isNew={true} overrideValue="Custom override text" />);
    // The amber warning <p> includes the i18n key + extra text
    const warningParagraph = screen.getByText(
      /admin:hcp\.overrideInstructions.*override will be used/,
    );
    expect(warningParagraph).toBeInTheDocument();
    // The label should also be present
    expect(
      screen.getByText("admin:hcp.overrideInstructions"),
    ).toBeInTheDocument();
  });

  it("does not show override warning when override is empty", () => {
    render(<TestWrapper isNew={true} overrideValue="" />);
    // Only the label should exist, not the warning
    const elements = screen.getAllByText("admin:hcp.overrideInstructions");
    expect(elements.length).toBe(1); // just the label
  });

  it("calls previewInstructions on mount for existing profiles", async () => {
    mockPreviewInstructions.mockResolvedValue({
      instructions: "Generated instructions",
      is_override: false,
    });

    render(<TestWrapper profileId="hcp-1" isNew={false} />);

    // Wait for the async effect
    await vi.waitFor(() => {
      expect(mockPreviewInstructions).toHaveBeenCalledOnce();
    });
  });

  it("does not call previewInstructions on mount for new profiles", () => {
    render(<TestWrapper isNew={true} />);
    expect(mockPreviewInstructions).not.toHaveBeenCalled();
  });

  it("displays auto-generated instructions after loading", async () => {
    mockPreviewInstructions.mockResolvedValue({
      instructions: "You are Dr. Test, an oncologist.",
      is_override: false,
    });

    render(<TestWrapper profileId="hcp-1" isNew={false} />);

    await vi.waitFor(() => {
      expect(
        screen.getByText("You are Dr. Test, an oncologist."),
      ).toBeInTheDocument();
    });
  });

  it("calls onAutoInstructionsChange when instructions are loaded", async () => {
    const onAutoChange = vi.fn();
    mockPreviewInstructions.mockResolvedValue({
      instructions: "Auto instructions",
      is_override: false,
    });

    render(
      <TestWrapper
        profileId="hcp-1"
        isNew={false}
        onAutoInstructionsChange={onAutoChange}
      />,
    );

    await vi.waitFor(() => {
      expect(onAutoChange).toHaveBeenCalledWith("Auto instructions");
    });
  });

  it("calls previewInstructions when generate button is clicked", async () => {
    const user = userEvent.setup();
    mockPreviewInstructions.mockResolvedValue({
      instructions: "Regenerated instructions",
      is_override: false,
    });

    render(<TestWrapper isNew={true} />);

    await user.click(screen.getByText("common:generate"));

    await vi.waitFor(() => {
      expect(mockPreviewInstructions).toHaveBeenCalledOnce();
    });
  });

  it("shows generated instructions after clicking generate", async () => {
    const user = userEvent.setup();
    mockPreviewInstructions.mockResolvedValue({
      instructions: "Freshly generated",
      is_override: false,
    });

    render(<TestWrapper isNew={true} />);
    await user.click(screen.getByText("common:generate"));

    await vi.waitFor(() => {
      expect(screen.getByText("Freshly generated")).toBeInTheDocument();
    });
  });
});
