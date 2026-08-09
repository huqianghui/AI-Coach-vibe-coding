import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { ObjectionList } from "./objection-list";

describe("ObjectionList", () => {
  it("renders existing items", () => {
    render(
      <ObjectionList
        items={["First objection", "Second objection"]}
        onChange={vi.fn()}
        label="Objections"
        addLabel="Add Objection"
      />,
    );

    const inputs = screen.getAllByRole("textbox");
    expect(inputs).toHaveLength(2);
    expect(inputs[0]).toHaveValue("First objection");
    expect(inputs[1]).toHaveValue("Second objection");
  });

  it("calls onChange with a new empty item when add button is clicked", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();

    render(
      <ObjectionList
        items={["Existing"]}
        onChange={onChange}
        label="Objections"
        addLabel="Add Objection"
      />,
    );

    await user.click(screen.getByText("Add Objection"));
    expect(onChange).toHaveBeenCalledWith(["Existing", ""]);
  });

  it("focuses the newly added controlled input", async () => {
    const user = userEvent.setup();
    function ControlledList() {
      const [items, setItems] = useState(["Existing"]);
      return (
        <ObjectionList
          items={items}
          onChange={setItems}
          label="Objections"
          addLabel="Add Objection"
        />
      );
    }
    render(<ControlledList />);

    await user.click(screen.getByText("Add Objection"));

    const inputs = screen.getAllByRole("textbox");
    expect(inputs).toHaveLength(2);
    expect(inputs[1]).toHaveFocus();
  });

  it("calls onChange without the removed item when remove button is clicked", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();

    render(
      <ObjectionList
        items={["First", "Second", "Third"]}
        onChange={onChange}
        label="Objections"
        addLabel="Add Objection"
      />,
    );

    const removeButtons = screen.getAllByRole("button", {
      name: "Remove item",
    });
    await user.click(removeButtons[1]!);
    expect(onChange).toHaveBeenCalledWith(["First", "Third"]);
  });

  it("calls onChange with updated value when input text changes", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();

    render(
      <ObjectionList
        items={["Original"]}
        onChange={onChange}
        label="Objections"
        addLabel="Add Objection"
      />,
    );

    const input = screen.getByRole("textbox");
    // Type a single character at the end
    await user.type(input, "X");
    // The last call should contain the appended character
    const lastCall =
      onChange.mock.calls[onChange.mock.calls.length - 1] as string[][];
    expect(lastCall[0]![0]).toBe("OriginalX");
  });

  it("renders the label text", () => {
    render(
      <ObjectionList
        items={[]}
        onChange={vi.fn()}
        label="My Custom Label"
        addLabel="Add Item"
      />,
    );

    expect(screen.getByText("My Custom Label")).toBeInTheDocument();
  });
});
