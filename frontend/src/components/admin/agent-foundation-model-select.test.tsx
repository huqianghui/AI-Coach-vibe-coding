import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// Polyfill pointer capture methods missing in jsdom (required by Radix Select)
beforeAll(() => {
  if (!HTMLElement.prototype.hasPointerCapture) {
    HTMLElement.prototype.hasPointerCapture = vi.fn().mockReturnValue(false);
  }
  if (!HTMLElement.prototype.setPointerCapture) {
    HTMLElement.prototype.setPointerCapture = vi.fn();
  }
  if (!HTMLElement.prototype.releasePointerCapture) {
    HTMLElement.prototype.releasePointerCapture = vi.fn();
  }
  if (!HTMLElement.prototype.scrollIntoView) {
    HTMLElement.prototype.scrollIntoView = vi.fn();
  }
});

// ---- Mocks ----

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en-US" },
  }),
}));

const mockRefetch = vi.fn();
let mockHookReturn: {
  data: { models: { id: string; label: string }[]; stale: boolean; error: string | null } | undefined;
  isLoading: boolean;
  isError: boolean;
  refetch: typeof mockRefetch;
} = {
  data: { models: [], stale: false, error: null },
  isLoading: false,
  isError: false,
  refetch: mockRefetch,
};

vi.mock("@/hooks/use-agent-foundation-models", () => ({
  useAgentFoundationModels: () => mockHookReturn,
}));

// Import after mocks
import { AgentFoundationModelSelect } from "./agent-foundation-model-select";

describe("AgentFoundationModelSelect", () => {
  it("renders a disabled select with loading placeholder while loading", () => {
    mockHookReturn = {
      data: undefined,
      isLoading: true,
      isError: false,
      refetch: mockRefetch,
    };
    render(<AgentFoundationModelSelect value="" onValueChange={vi.fn()} />);

    expect(screen.getByRole("combobox")).toBeDisabled();
    expect(screen.getByText("hcp.foundationModelLoading")).toBeInTheDocument();
  });

  it("renders error copy + retry button with aria-label when isError, and refetches on click", async () => {
    mockHookReturn = {
      data: undefined,
      isLoading: false,
      isError: true,
      refetch: mockRefetch,
    };
    const user = userEvent.setup();
    render(<AgentFoundationModelSelect value="" onValueChange={vi.fn()} />);

    expect(screen.getByText("hcp.foundationModelError")).toBeInTheDocument();
    const retryButton = screen.getByRole("button", {
      name: "hcp.foundationModelError",
    });
    expect(retryButton).toHaveAttribute("aria-label", "hcp.foundationModelError");

    await user.click(retryButton);
    expect(mockRefetch).toHaveBeenCalled();
  });

  it("renders error copy when data.error is set (fetch succeeded but stale/error flagged)", () => {
    mockHookReturn = {
      data: { models: [], stale: true, error: "Foundry unreachable" },
      isLoading: false,
      isError: false,
      refetch: mockRefetch,
    };
    render(<AgentFoundationModelSelect value="" onValueChange={vi.fn()} />);

    expect(screen.getByText("hcp.foundationModelError")).toBeInTheDocument();
  });

  it("renders empty-state copy when models list is empty", () => {
    mockHookReturn = {
      data: { models: [], stale: false, error: null },
      isLoading: false,
      isError: false,
      refetch: mockRefetch,
    };
    render(<AgentFoundationModelSelect value="" onValueChange={vi.fn()} />);

    expect(screen.getByText("hcp.foundationModelEmpty")).toBeInTheDocument();
  });

  it("renders a populated select and calls onValueChange with the selected model id", async () => {
    mockHookReturn = {
      data: {
        models: [
          { id: "dep-1", label: "My Chat Model" },
          { id: "dep-2", label: "Another Model" },
        ],
        stale: false,
        error: null,
      },
      isLoading: false,
      isError: false,
      refetch: mockRefetch,
    };
    const onValueChange = vi.fn();
    const user = userEvent.setup();
    render(
      <AgentFoundationModelSelect value="" onValueChange={onValueChange} />,
    );

    const trigger = screen.getByRole("combobox");
    expect(trigger).not.toBeDisabled();
    await user.click(trigger);

    const option = await screen.findByText("Another Model");
    await user.click(option);

    expect(onValueChange).toHaveBeenCalledWith("dep-2");
  });
});
