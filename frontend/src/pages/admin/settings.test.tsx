import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import AdminSettingsPage from "./settings";

vi.mock("react-i18next", async () => {
  const { createTestTranslator } = await import("@/test/i18n-mock");
  return {
    useTranslation: (namespace?: string | string[]) => ({
      t: createTestTranslator(namespace),
      i18n: { changeLanguage: vi.fn(), language: "en-US" },
    }),
  };
});

describe("AdminSettingsPage", () => {
  it("renders the page title and description", () => {
    render(<AdminSettingsPage />);
    expect(screen.getByText("System Settings")).toBeInTheDocument();
    expect(
      screen.getByText("Configure platform-wide settings"),
    ).toBeInTheDocument();
  });

  it("renders Language & Region card", () => {
    render(<AdminSettingsPage />);
    expect(screen.getByText("Language & Region")).toBeInTheDocument();
    expect(screen.getByText("Default Language")).toBeInTheDocument();
  });

  it("renders Data Retention card", () => {
    render(<AdminSettingsPage />);
    expect(screen.getByText("Data Retention")).toBeInTheDocument();
    expect(
      screen.getByText("Voice Recording Retention (days)"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Voice recordings older than this will be automatically deleted",
      ),
    ).toBeInTheDocument();
  });

  it("renders Branding card", () => {
    render(<AdminSettingsPage />);
    expect(screen.getByText("Branding")).toBeInTheDocument();
    expect(screen.getByText("Organization Name")).toBeInTheDocument();
    expect(screen.getByText("Dark Mode")).toBeInTheDocument();
  });

  it("renders Save Settings button", () => {
    render(<AdminSettingsPage />);
    expect(screen.getByText("Save Settings")).toBeInTheDocument();
  });

  it("shows default retention days value of 90", () => {
    render(<AdminSettingsPage />);
    const retentionInput = screen.getByDisplayValue("90");
    expect(retentionInput).toBeInTheDocument();
  });

  it("shows default org name of BeiGene", () => {
    render(<AdminSettingsPage />);
    const orgInput = screen.getByDisplayValue("BeiGene");
    expect(orgInput).toBeInTheDocument();
  });

  it("allows editing retention days", async () => {
    render(<AdminSettingsPage />);
    const user = userEvent.setup();
    const retentionInput = screen.getByDisplayValue("90");
    await user.clear(retentionInput);
    await user.type(retentionInput, "30");
    expect(retentionInput).toHaveValue(30);
  });

  it("allows editing org name", async () => {
    render(<AdminSettingsPage />);
    const user = userEvent.setup();
    const orgInput = screen.getByDisplayValue("BeiGene");
    await user.clear(orgInput);
    await user.type(orgInput, "TestOrg");
    expect(orgInput).toHaveValue("TestOrg");
  });

  it("renders language select with default zh-CN", () => {
    render(<AdminSettingsPage />);
    // The select trigger shows "Chinese (Simplified)" because of the default value
    expect(
      screen.getByText("Chinese"),
    ).toBeInTheDocument();
  });
});
