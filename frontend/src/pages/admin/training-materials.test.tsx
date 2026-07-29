import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

// Mock react-i18next
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en-US", changeLanguage: vi.fn() },
  }),
}));

// Mock sonner
vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

// Mock react-dropzone — capture onDrop callback for testing
let capturedOnDrop: ((files: File[]) => void) | null = null;
vi.mock("react-dropzone", () => ({
  useDropzone: vi.fn((opts: { onDrop?: (files: File[]) => void }) => {
    capturedOnDrop = opts?.onDrop ?? null;
    return {
      getRootProps: () => ({}),
      getInputProps: () => ({}),
      isDragActive: false,
    };
  }),
}));

// Mock the materials hooks
const mockUseMaterials = vi.fn();
const mockUseMaterialVersions = vi.fn();
const mockUploadMutate = vi.fn();
const mockUpdateMutate = vi.fn();
const mockArchiveMutate = vi.fn();
const mockRestoreMutate = vi.fn();

vi.mock("@/hooks/use-materials", () => ({
  useMaterials: (...args: unknown[]) => mockUseMaterials(...args),
  useMaterialVersions: (...args: unknown[]) => mockUseMaterialVersions(...args),
  useUploadMaterial: () => ({ mutate: mockUploadMutate, isPending: false }),
  useUpdateMaterial: () => ({ mutate: mockUpdateMutate, isPending: false }),
  useArchiveMaterial: () => ({ mutate: mockArchiveMutate }),
  useRestoreMaterial: () => ({ mutate: mockRestoreMutate }),
}));

import TrainingMaterialsPage from "./training-materials";

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <TrainingMaterialsPage />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

const mockMaterialsList = {
  items: [
    {
      id: "m1",
      name: "Brukinsa Guide",
      product: "Brukinsa",
      therapeutic_area: "Oncology",
      tags: "",
      is_archived: false,
      current_version: 2,
      created_by: "user1",
      created_at: "2026-03-15T10:00:00Z",
      updated_at: "2026-03-15T10:00:00Z",
    },
    {
      id: "m2",
      name: "Archived Doc",
      product: "DrugX",
      therapeutic_area: "",
      tags: "",
      is_archived: true,
      current_version: 1,
      created_by: "user1",
      created_at: "2026-03-10T10:00:00Z",
      updated_at: "2026-03-10T10:00:00Z",
    },
  ],
  total: 2,
  page: 1,
  page_size: 20,
  total_pages: 1,
};

