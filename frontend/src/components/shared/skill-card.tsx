import { useTranslation } from "react-i18next";
import {
  MoreHorizontal,
  Pencil,
  Archive,
  Download,
  Trash2,
  Cloud,
  RefreshCw,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { SkillStatusBadge } from "@/components/shared/skill-status-badge";
import { cn } from "@/lib/utils";
import type { SkillListItem } from "@/types/skill";

interface SkillCardProps {
  skill: SkillListItem;
  onEdit: (skill: SkillListItem) => void;
  onArchive: (skill: SkillListItem) => void;
  onDelete: (skill: SkillListItem) => void;
  onExport: (skill: SkillListItem) => void;
  onFoundrySync: (skill: SkillListItem) => void;
  foundrySyncPending?: boolean;
}

export function SkillCard({
  skill,
  onEdit,
  onArchive,
  onDelete,
  onExport,
  onFoundrySync,
  foundrySyncPending = false,
}: SkillCardProps) {
  const { t } = useTranslation("skill");

  const tags = skill.tags ? skill.tags.split(",").map((s) => s.trim()).filter(Boolean) : [];
  const visibleTags = tags.slice(0, 3);
  const extraTagCount = tags.length - 3;

  return (
    <div
      className={cn(
        "flex min-h-[180px] flex-col rounded-lg border bg-card p-6",
        "transition-shadow duration-150 hover:shadow-md",
      )}
    >
      {/* Top row: status badge + quality score */}
      <div className="flex items-start justify-between">
        <SkillStatusBadge status={skill.status} />
        {skill.quality_score != null && (
          <span className="text-sm font-medium text-muted-foreground">
            {skill.quality_score}
          </span>
        )}
      </div>

      {/* Name */}
      <h3 className="mt-3 line-clamp-1 text-base font-semibold text-foreground">
        {skill.name}
      </h3>

      {/* Product */}
      {skill.product && (
        <p className="mt-1 text-sm text-muted-foreground">{skill.product}</p>
      )}

      {/* Tags */}
      {visibleTags.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {visibleTags.map((tag) => (
            <Badge key={tag} variant="outline" className="text-xs">
              {tag}
            </Badge>
          ))}
          {extraTagCount > 0 && (
            <Badge variant="outline" className="text-xs text-muted-foreground">
              +{extraTagCount}
            </Badge>
          )}
        </div>
      )}

      <div className="mt-3 flex items-center gap-1.5 text-xs text-muted-foreground">
        <Cloud
          className={cn(
            "size-3.5",
            skill.foundry_sync_status === "synced" && "text-green-600",
            skill.foundry_sync_status === "failed" && "text-red-600",
            skill.foundry_sync_status === "pending" && "text-amber-600",
          )}
        />
        <span>{t(`foundry.cardStatus.${skill.foundry_sync_status}`)}</span>
        {skill.foundry_cloud_version && (
          <span>· v{skill.foundry_cloud_version}</span>
        )}
      </div>

      {/* Spacer */}
      <div className="flex-1" />

      {/* Actions */}
      <div className="mt-4 flex items-center justify-end gap-2">
        <Button variant="ghost" size="sm" onClick={() => onEdit(skill)}>
          <Pencil className="mr-1 size-4" />
          {t("actions.edit")}
        </Button>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" className="size-8">
              <MoreHorizontal className="size-4" />
              <span className="sr-only">{t("actions.more")}</span>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            {skill.status === "published" && (
              <DropdownMenuItem
                disabled={foundrySyncPending || skill.foundry_sync_status === "pending"}
                onClick={() => onFoundrySync(skill)}
              >
                <RefreshCw className={cn("size-4", foundrySyncPending && "animate-spin")} />
                {t("actions.syncFoundry")}
              </DropdownMenuItem>
            )}
            <DropdownMenuItem onClick={() => onArchive(skill)}>
              <Archive className="size-4" />
              {t("actions.archive")}
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => onExport(skill)}>
              <Download className="size-4" />
              {t("actions.export")}
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              variant="destructive"
              onClick={() => onDelete(skill)}
            >
              <Trash2 className="size-4" />
              {t("actions.delete")}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div>
  );
}
