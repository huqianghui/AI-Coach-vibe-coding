import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import type { UseFormReturn } from "react-hook-form";
import { toast } from "sonner";
import {
  ChevronRight,
  ChevronDown,
  Database,
  FileText,
  Plus,
  Trash2,
  Wrench,
  X,
  ExternalLink,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
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
import { Label } from "@/components/ui/label";
import { InstructionsSection } from "@/components/admin/instructions-section";
import { ConnectKbDialog } from "@/components/admin/connect-kb-dialog";
import {
  useHcpKnowledgeConfigs,
  useRemoveKnowledgeConfig,
} from "@/hooks/use-knowledge-base";
import {
  useVoiceLiveInstances,
  useAssignVoiceLiveInstance,
  useUnassignVoiceLiveInstance,
} from "@/hooks/use-voice-live-instances";
import type { HcpFormValues } from "@/pages/admin/hcp-profile-editor";
import type { HcpProfile } from "@/types/hcp";

interface AgentConfigLeftPanelProps {
  form: UseFormReturn<HcpFormValues>;
  profile?: HcpProfile;
  isNew: boolean;
  onAutoInstructionsChange?: (instructions: string) => void;
}

export function AgentConfigLeftPanel({
  form,
  profile,
  isNew,
  onAutoInstructionsChange,
}: AgentConfigLeftPanelProps) {
  const { t } = useTranslation(["admin", "common"]);
  const navigate = useNavigate();

  const { data } = useVoiceLiveInstances();
  const instances = data?.items ?? [];
  const assignMutation = useAssignVoiceLiveInstance();
  const unassignMutation = useUnassignVoiceLiveInstance();

  const currentId = form.watch("voice_live_instance_id");
  const selectedInstance = instances.find((i) => i.id === currentId);

  const [knowledgeToolsExpanded, setKnowledgeToolsExpanded] = useState(false);
  const [showRemoveDialog, setShowRemoveDialog] = useState(false);
  const [connectKbDialogOpen, setConnectKbDialogOpen] = useState(false);

  const { data: kbConfigs } = useHcpKnowledgeConfigs(profile?.id);
  const removeKbMutation = useRemoveKnowledgeConfig();

  // --- VL Instance assign/unassign logic (migrated from voice-avatar-tab.tsx) ---
  const handleInstanceChange = (value: string) => {
    if (profile?.id) {
      assignMutation.mutate(
        { instanceId: value, hcpProfileId: profile.id },
        {
          onSuccess: () => {
            form.setValue("voice_live_instance_id", value, {
              shouldDirty: true,
            });
            toast.success(t("admin:voiceLive.instanceAssigned"));
          },
          onError: () => {
            toast.error(t("admin:voiceLive.assignError"));
          },
        },
      );
    } else {
      form.setValue("voice_live_instance_id", value, { shouldDirty: true });
    }
  };

  const handleConfirmRemove = () => {
    if (!profile?.id) return;
    unassignMutation.mutate(profile.id, {
      onSuccess: () => {
        form.setValue("voice_live_instance_id", null, { shouldDirty: true });
        toast.success(t("admin:voiceLive.removeInstanceSuccess"));
        setShowRemoveDialog(false);
      },
      onError: () => {
        toast.error(t("admin:voiceLive.assignError"));
        setShowRemoveDialog(false);
      },
    });
  };

  return (
    <div className="space-y-4">
      {/* 1. VL Instance Summary (D-11) */}
      <Card>
        <CardContent className="pt-4 pb-3 space-y-3">
          <Label className="text-xs font-semibold">
            {t("admin:hcp.vlInstanceLabel")}
          </Label>

          {currentId && selectedInstance ? (
            <div className="space-y-2">
              <p className="text-sm font-semibold truncate">
                {selectedInstance.name}
              </p>
              <div className="flex flex-wrap gap-1.5">
                <Badge variant="secondary" className="text-[10px]">
                  {selectedInstance.voice_live_model}
                </Badge>
                <Badge variant="secondary" className="text-[10px]">
                  {selectedInstance.voice_name}
                </Badge>
                <Badge variant="secondary" className="text-[10px]">
                  {selectedInstance.avatar_character} · {selectedInstance.avatar_style}
                </Badge>
              </div>
            </div>
          ) : (
            <div className="space-y-1">
              <div className="flex items-center gap-1.5">
                <p className="text-xs font-semibold text-muted-foreground">
                  {t("admin:hcp.vlInstanceEmptyTitle")}
                </p>
                <Badge variant="destructive" className="text-[10px]">
                  {t("admin:hcp.vlInstanceRequiredBadge")}
                </Badge>
              </div>
              <p className="text-[10px] text-muted-foreground">
                {t("admin:hcp.vlInstanceEmptyBody")}
              </p>
            </div>
          )}

          <div className="flex items-center gap-2">
            <Select
              value={currentId ?? undefined}
              onValueChange={handleInstanceChange}
              disabled={isNew}
            >
              <SelectTrigger className="h-9 text-sm flex-1 min-w-0 truncate">
                <SelectValue placeholder={t("admin:hcp.vlInstanceRequired")} />
              </SelectTrigger>
              <SelectContent>
                {instances.map((inst) => (
                  <SelectItem key={inst.id} value={inst.id}>
                    <span className="flex items-center gap-1.5 max-w-full">
                      <span className="truncate">{inst.name}</span>
                      <Badge variant="secondary" className="text-[10px] shrink-0">
                        {inst.voice_live_model}
                      </Badge>
                    </span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {currentId && (
              <Button
                variant="ghost"
                size="icon"
                className="size-9 shrink-0 text-muted-foreground hover:text-destructive"
                onClick={() => setShowRemoveDialog(true)}
                title={t("admin:voiceLive.removeInstance")}
                aria-label={t("admin:voiceLive.removeInstance")}
              >
                <X className="size-4" />
              </Button>
            )}
          </div>

          {form.formState.errors.voice_live_instance_id && (
            <p className="text-destructive text-sm">
              {t("admin:hcp.vlInstanceValidationError")}
            </p>
          )}

          <Button
            variant="link"
            size="sm"
            className="h-auto p-0 text-xs"
            onClick={() => navigate("/admin/voice-live")}
          >
            <ExternalLink className="size-3 mr-1" />
            {t("admin:voiceLive.goToVlManagement")}
          </Button>

          {isNew && (
            <p className="text-[10px] text-muted-foreground">
              {t("admin:hcp.playgroundDisabledNew")}
            </p>
          )}
        </CardContent>
      </Card>

      {/* 2. Instructions Section */}
      <InstructionsSection
        form={form}
        profileId={profile?.id}
        isNew={isNew}
        onAutoInstructionsChange={onAutoInstructionsChange}
      />

      {/* 3. Knowledge & Tools (collapsible skeleton) */}
      <Card>
        <CardHeader
          className="cursor-pointer select-none pb-2"
          onClick={() => setKnowledgeToolsExpanded((prev) => !prev)}
        >
          <div className="flex items-center gap-2">
            {knowledgeToolsExpanded ? (
              <ChevronDown className="size-4 text-muted-foreground" />
            ) : (
              <ChevronRight className="size-4 text-muted-foreground" />
            )}
            <CardTitle className="text-sm font-semibold">
              {t("admin:hcp.knowledgeAndTools")}
            </CardTitle>
          </div>
        </CardHeader>
        {knowledgeToolsExpanded && (
          <CardContent className="space-y-3 pt-0">
            {/* Knowledge Bases */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-muted-foreground">
                  <FileText className="inline size-3.5 mr-1" />
                  {t("admin:hcp.knowledgeTitle")}
                </span>
                {profile?.id && (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 px-2 text-xs"
                    onClick={() => setConnectKbDialogOpen(true)}
                  >
                    <Plus className="size-3 mr-1" />
                    {t("admin:hcp.addKnowledgeBase")}
                  </Button>
                )}
              </div>
              {kbConfigs && kbConfigs.length > 0 ? (
                <div className="space-y-1.5">
                  {kbConfigs.map((cfg) => (
                    <div
                      key={cfg.id}
                      className="flex items-center justify-between rounded border px-2 py-1.5"
                    >
                      <div className="flex items-center gap-2 min-w-0">
                        <Database className="size-3.5 shrink-0 text-muted-foreground" />
                        <span className="text-xs truncate">{cfg.index_name}</span>
                      </div>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="size-6 shrink-0 text-muted-foreground hover:text-destructive"
                        onClick={() => removeKbMutation.mutate(cfg.id)}
                        disabled={removeKbMutation.isPending}
                      >
                        <Trash2 className="size-3" />
                      </Button>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-[10px] text-muted-foreground">
                  {profile?.id
                    ? t("admin:hcp.noKnowledgeBases")
                    : t("admin:hcp.playgroundDisabledNew")}
                </p>
              )}
            </div>
            {/* Tools placeholder */}
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Wrench className="size-4" />
              <span>{t("admin:hcp.toolsPlaceholder")}</span>
            </div>
          </CardContent>
        )}
      </Card>

      {/* Connect Knowledge Base Dialog */}
      {profile?.id && (
        <ConnectKbDialog
          hcpId={profile.id}
          open={connectKbDialogOpen}
          onOpenChange={setConnectKbDialogOpen}
        />
      )}

      {/* Remove Confirm Dialog (migrated from voice-avatar-tab.tsx) */}
      <Dialog open={showRemoveDialog} onOpenChange={setShowRemoveDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("admin:voiceLive.removeInstance")}</DialogTitle>
            <DialogDescription>
              {t("admin:voiceLive.removeInstanceConfirm", {
                name: selectedInstance?.name ?? "",
              })}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setShowRemoveDialog(false)}
            >
              {t("common:cancel")}
            </Button>
            <Button
              variant="destructive"
              onClick={handleConfirmRemove}
              disabled={unassignMutation.isPending}
            >
              {unassignMutation.isPending
                ? t("common:saving")
                : t("admin:voiceLive.removeInstance")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
