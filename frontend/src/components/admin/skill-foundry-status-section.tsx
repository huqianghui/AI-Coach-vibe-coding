import { useTranslation } from "react-i18next";
import {
  Sparkles,
  CheckCircle2,
  XCircle,
  Clock,
  AlertTriangle,
  RefreshCw,
  ExternalLink,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { getSkillFoundryPortalUrl } from "@/api/skills";
import type { Skill } from "@/types/skill";

interface SkillFoundryStatusSectionProps {
  skill: Skill | undefined;
  onRetrySync: () => void;
  retrySyncPending: boolean;
}

export function SkillFoundryStatusSection({
  skill,
  onRetrySync,
  retrySyncPending,
}: SkillFoundryStatusSectionProps) {
  const { t } = useTranslation("skill");

  const foundryStatus = skill?.foundry_sync_status ?? "none";
  const isArchived = skill?.status === "archived";
  const isPublished = skill?.status === "published";

  const STATUS_CONFIG = {
    synced: {
      icon: CheckCircle2,
      color: "text-green-600",
      bg: "bg-green-50 border-green-200",
      label: t("foundry.statusSynced"),
    },
    pending: {
      icon: Clock,
      color: "text-amber-600",
      bg: "bg-amber-50 border-amber-200",
      label: t("foundry.statusPending"),
    },
    failed: {
      icon: XCircle,
      color: "text-red-600",
      bg: "bg-red-50 border-red-200",
      label: t("foundry.statusFailed"),
    },
    none: {
      icon: AlertTriangle,
      color: "text-muted-foreground",
      bg: "bg-muted/50 border-muted",
      label: t("foundry.statusNone"),
    },
  } as const;

  const statusConfig = STATUS_CONFIG[foundryStatus];
  const StatusIcon = statusConfig.icon;

  return (
    <Card className={cn("border", statusConfig.bg)}>
      <CardHeader className="pb-3">
        <CardTitle className="text-base font-semibold flex items-center gap-2">
          <Sparkles className="size-5" />
          {t("foundry.title")}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Status */}
        <div className="flex items-center gap-2">
          <StatusIcon className={cn("size-5", statusConfig.color)} />
          <span className={cn("text-sm font-medium", statusConfig.color)}>
            {statusConfig.label}
          </span>
        </div>

        {/* Foundry skill name */}
        {skill?.foundry_skill_name && (
          <div className="space-y-1">
            <Label className="text-xs text-muted-foreground">
              {t("foundry.cloudNameLabel")}
            </Label>
            <Tooltip>
              <TooltipTrigger asChild>
                <p className="text-sm font-mono bg-background/80 rounded px-2 py-1 truncate border">
                  {skill.foundry_skill_name}
                </p>
              </TooltipTrigger>
              <TooltipContent>{skill.foundry_skill_name}</TooltipContent>
            </Tooltip>
          </div>
        )}

        {/* Foundry cloud version */}
        {skill?.foundry_cloud_version && (
          <div className="space-y-1">
            <Label className="text-xs text-muted-foreground">
              {t("foundry.cloudVersionLabel")}
            </Label>
            <p className="text-sm font-mono bg-background/80 rounded px-2 py-1 border">
              {skill.foundry_cloud_version}
            </p>
          </div>
        )}

        {/* Error message */}
        {foundryStatus === "failed" && skill?.foundry_sync_error && (
          <div className="space-y-1">
            <Label className="text-xs text-red-600">
              {t("foundry.errorLabel")}
            </Label>
            <p className="text-xs text-red-600 bg-red-50 rounded px-2 py-1 border border-red-200 max-h-24 overflow-y-auto">
              {skill.foundry_sync_error}
            </p>
          </div>
        )}

        {/* Actions */}
        <div className="flex flex-col gap-2 pt-2">
          {isArchived ? (
            <p className="text-xs text-muted-foreground">
              {t("foundry.archivedNote")}
            </p>
          ) : isPublished ? (
            <Button
              variant="outline"
              size="sm"
              onClick={onRetrySync}
              disabled={retrySyncPending || foundryStatus === "pending"}
              className="w-full"
            >
              <RefreshCw
                className={cn(
                  "size-4 mr-2",
                  retrySyncPending && "animate-spin",
                )}
              />
              {retrySyncPending
                ? t("foundry.retryingButton")
                : t("foundry.retryButton")}
            </Button>
          ) : (
            <p className="text-xs text-muted-foreground">
              {t("foundry.notPublishedNote")}
            </p>
          )}
          {skill?.foundry_skill_name && (
            <Button
              variant="ghost"
              size="sm"
              className="w-full text-xs"
              onClick={async () => {
                try {
                  const result = await getSkillFoundryPortalUrl(skill.id);
                  window.open(result.url, "_blank", "noopener,noreferrer");
                } catch {
                  window.open(
                    "https://ai.azure.com",
                    "_blank",
                    "noopener,noreferrer",
                  );
                }
              }}
            >
              <ExternalLink className="size-3.5 mr-1.5" />
              {t("foundry.portalButton")}
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
