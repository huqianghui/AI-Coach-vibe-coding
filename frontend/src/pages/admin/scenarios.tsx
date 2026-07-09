import { useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Eye, Pencil, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
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
  DialogFooter,
} from "@/components/ui/dialog";
import { ScenarioTable } from "@/components/admin/scenario-table";
import { Input, Label } from "@/components/ui";
import {
  useScenarios,
  useDeleteScenario,
  useCloneScenario,
  useTransitionScenarioStatus,
} from "@/hooks/use-scenarios";
import {
  useCreateScenarioGroup,
  useDeleteScenarioGroup,
  useScenarioGroups,
  useTransitionScenarioGroupStatus,
  useUpdateScenarioGroup,
} from "@/hooks/use-scenario-groups";
import type { ScenarioGroup } from "@/types/scenario-group";

type GroupFormItem = { scenarioId: string; weight: number };

const ALL_STATUS = "__all__";

export default function ScenariosPage() {
  const { t } = useTranslation("admin");
  const { t: tc } = useTranslation("common");
  const navigate = useNavigate();
  const [filterStatus, setFilterStatus] = useState(ALL_STATUS);
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
  const [deleteGroupConfirmId, setDeleteGroupConfirmId] = useState<string | null>(null);
  const [groupDialogOpen, setGroupDialogOpen] = useState(false);
  const [editingGroup, setEditingGroup] = useState<ScenarioGroup | null>(null);
  const [viewingGroup, setViewingGroup] = useState<ScenarioGroup | null>(null);
  const [groupName, setGroupName] = useState("");
  const [groupDescription, setGroupDescription] = useState("");
  const [groupPassThreshold, setGroupPassThreshold] = useState(70);
  const [groupItems, setGroupItems] = useState<GroupFormItem[]>([{ scenarioId: "", weight: 100 }]);

  const queryStatus = filterStatus === ALL_STATUS ? undefined : filterStatus;
  const { data: scenariosData } = useScenarios({ status: queryStatus });
  const { data: groupsData } = useScenarioGroups({ status: queryStatus });
  const deleteMutation = useDeleteScenario();
  const cloneMutation = useCloneScenario();
  const transitionMutation = useTransitionScenarioStatus();
  const createGroupMutation = useCreateScenarioGroup();
  const updateGroupMutation = useUpdateScenarioGroup();
  const transitionGroupMutation = useTransitionScenarioGroupStatus();
  const deleteGroupMutation = useDeleteScenarioGroup();

  const scenarios = useMemo(
    () => scenariosData?.items ?? [],
    [scenariosData],
  );
  const scenarioOptions = useMemo(
    () => (scenariosData?.items ?? []).filter((scenario) => scenario.status === "active"),
    [scenariosData],
  );
  const groups = useMemo(() => groupsData?.items ?? [], [groupsData]);
  const groupWeightTotal = groupItems.reduce((sum, item) => sum + (Number(item.weight) || 0), 0);

  const resetGroupForm = () => {
    setEditingGroup(null);
    setGroupName("");
    setGroupDescription("");
    setGroupPassThreshold(70);
    setGroupItems([{ scenarioId: "", weight: 100 }]);
  };

  const openCreateGroupDialog = () => {
    resetGroupForm();
    setGroupDialogOpen(true);
  };

  const openEditGroupDialog = (group: ScenarioGroup) => {
    setEditingGroup(group);
    setGroupName(group.name);
    setGroupDescription(group.description ?? "");
    setGroupPassThreshold(group.passThreshold);
    setGroupItems(
      group.items
        .sort((a, b) => a.sortOrder - b.sortOrder)
        .map((item) => ({ scenarioId: item.scenarioId, weight: item.weight })),
    );
    setGroupDialogOpen(true);
  };

  const describeScenarioOption = (scenarioId: string) => {
    const scenario = scenariosData?.items.find((item) => item.id === scenarioId);
    if (!scenario) return "未选择场景";
    const modeLabel = scenario.mode === "conference" ? "会议" : "F2F";
    return `${modeLabel} · ${scenario.name}`;
  };

  const handleCreate = () => {
    navigate("/admin/scenarios/new");
  };

  const handleDelete = (id: string) => {
    setDeleteConfirmId(id);
  };

  const confirmDelete = () => {
    if (deleteConfirmId) {
      deleteMutation.mutate(deleteConfirmId, {
        onSuccess: () => {
          toast.success(t("scenarios.deleted"));
          setDeleteConfirmId(null);
        },
      });
    }
  };

  const confirmGroupDelete = () => {
    if (deleteGroupConfirmId) {
      deleteGroupMutation.mutate(deleteGroupConfirmId, {
        onSuccess: () => {
          toast.success("组合场景已删除");
          setDeleteGroupConfirmId(null);
        },
      });
    }
  };

  const handleClone = (id: string) => {
    cloneMutation.mutate(id, {
      onSuccess: () => toast.success(t("scenarios.cloned")),
    });
  };

  const handleTransition = (id: string, status: string) => {
    transitionMutation.mutate(
      { id, status },
      {
        onSuccess: () => {
          toast.success(t("scenarios.statusChanged"));
        },
        onError: () => {
          toast.error(t("scenarios.statusChangeFailed"));
        },
      },
    );
  };

  const handleCreateGroup = () => {
    const validItems = groupItems.filter((item) => item.scenarioId && item.weight > 0);
    if (!groupName.trim() || validItems.length === 0) {
      toast.error("请填写组合名称并至少选择一个场景");
      return;
    }
    const weightTotal = validItems.reduce((sum, item) => sum + item.weight, 0);
    if (weightTotal !== 100) {
      toast.error(`场景权重总和必须等于 100，当前为 ${weightTotal}`);
      return;
    }
    const payload = {
      name: groupName.trim(),
      description: groupDescription,
      passThreshold: groupPassThreshold,
      items: validItems.map((item, index) => ({
        scenarioId: item.scenarioId,
        weight: item.weight,
        sortOrder: index,
      })),
    };
    const mutationOptions = {
        onSuccess: () => {
          toast.success(editingGroup ? "组合场景已更新" : "组合场景已创建");
          setGroupDialogOpen(false);
          resetGroupForm();
        },
      };
    if (editingGroup) {
      updateGroupMutation.mutate({ id: editingGroup.id, data: payload }, mutationOptions);
    } else {
      createGroupMutation.mutate(payload, mutationOptions);
    }
  };

  const handleGroupTransition = (id: string, status: string) => {
    transitionGroupMutation.mutate(
      { id, status },
      { onSuccess: () => toast.success("组合场景状态已更新") },
    );
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-medium text-foreground">{t("scenarios.title")}</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {t("scenarios.description")}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Select value={filterStatus} onValueChange={setFilterStatus}>
            <SelectTrigger className="w-[140px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL_STATUS}>{tc("all")}</SelectItem>
              <SelectItem value="active">{tc("active")}</SelectItem>
              <SelectItem value="draft">{tc("draft")}</SelectItem>
              <SelectItem value="archived">{tc("archived")}</SelectItem>
            </SelectContent>
          </Select>
          <Button onClick={handleCreate}>
            <Plus className="size-4" />
            {t("scenarios.createButton")}
          </Button>
          <Button variant="outline" onClick={openCreateGroupDialog}>
            <Plus className="size-4" />
            创建组合场景
          </Button>
        </div>
      </div>

      <ScenarioTable
        scenarios={scenarios}
        onDelete={handleDelete}
        onClone={handleClone}
        onTransition={handleTransition}
      />

      <div className="rounded-lg border border-border bg-card p-6">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-foreground">合并场景</h2>
            <p className="text-sm text-muted-foreground">组合多个单场景，并设置每个场景的打分权重。</p>
          </div>
        </div>
        <div className="space-y-3">
          {groups.map((group) => (
            <div key={group.id} className="flex flex-col gap-3 rounded-lg border border-border p-4 md:flex-row md:items-center md:justify-between">
              <div>
                <div className="font-medium text-foreground">{group.name}</div>
                <div className="text-sm text-muted-foreground">
                  {group.items.length} 个场景 · 通过线 {group.passThreshold}
                </div>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {group.items
                    .sort((a, b) => a.sortOrder - b.sortOrder)
                    .slice(0, 4)
                    .map((item) => (
                      <span key={item.id} className="rounded-md bg-muted px-2 py-0.5 text-xs text-muted-foreground">
                        {item.scenario?.mode === "conference" ? "会议" : "F2F"} · {item.scenario?.name ?? item.scenarioId} · 权重 {item.weight}
                      </span>
                    ))}
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button size="sm" variant="outline" onClick={() => setViewingGroup(group)}>
                  <Eye className="size-4" />
                  查看
                </Button>
                <Button size="sm" variant="outline" onClick={() => openEditGroupDialog(group)}>
                  <Pencil className="size-4" />
                  编辑
                </Button>
                {group.status === "draft" && (
                  <Button size="sm" onClick={() => handleGroupTransition(group.id, "active")}>激活</Button>
                )}
                {group.status === "active" && (
                  <Button size="sm" variant="outline" onClick={() => handleGroupTransition(group.id, "archived")}>归档</Button>
                )}
                {group.status !== "active" && (
                  <Button size="sm" variant="destructive" onClick={() => setDeleteGroupConfirmId(group.id)}>删除</Button>
                )}
              </div>
            </div>
          ))}
          {groups.length === 0 && <p className="text-sm text-muted-foreground">暂无合并场景。</p>}
        </div>
      </div>

      <Dialog
        open={groupDialogOpen}
        onOpenChange={(open) => {
          setGroupDialogOpen(open);
          if (!open) resetGroupForm();
        }}
      >
        <DialogContent className="max-h-[90vh] w-[calc(100vw-2rem)] max-w-3xl overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{editingGroup ? "编辑组合场景" : "创建组合场景"}</DialogTitle>
            <DialogDescription>选择需要串联训练的单场景，并设置最终评分权重和通过线。</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="grid gap-4 md:grid-cols-[1fr_140px]">
              <div className="space-y-2">
                <Label>名称</Label>
                <Input value={groupName} onChange={(event) => setGroupName(event.target.value)} />
              </div>
              <div className="space-y-2">
                <Label>通过线</Label>
                <Input
                  type="number"
                  min={0}
                  max={100}
                  value={groupPassThreshold}
                  onChange={(event) => setGroupPassThreshold(Number(event.target.value))}
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label>描述</Label>
              <Input value={groupDescription} onChange={(event) => setGroupDescription(event.target.value)} />
            </div>
            <div className="space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <Label>场景与权重</Label>
                <span className={groupWeightTotal === 100 ? "text-xs text-success-700" : "text-xs text-danger-700"}>
                  当前权重总和 {groupWeightTotal}/100
                </span>
              </div>
              {groupItems.map((item, index) => (
                <div key={index} className="grid gap-2 rounded-lg border border-border p-3 md:grid-cols-[minmax(0,1fr)_112px_40px]">
                  <div className="min-w-0 space-y-1.5">
                    <Select
                      value={item.scenarioId}
                      onValueChange={(value) => {
                        setGroupItems((prev) => prev.map((row, i) => i === index ? { ...row, scenarioId: value } : row));
                      }}
                    >
                      <SelectTrigger className="w-full min-w-0">
                        <SelectValue placeholder="选择单场景">
                          <span className="block truncate">{describeScenarioOption(item.scenarioId)}</span>
                        </SelectValue>
                      </SelectTrigger>
                      <SelectContent className="max-w-[calc(100vw-3rem)]">
                        {scenarioOptions.map((scenario) => (
                          <SelectItem key={scenario.id} value={scenario.id}>
                            <span className="flex min-w-0 items-center gap-2">
                              <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground">
                                {scenario.mode === "conference" ? "会议" : "F2F"}
                              </span>
                              <span className="truncate">{scenario.name}</span>
                            </span>
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    {item.scenarioId && (
                      <p className="truncate text-xs text-muted-foreground">
                        {describeScenarioOption(item.scenarioId)}
                      </p>
                    )}
                  </div>
                  <Input
                    className="w-full"
                    type="number"
                    min={1}
                    aria-label="权重"
                    value={item.weight}
                    onChange={(event) => {
                      setGroupItems((prev) => prev.map((row, i) => i === index ? { ...row, weight: Number(event.target.value) } : row));
                    }}
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    aria-label="删除场景"
                    onClick={() => setGroupItems((prev) => prev.filter((_, i) => i !== index))}
                    disabled={groupItems.length <= 1}
                  >
                    <Trash2 className="size-4" />
                  </Button>
                </div>
              ))}
              {groupWeightTotal !== 100 && (
                <p className="text-sm text-danger-700">保存前请调整权重，总和必须等于 100。</p>
              )}
              <Button
                type="button"
                variant="outline"
                onClick={() => setGroupItems((prev) => [...prev, { scenarioId: "", weight: 100 }])}
              >
                <Plus className="size-4" />
                添加场景
              </Button>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setGroupDialogOpen(false)}>{tc("cancel")}</Button>
            <Button onClick={handleCreateGroup} disabled={createGroupMutation.isPending || updateGroupMutation.isPending}>
              {editingGroup ? "保存" : "创建"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={viewingGroup !== null} onOpenChange={() => setViewingGroup(null)}>
        <DialogContent className="max-h-[90vh] w-[calc(100vw-2rem)] max-w-2xl overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{viewingGroup?.name}</DialogTitle>
            <DialogDescription>
              {viewingGroup?.items.length ?? 0} 个场景 · 通过线 {viewingGroup?.passThreshold}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            {viewingGroup?.items
              .sort((a, b) => a.sortOrder - b.sortOrder)
              .map((item, index) => (
                <div key={item.id} className="rounded-lg border border-border p-3">
                  <div className="text-xs font-medium text-muted-foreground">场景 {index + 1}</div>
                  <div className="mt-1 font-medium text-foreground">{item.scenario?.name}</div>
                  <div className="mt-1 text-sm text-muted-foreground">
                    {item.scenario?.mode === "conference" ? "会议" : "F2F"} · 权重 {item.weight}
                  </div>
                </div>
              ))}
          </div>
          <DialogFooter>
            {viewingGroup && (
              <Button
                variant="outline"
                onClick={() => {
                  openEditGroupDialog(viewingGroup);
                  setViewingGroup(null);
                }}
              >
                编辑
              </Button>
            )}
            <Button onClick={() => setViewingGroup(null)}>关闭</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={deleteConfirmId !== null}
        onOpenChange={() => setDeleteConfirmId(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {t("scenarios.deleteTitle")}
            </DialogTitle>
            <DialogDescription>
              {t("scenarios.deleteConfirm")}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteConfirmId(null)}>
              {tc("cancel")}
            </Button>
            <Button variant="destructive" onClick={confirmDelete}>
              {tc("delete")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={deleteGroupConfirmId !== null}
        onOpenChange={() => setDeleteGroupConfirmId(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>删除组合场景</DialogTitle>
            <DialogDescription>确定要删除这个组合场景吗？</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteGroupConfirmId(null)}>
              {tc("cancel")}
            </Button>
            <Button variant="destructive" onClick={confirmGroupDelete}>
              {tc("delete")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
