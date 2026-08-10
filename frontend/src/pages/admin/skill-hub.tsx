import { useState, useEffect, useMemo, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Plus, BookOpen, Upload, FileArchive, Check, CloudUpload } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/shared/empty-state";
import { SkillCard } from "@/components/shared/skill-card";
import { cn } from "@/lib/utils";
import {
  useSkills,
  useDeleteSkill,
  useArchiveSkill,
  useExportSkillZip,
  useImportSkillZip,
  useCreateSkill,
  useCreateSkillFromMaterials,
  useRetryFoundrySync,
  useBatchFoundrySync,
} from "@/hooks/use-skills";
import { useMaterials } from "@/hooks/use-materials";
import type { SkillListItem } from "@/types/skill";

const ALL_VALUE = "__all__";

export default function SkillHubPage() {
  const { t } = useTranslation("skill");
  const { t: tc } = useTranslation("common");
  const navigate = useNavigate();

  // Filters
  const [searchInput, setSearchInput] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState(ALL_VALUE);
  const [productFilter, setProductFilter] = useState(ALL_VALUE);
  const [page, setPage] = useState(1);

  // Debounce search (300ms)
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchInput);
      setPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchInput]);

  // Reset page on filter change
  useEffect(() => {
    setPage(1);
  }, [statusFilter, productFilter]);

  // Query
  const queryParams = useMemo(
    () => ({
      page,
      page_size: 12,
      status: statusFilter === ALL_VALUE ? undefined : statusFilter,
      product: productFilter === ALL_VALUE ? undefined : productFilter,
      search: debouncedSearch || undefined,
    }),
    [page, statusFilter, productFilter, debouncedSearch],
  );

  const { data, isLoading, isError, refetch } = useSkills(queryParams);
  const skills = data?.items ?? [];
  const totalPages = data?.total_pages ?? 1;

  // Unique products for filter (from current result set)
  const productOptions = useMemo(() => {
    const products = new Set<string>();
    for (const skill of skills) {
      if (skill.product) {
        products.add(skill.product);
      }
    }
    return Array.from(products).sort();
  }, [skills]);

  // Mutations
  const deleteMutation = useDeleteSkill();
  const archiveMutation = useArchiveSkill();
  const exportMutation = useExportSkillZip();
  const importMutation = useImportSkillZip();
  const createMutation = useCreateSkill();
  const createFromMaterialsMutation = useCreateSkillFromMaterials();
  const foundrySyncMutation = useRetryFoundrySync();
  const batchFoundrySyncMutation = useBatchFoundrySync();
  const [syncingSkillId, setSyncingSkillId] = useState<string | null>(null);

  // Material picker
  const [materialPickerOpen, setMaterialPickerOpen] = useState(false);
  const [selectedMaterialIds, setSelectedMaterialIds] = useState<string[]>([]);
  const { data: materialsData } = useMaterials({ page_size: 100 });
  const availableMaterials = materialsData?.items ?? [];

  // Dialogs
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<SkillListItem | null>(null);
  const [archiveTarget, setArchiveTarget] = useState<SkillListItem | null>(
    null,
  );

  // Handlers
  const handleEdit = useCallback(
    (skill: SkillListItem) => {
      navigate(`/admin/skills/${skill.id}/edit`);
    },
    [navigate],
  );

  const handleArchive = useCallback((skill: SkillListItem) => {
    setArchiveTarget(skill);
  }, []);

  const handleDelete = useCallback((skill: SkillListItem) => {
    setDeleteTarget(skill);
  }, []);

  const handleExport = useCallback(
    (skill: SkillListItem) => {
      exportMutation.mutate(skill.id, {
        onSuccess: (blob) => {
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = `${skill.name}.zip`;
          document.body.appendChild(a);
          a.click();
          a.remove();
          setTimeout(() => URL.revokeObjectURL(url), 5000);
        },
        onError: () => toast.error(t("errors.loadFailed")),
      });
    },
    [exportMutation, t],
  );

  const handleFoundrySync = useCallback(
    (skill: SkillListItem) => {
      setSyncingSkillId(skill.id);
      foundrySyncMutation.mutate(skill.id, {
        onSuccess: (updated) => {
          if (updated.foundry_sync_status === "synced") {
            toast.success(t("foundry.syncSuccess"));
          } else {
            toast.error(t("foundry.retryError", { error: updated.foundry_sync_error }));
          }
        },
        onError: (error) =>
          toast.error(t("foundry.retryError", { error: error.message })),
        onSettled: () => setSyncingSkillId(null),
      });
    },
    [foundrySyncMutation, t],
  );

  const handleBatchFoundrySync = () => {
    batchFoundrySyncMutation.mutate(undefined, {
      onSuccess: (result) => {
        if (result.failed > 0) {
          toast.error(
            t("foundry.batchPartial", {
              synced: result.synced,
              failed: result.failed,
            }),
          );
        } else {
          toast.success(t("foundry.batchSuccess", { synced: result.synced }));
        }
      },
      onError: () => toast.error(t("foundry.batchError")),
    });
  };

  const confirmDelete = () => {
    if (!deleteTarget) return;
    deleteMutation.mutate(deleteTarget.id, {
      onSuccess: () => {
        toast.success(tc("delete"));
        setDeleteTarget(null);
      },
      onError: () => toast.error(t("errors.deleteFailed")),
    });
  };

  const confirmArchive = () => {
    if (!archiveTarget) return;
    archiveMutation.mutate(archiveTarget.id, {
      onSuccess: () => {
        toast.success(t("actions.archive"));
        setArchiveTarget(null);
      },
      onError: () => toast.error(t("errors.archiveFailed")),
    });
  };

  const handleCreateFromMaterials = () => {
    setCreateDialogOpen(false);
    if (availableMaterials.length > 0) {
      setSelectedMaterialIds([]);
      setMaterialPickerOpen(true);
    } else {
      // No materials available, fall back to creating empty skill
      createMutation.mutate(
        { name: t("editor.defaultSkillName") },
        {
          onSuccess: (skill) => {
            navigate(`/admin/skills/${skill.id}/edit`);
          },
          onError: () => toast.error(t("errors.saveFailed")),
        },
      );
    }
  };

  const handleConfirmMaterials = () => {
    if (selectedMaterialIds.length === 0) return;
    setMaterialPickerOpen(false);
    createFromMaterialsMutation.mutate(
      { materialIds: selectedMaterialIds },
      {
        onSuccess: (result) => {
          toast.success(t("conversion.started"));
          navigate(`/admin/skills/${result.id}/edit`);
        },
        onError: () => toast.error(t("errors.saveFailed")),
      },
    );
  };

  const toggleMaterial = (id: string) => {
    setSelectedMaterialIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  };

  const handleImportZip = () => {
    setCreateDialogOpen(false);
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".zip";
    input.onchange = () => {
      const file = input.files?.[0];
      if (!file) return;
      importMutation.mutate(file, {
        onSuccess: (skill) => {
          toast.success(t("conversion.completed"));
          navigate(`/admin/skills/${skill.id}/edit`);
        },
        onError: () => toast.error(t("errors.loadFailed")),
      });
    };
    input.click();
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">
            {t("hub.title")}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {t("hub.description")}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            onClick={handleBatchFoundrySync}
            disabled={batchFoundrySyncMutation.isPending}
          >
            <CloudUpload
              className={cn(
                "size-4",
                batchFoundrySyncMutation.isPending && "animate-pulse",
              )}
            />
            {batchFoundrySyncMutation.isPending
              ? t("foundry.syncingAll")
              : t("foundry.syncAll")}
          </Button>
          <Button onClick={() => setCreateDialogOpen(true)}>
            <Plus className="size-4" />
            {t("hub.createSkill")}
          </Button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-col gap-3 sm:flex-row">
        <Input
          placeholder={t("hub.search")}
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          className="flex-1"
        />
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-[160px]">
            <SelectValue placeholder={t("hub.filterStatus")} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL_VALUE}>{t("hub.allStatuses")}</SelectItem>
            <SelectItem value="draft">{t("status.draft")}</SelectItem>
            <SelectItem value="review">{t("status.review")}</SelectItem>
            <SelectItem value="published">{t("status.published")}</SelectItem>
            <SelectItem value="archived">{t("status.archived")}</SelectItem>
            <SelectItem value="failed">{t("status.failed")}</SelectItem>
          </SelectContent>
        </Select>
        <Select value={productFilter} onValueChange={setProductFilter}>
          <SelectTrigger className="w-[160px]">
            <SelectValue placeholder={t("hub.filterProduct")} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL_VALUE}>{t("hub.allProducts")}</SelectItem>
            {productOptions.map((product) => (
              <SelectItem key={product} value={product}>
                {product}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Content */}
      {isLoading ? (
        <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-[180px] rounded-lg" />
          ))}
        </div>
      ) : isError ? (
        <EmptyState
          title={t("hub.errorTitle")}
          body={t("errors.loadFailed")}
          action={
            <Button variant="outline" onClick={() => refetch()}>
              {t("hub.errorRetry")}
            </Button>
          }
        />
      ) : skills.length === 0 ? (
        <EmptyState
          title={t("hub.emptyTitle")}
          body={t("hub.emptyBody")}
          action={
            <Button onClick={() => setCreateDialogOpen(true)}>
              <BookOpen className="size-4" />
              {t("hub.createSkill")}
            </Button>
          }
        />
      ) : (
        <>
          <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
            {skills.map((skill) => (
              <SkillCard
                key={skill.id}
                skill={skill}
                onEdit={handleEdit}
                onArchive={handleArchive}
                onDelete={handleDelete}
                onExport={handleExport}
                onFoundrySync={handleFoundrySync}
                foundrySyncPending={syncingSkillId === skill.id}
              />
            ))}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1}
                onClick={() => setPage((p) => p - 1)}
              >
                {tc("previous")}
              </Button>
              <span className="text-sm text-muted-foreground">
                {page} / {totalPages}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => p + 1)}
              >
                {tc("next")}
              </Button>
            </div>
          )}
        </>
      )}

      {/* Create Skill Dialog */}
      <Dialog open={createDialogOpen} onOpenChange={setCreateDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("hub.createDialogTitle")}</DialogTitle>
            <DialogDescription>
              {t("hub.createDialogDescription")}
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-3">
            <Button
              variant="outline"
              className="justify-start gap-3 px-4 py-6"
              onClick={handleCreateFromMaterials}
            >
              <Upload className="size-5" />
              <div className="text-left">
                <div className="font-medium">
                  {t("hub.createFromMaterials")}
                </div>
              </div>
            </Button>
            <Button
              variant="outline"
              className="justify-start gap-3 px-4 py-6"
              onClick={handleImportZip}
            >
              <FileArchive className="size-5" />
              <div className="text-left">
                <div className="font-medium">
                  {t("hub.importZipPackage")}
                </div>
              </div>
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Material Picker Dialog */}
      <Dialog open={materialPickerOpen} onOpenChange={setMaterialPickerOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>
              {t("hub.selectMaterials")}
            </DialogTitle>
            <DialogDescription>
              {t("hub.selectMaterialsDesc")}
            </DialogDescription>
          </DialogHeader>
          <div className="max-h-64 space-y-2 overflow-y-auto">
            {availableMaterials.map((m) => (
              <button
                key={m.id}
                type="button"
                className={`flex w-full items-center gap-3 rounded-md border p-3 text-left transition-colors ${
                  selectedMaterialIds.includes(m.id)
                    ? "border-primary bg-primary/5"
                    : "border-border hover:bg-muted/50"
                }`}
                onClick={() => toggleMaterial(m.id)}
              >
                <div
                  className={`flex size-5 shrink-0 items-center justify-center rounded border ${
                    selectedMaterialIds.includes(m.id)
                      ? "border-primary bg-primary text-primary-foreground"
                      : "border-muted-foreground/30"
                  }`}
                >
                  {selectedMaterialIds.includes(m.id) && (
                    <Check className="size-3" />
                  )}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="truncate font-medium">{m.name}</div>
                  <div className="text-xs text-muted-foreground">
                    {m.product}
                  </div>
                </div>
              </button>
            ))}
          </div>
          <div className="flex justify-end gap-2">
            <Button
              variant="outline"
              onClick={() => setMaterialPickerOpen(false)}
            >
              {tc("cancel")}
            </Button>
            <Button
              disabled={selectedMaterialIds.length === 0}
              onClick={handleConfirmMaterials}
            >
              {t("hub.convertSelected", {
                count: selectedMaterialIds.length,
              })}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog
        open={deleteTarget !== null}
        onOpenChange={() => setDeleteTarget(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("confirm.deleteTitle")}</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            {t("confirm.deleteMessage", { name: deleteTarget?.name ?? "" })}
          </p>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setDeleteTarget(null)}>
              {tc("cancel")}
            </Button>
            <Button variant="destructive" onClick={confirmDelete}>
              {tc("delete")}
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Archive Confirmation Dialog */}
      <Dialog
        open={archiveTarget !== null}
        onOpenChange={() => setArchiveTarget(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("confirm.archiveTitle")}</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            {t("confirm.archiveMessage", {
              name: archiveTarget?.name ?? "",
            })}
          </p>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => setArchiveTarget(null)}>
              {tc("cancel")}
            </Button>
            <Button variant="destructive" onClick={confirmArchive}>
              {t("actions.archive")}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
