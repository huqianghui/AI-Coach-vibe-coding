import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SkillCard } from "./skill-card";
import type { SkillListItem } from "@/types/skill";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

function makeSkill(overrides: Partial<SkillListItem> = {}): SkillListItem {
  return {
    id: "skill-1",
    name: "Test Skill",
    description: "Description",
    product: "Product",
    status: "published",
    tags: "tag-one, tag-two, tag-three, tag-four",
    quality_score: 88,
    quality_verdict: "PASS",
    structure_check_passed: true,
    conversion_status: "completed",
    current_version: 1,
    created_by: "admin",
    created_at: "2026-08-10T00:00:00Z",
    updated_at: "2026-08-10T00:00:00Z",
    foundry_skill_name: "test-skill-12345678",
    foundry_sync_status: "synced",
    foundry_cloud_version: "2",
    foundry_sync_error: "",
    ...overrides,
  };
}

const handlers = {
  onEdit: vi.fn(),
  onArchive: vi.fn(),
  onDelete: vi.fn(),
  onExport: vi.fn(),
  onFoundrySync: vi.fn(),
};

describe("SkillCard Foundry synchronization", () => {
  beforeEach(() => vi.clearAllMocks());

  it("shows synced state and lets a published Skill be synchronized", async () => {
    const skill = makeSkill();
    render(<SkillCard skill={skill} {...handlers} />);

    expect(screen.getByText("foundry.cardStatus.synced")).toBeInTheDocument();
    expect(screen.getByText("· v2")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "actions.more" }));
    await userEvent.click(screen.getByText("actions.syncFoundry"));

    expect(handlers.onFoundrySync).toHaveBeenCalledWith(skill);
  });

  it("does not offer Foundry synchronization for a draft Skill", async () => {
    render(
      <SkillCard
        skill={makeSkill({
          status: "draft",
          foundry_sync_status: "none",
          foundry_cloud_version: "",
        })}
        {...handlers}
      />,
    );

    expect(screen.getByText("foundry.cardStatus.none")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "actions.more" }));
    expect(screen.queryByText("actions.syncFoundry")).not.toBeInTheDocument();
  });

  it("disables synchronization while a Skill sync is pending", async () => {
    render(
      <SkillCard
        skill={makeSkill({ foundry_sync_status: "pending" })}
        foundrySyncPending
        {...handlers}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: "actions.more" }));
    expect(screen.getByText("actions.syncFoundry").closest("div")).toHaveAttribute(
      "data-disabled",
    );
  });
});