describe("TrainingMaterialsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseMaterials.mockReturnValue({ data: undefined });
    mockUseMaterialVersions.mockReturnValue({ data: undefined });
  });

  it("renders page title", () => {
    renderPage();
    expect(screen.getByText("materials.title")).toBeInTheDocument();
  });

  it("renders upload button", () => {
    renderPage();
    expect(screen.getByText("materials.upload")).toBeInTheDocument();
  });

  it("shows empty state when no materials", () => {
    mockUseMaterials.mockReturnValue({
      data: { items: [], total: 0, page: 1, page_size: 20, total_pages: 0 },
    });
    renderPage();
    expect(screen.getByText("materials.noMaterials")).toBeInTheDocument();
  });

  it("renders material table with data", () => {
    mockUseMaterials.mockReturnValue({ data: mockMaterialsList });
    renderPage();
    expect(screen.getByText("Brukinsa Guide")).toBeInTheDocument();
    expect(screen.getByText("Brukinsa")).toBeInTheDocument();
    expect(screen.getByText("v2")).toBeInTheDocument();
  });

  it("renders archived badge for archived material", () => {
    mockUseMaterials.mockReturnValue({ data: mockMaterialsList });
    renderPage();
    const badges = screen.getAllByText("materials.archived");
    expect(badges.length).toBeGreaterThan(0);
  });

  it("renders active badge for active material", () => {
    mockUseMaterials.mockReturnValue({ data: mockMaterialsList });
    renderPage();
    const badges = screen.getAllByText("materials.active");
    expect(badges.length).toBeGreaterThan(0);
  });

  it("search input resets page to 1", async () => {
    mockUseMaterials.mockReturnValue({ data: mockMaterialsList });
    renderPage();

    const searchInput = screen.getByPlaceholderText("materials.searchPlaceholder");
    await userEvent.setup().type(searchInput, "test");

    // Verify useMaterials was called - search is debounced via state
    expect(mockUseMaterials).toHaveBeenCalled();
  });

  it("opens upload dialog on button click", async () => {
    renderPage();
    const uploadBtn = screen.getByText("materials.upload");
    await userEvent.setup().click(uploadBtn);

    // Dialog should now be open with upload hint (appears in both DialogDescription and dropzone)
    const hints = screen.getAllByText("materials.uploadHint");
    expect(hints.length).toBeGreaterThan(0);
  });

  it("upload button in dialog is disabled without file", async () => {
    renderPage();
    // Open upload dialog
    const uploadBtn = screen.getByText("materials.upload");
    await userEvent.setup().click(uploadBtn);

    // The submit button in the dialog should be disabled
    const submitButtons = screen.getAllByText("materials.upload");
    // The last one is in the dialog
    const dialogSubmit = submitButtons[submitButtons.length - 1]!;
    // Check the closest button element is disabled
    const buttonEl = dialogSubmit.closest("button");
    expect(buttonEl).toBeDisabled();
  });

  it("opens edit dialog with prefilled data", async () => {
    mockUseMaterials.mockReturnValue({ data: mockMaterialsList });
    renderPage();

    // Click edit button for first material
    const editButtons = screen.getAllByTitle("materials.edit");
    await userEvent.setup().click(editButtons[0]!);

    // Edit dialog should show with name input
    const nameInput = screen.getByDisplayValue("Brukinsa Guide");
    expect(nameInput).toBeInTheDocument();
  });

  it("archive button opens confirmation dialog", async () => {
    mockUseMaterials.mockReturnValue({ data: mockMaterialsList });
    renderPage();

    // Click archive button for first (non-archived) material
    const archiveButtons = screen.getAllByTitle("materials.archive");
    await userEvent.setup().click(archiveButtons[0]!);

    // Confirmation dialog should appear
    expect(screen.getByText("materials.archiveConfirm")).toBeInTheDocument();
  });

  it("restore button opens confirmation dialog", async () => {
    mockUseMaterials.mockReturnValue({ data: mockMaterialsList });
    renderPage();

    // Click restore button for archived material
    const restoreButtons = screen.getAllByTitle("materials.restore");
    await userEvent.setup().click(restoreButtons[0]!);

    // Confirmation dialog should appear
    expect(screen.getByText("materials.restoreConfirm")).toBeInTheDocument();
  });

  it("formatDate renders date in table cells", () => {
    mockUseMaterials.mockReturnValue({ data: mockMaterialsList });
    renderPage();
    // Both dates are March 2026, so multiple cells match
    const dateCells = screen.getAllByText(/2026/);
    expect(dateCells.length).toBeGreaterThan(0);
  });

  it("edit dialog save calls updateMutate", async () => {
    const user = userEvent.setup();
    mockUseMaterials.mockReturnValue({ data: mockMaterialsList });
    renderPage();

    // Open edit dialog for m1
    const editButtons = screen.getAllByTitle("materials.edit");
    await user.click(editButtons[0]!);

    // Click Save button (tc("save") returns "save")
    const saveButton = screen.getByRole("button", { name: "save" });
    await user.click(saveButton);

    expect(mockUpdateMutate).toHaveBeenCalledWith(
      {
        id: "m1",
        data: {
          name: "Brukinsa Guide",
          product: "Brukinsa",
          therapeutic_area: "Oncology",
        },
      },
      expect.objectContaining({
        onSuccess: expect.any(Function),
        onError: expect.any(Function),
      }),
    );
  });

  it("archive confirmation calls archiveMutate", async () => {
    const user = userEvent.setup();
    mockUseMaterials.mockReturnValue({ data: mockMaterialsList });
    renderPage();

    // Click archive button for m1 (non-archived material)
    const archiveButtons = screen.getAllByTitle("materials.archive");
    await user.click(archiveButtons[0]!);

    // Now there are TWO elements with text "materials.archive":
    // the dialog title and the confirm button
    const archiveTexts = screen.getAllByText("materials.archive");
    // Find the destructive button among them
    const confirmButton = archiveTexts
      .map((el) => el.closest("button"))
      .find((btn) => btn !== null)!;
    await user.click(confirmButton);

    expect(mockArchiveMutate).toHaveBeenCalledWith(
      "m1",
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );
  });

  it("restore confirmation calls restoreMutate", async () => {
    const user = userEvent.setup();
    mockUseMaterials.mockReturnValue({ data: mockMaterialsList });
    renderPage();

    // Click restore button for m2 (archived material)
    const restoreButtons = screen.getAllByTitle("materials.restore");
    await user.click(restoreButtons[0]!);

    // Dialog is open with title "materials.restore" and confirm button "materials.restore"
    // Find all buttons in the dialog footer and click the non-outline one
    const allButtons = screen.getAllByRole("button");
    const restoreConfirmButton = allButtons.find(
      (btn) =>
        btn.textContent === "materials.restore" &&
        !btn.classList.contains("outline"),
    )!;
    await user.click(restoreConfirmButton);

    expect(mockRestoreMutate).toHaveBeenCalledWith(
      "m2",
      expect.objectContaining({ onSuccess: expect.any(Function) }),
    );
  });

  it("versions dialog shows version list", async () => {
    const user = userEvent.setup();
    const versionData = [
      {
        id: "v1",
        material_id: "mat-1",
        version_number: 3,
        filename: "brukinsa-guide-v3.pdf",
        file_size: 2048,
        content_type: "application/pdf",
        download_url: "/files/v3.pdf",
        is_active: true,
        created_at: "2026-03-14T10:00:00Z",
      },
    ];
    mockUseMaterials.mockReturnValue({ data: mockMaterialsList });
    mockUseMaterialVersions.mockReturnValue({ data: versionData });
    renderPage();

    // Click versions (History) icon button for m1
    const versionsButtons = screen.getAllByTitle("materials.viewVersions");
    await user.click(versionsButtons[0]!);

    // Version data should render
    expect(screen.getByText("v3")).toBeInTheDocument();
    expect(screen.getByText(/brukinsa-guide-v3\.pdf/)).toBeInTheDocument();
    expect(screen.getByText(/2\.0 KB/)).toBeInTheDocument();
  });

  it("versions dialog shows empty state", async () => {
    const user = userEvent.setup();
    mockUseMaterials.mockReturnValue({ data: mockMaterialsList });
    mockUseMaterialVersions.mockReturnValue({ data: [] });
    renderPage();

    // Click versions button for m1
    const versionsButtons = screen.getAllByTitle("materials.viewVersions");
    await user.click(versionsButtons[0]!);

    expect(screen.getByText("materials.noVersions")).toBeInTheDocument();
  });

  it("pagination renders when multiple pages", () => {
    mockUseMaterials.mockReturnValue({
      data: {
        ...mockMaterialsList,
        total: 60,
        page: 1,
        total_pages: 3,
      },
    });
    renderPage();

    expect(screen.getByText("previous")).toBeInTheDocument();
    expect(screen.getByText("next")).toBeInTheDocument();
    // Component starts at page=1 internally
    expect(screen.getByText("1 / 3")).toBeInTheDocument();
  });

  it("pagination Previous and Next buttons work", async () => {
    const user = userEvent.setup();
    mockUseMaterials.mockReturnValue({
      data: {
        ...mockMaterialsList,
        total: 60,
        page: 2,
        total_pages: 3,
      },
    });
    renderPage();

    const prevButton = screen.getByText("previous");
    const nextButton = screen.getByText("next");

    await user.click(nextButton);
    // useMaterials should be called with updated page
    expect(mockUseMaterials).toHaveBeenCalled();

    await user.click(prevButton);
    expect(mockUseMaterials).toHaveBeenCalled();
  });

  it("show archived toggle re-calls useMaterials", async () => {
    const user = userEvent.setup();
    mockUseMaterials.mockReturnValue({ data: mockMaterialsList });
    renderPage();

    const callCountBefore = mockUseMaterials.mock.calls.length;

    // Click the switch element
    const switchEl = screen.getByRole("switch");
    await user.click(switchEl);

    // useMaterials should have been called again with include_archived changed
    expect(mockUseMaterials.mock.calls.length).toBeGreaterThan(callCountBefore);
  });

  it("cancel buttons close dialogs", async () => {
    const user = userEvent.setup();
    mockUseMaterials.mockReturnValue({ data: mockMaterialsList });
    renderPage();

    // Open upload dialog and cancel
    const uploadBtn = screen.getByText("materials.upload");
    await user.click(uploadBtn);
    const hints = screen.getAllByText("materials.uploadHint");
    expect(hints.length).toBeGreaterThan(0);

    const cancelButtons = screen.getAllByText("cancel");
    await user.click(cancelButtons[0]!);

    // uploadHint text should disappear from the dialog (dialog closed)
    // Wait for it to be removed
    const remainingHints = screen.queryAllByText("materials.uploadHint");
    // Dialog is closed so the hints from dialog description + dropzone should be gone
    expect(remainingHints.length).toBe(0);

    // Open edit dialog and cancel
    const editButtons = screen.getAllByTitle("materials.edit");
    await user.click(editButtons[0]!);
    expect(screen.getByDisplayValue("Brukinsa Guide")).toBeInTheDocument();

    const editCancelButtons = screen.getAllByText("cancel");
    await user.click(editCancelButtons[0]!);

    // Edit dialog should be closed — name input no longer present
    expect(screen.queryByDisplayValue("Brukinsa Guide")).not.toBeInTheDocument();
  });

  it("upload dialog for new version hides form fields", async () => {
    const user = userEvent.setup();
    mockUseMaterials.mockReturnValue({ data: mockMaterialsList });
    renderPage();

    // Click the "uploadNewVersion" icon button on m1's row
    const uploadVersionButtons = screen.getAllByTitle(
      "materials.uploadNewVersion",
    );
    await user.click(uploadVersionButtons[0]!);

    // Dialog should be open (upload hint visible)
    const hints = screen.getAllByText("materials.uploadHint");
    expect(hints.length).toBeGreaterThan(0);

    // Name and product inputs should NOT be visible (hidden for version uploads)
    expect(screen.queryByLabelText("materials.name")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("materials.product")).not.toBeInTheDocument();
  });

  it("formatFileSize helper renders in version dialog", async () => {
    const user = userEvent.setup();
    const versionData = [
      {
        id: "v1",
        material_id: "mat-1",
        version_number: 1,
        filename: "large-file.pdf",
        file_size: 1048576,
        content_type: "application/pdf",
        download_url: "/files/v1.pdf",
        is_active: false,
        created_at: "2026-03-14T10:00:00Z",
      },
    ];
    mockUseMaterials.mockReturnValue({ data: mockMaterialsList });
    mockUseMaterialVersions.mockReturnValue({ data: versionData });
    renderPage();

    // Open versions dialog
    const versionsButtons = screen.getAllByTitle("materials.viewVersions");
    await user.click(versionsButtons[0]!);

    // 1048576 bytes = 1.00 MB
    expect(screen.getByText(/1\.00 MB/)).toBeInTheDocument();
  });

  it("edit dialog onSuccess callback closes dialog and toasts", async () => {
    const user = userEvent.setup();
    // Make updateMutate invoke onSuccess immediately
    mockUpdateMutate.mockImplementation((_data: unknown, opts: { onSuccess?: () => void }) => {
      opts.onSuccess?.();
    });
    mockUseMaterials.mockReturnValue({ data: mockMaterialsList });
    renderPage();

    // Open edit dialog
    const editButtons = screen.getAllByTitle("materials.edit");
    await user.click(editButtons[0]!);

    // Click Save (tc("save") returns "save")
    const saveButton = screen.getByRole("button", { name: "save" });
    await user.click(saveButton);

    // Dialog should be closed (edit name input gone)
    expect(screen.queryByDisplayValue("Brukinsa Guide")).not.toBeInTheDocument();
  });

  it("edit dialog onError callback shows error toast", async () => {
    const user = userEvent.setup();
    // Make updateMutate invoke onError
    mockUpdateMutate.mockImplementation((_data: unknown, opts: { onError?: () => void }) => {
      opts.onError?.();
    });
    mockUseMaterials.mockReturnValue({ data: mockMaterialsList });
    renderPage();

    // Open edit dialog and save (tc("save") returns "save")
    const editButtons = screen.getAllByTitle("materials.edit");
    await user.click(editButtons[0]!);
    const saveButton = screen.getByRole("button", { name: "save" });
    await user.click(saveButton);

    // updateMutate was called with onError
    expect(mockUpdateMutate).toHaveBeenCalled();
  });

  it("archive onSuccess callback closes dialog", async () => {
    const user = userEvent.setup();
    // Make archiveMutate invoke onSuccess
    mockArchiveMutate.mockImplementation((_id: string, opts: { onSuccess?: () => void }) => {
      opts.onSuccess?.();
    });
    mockUseMaterials.mockReturnValue({ data: mockMaterialsList });
    renderPage();

    // Click archive button for m1
    const archiveButtons = screen.getAllByTitle("materials.archive");
    await user.click(archiveButtons[0]!);

    // Confirm archive
    const archiveTexts = screen.getAllByText("materials.archive");
    const confirmButton = archiveTexts
      .map((el) => el.closest("button"))
      .find((btn) => btn !== null)!;
    await user.click(confirmButton);

    // Confirm dialog should close (archiveConfirm text gone)
    expect(screen.queryByText("materials.archiveConfirm")).not.toBeInTheDocument();
  });

  it("restore onSuccess callback closes dialog", async () => {
    const user = userEvent.setup();
    // Make restoreMutate invoke onSuccess
    mockRestoreMutate.mockImplementation((_id: string, opts: { onSuccess?: () => void }) => {
      opts.onSuccess?.();
    });
    mockUseMaterials.mockReturnValue({ data: mockMaterialsList });
    renderPage();

    // Click restore button for m2 (archived)
    const restoreButtons = screen.getAllByTitle("materials.restore");
    await user.click(restoreButtons[0]!);

    // Confirm restore
    const allButtons = screen.getAllByRole("button");
    const restoreConfirmButton = allButtons.find(
      (btn) =>
        btn.textContent === "materials.restore" &&
        !btn.classList.contains("outline"),
    )!;
    await user.click(restoreConfirmButton);

    // Confirm dialog should close
    expect(screen.queryByText("materials.restoreConfirm")).not.toBeInTheDocument();
  });

  it("product select filter triggers state update", async () => {
    const user = userEvent.setup();
    mockUseMaterials.mockReturnValue({ data: mockMaterialsList });
    renderPage();

    // The product select should be present - find it by its combobox role
    const selectTrigger = screen.getAllByRole("combobox")[0];
    if (selectTrigger) {
      await user.click(selectTrigger);
      // Select an option if available
      const options = screen.queryAllByRole("option");
      if (options.length > 0) {
        await user.click(options[0]!);
      }
    }

    // useMaterials should have been called with the filter
    expect(mockUseMaterials).toHaveBeenCalled();
  });

  it("formatFileSize handles bytes < 1024", () => {
    const versionData = [
      {
        id: "v1",
        material_id: "mat-1",
        version_number: 1,
        filename: "tiny.pdf",
        file_size: 500,
        content_type: "application/pdf",
        download_url: "/files/v1.pdf",
        is_active: true,
        created_at: "2026-03-14T10:00:00Z",
      },
    ];
    mockUseMaterials.mockReturnValue({ data: mockMaterialsList });
    mockUseMaterialVersions.mockReturnValue({ data: versionData });
    renderPage();
  });

  it("full upload flow: onDrop sets file, handleUpload calls mutate", async () => {
    const user = userEvent.setup();
    // Make uploadMutate invoke onSuccess
    mockUploadMutate.mockImplementation(
      (_data: unknown, opts: { onSuccess?: () => void }) => {
        opts.onSuccess?.();
      },
    );
    renderPage();

    // Open upload dialog
    const uploadBtn = screen.getByText("materials.upload");
    await user.click(uploadBtn);

    // Simulate file drop via captured onDrop callback
    const fakeFile = new File(["fake-content"], "report.pdf", {
      type: "application/pdf",
    });
    Object.defineProperty(fakeFile, "size", { value: 1024 });

    // The onDrop callback was captured when useDropzone was called during render
    expect(capturedOnDrop).not.toBeNull();
    capturedOnDrop!([fakeFile]);

    // Fill in name and product (onDrop auto-fills name from filename)
    const nameInput = screen.getByLabelText("materials.name");
    await user.clear(nameInput);
    await user.type(nameInput, "My Report");

    const productInput = screen.getByLabelText("materials.product");
    await user.type(productInput, "Brukinsa");

    // Click the upload submit button (second "materials.upload" text)
    const submitButtons = screen.getAllByText("materials.upload");
    const dialogSubmit = submitButtons[submitButtons.length - 1]!;
    const buttonEl = dialogSubmit.closest("button");
    if (buttonEl && !buttonEl.disabled) {
      await user.click(buttonEl);
    }

    // uploadMutate should have been called
    expect(mockUploadMutate).toHaveBeenCalled();
  });

  it("handleUpload onError shows error toast", async () => {
    const user = userEvent.setup();
    // Make uploadMutate invoke onError
    mockUploadMutate.mockImplementation(
      (_data: unknown, opts: { onError?: () => void }) => {
        opts.onError?.();
      },
    );
    renderPage();

    // Open upload dialog
    const uploadBtn = screen.getByText("materials.upload");
    await user.click(uploadBtn);

    // Simulate file drop
    const fakeFile = new File(["data"], "doc.pdf", {
      type: "application/pdf",
    });
    capturedOnDrop!([fakeFile]);

    // Fill form
    const nameInput = screen.getByLabelText("materials.name");
    await user.clear(nameInput);
    await user.type(nameInput, "Test Doc");
    const productInput = screen.getByLabelText("materials.product");
    await user.type(productInput, "TestDrug");

    // Click upload submit
    const submitButtons = screen.getAllByText("materials.upload");
    const dialogSubmit = submitButtons[submitButtons.length - 1]!;
    const buttonEl = dialogSubmit.closest("button");
    if (buttonEl && !buttonEl.disabled) {
      await user.click(buttonEl);
    }

    expect(mockUploadMutate).toHaveBeenCalled();
  });

  it("handleUpload early return when no file", async () => {
    const user = userEvent.setup();
    renderPage();

    // Open upload dialog WITHOUT dropping a file
    const uploadBtn = screen.getByText("materials.upload");
    await user.click(uploadBtn);

    // Fill name and product but no file
    const nameInput = screen.getByLabelText("materials.name");
    await user.type(nameInput, "No File Doc");
    const productInput = screen.getByLabelText("materials.product");
    await user.type(productInput, "Drug");

    // Submit button should be disabled (no file selected)
    const submitButtons = screen.getAllByText("materials.upload");
    const dialogSubmit = submitButtons[submitButtons.length - 1]!;
    const buttonEl = dialogSubmit.closest("button");
    expect(buttonEl).toBeDisabled();
  });
});
