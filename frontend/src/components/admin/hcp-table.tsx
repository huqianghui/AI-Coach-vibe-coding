import { useState, useMemo } from "react";
import { useTranslation } from "react-i18next";
import {
  Edit,
  Trash2,
  ArrowUpDown,
  RefreshCw,
  BookOpen,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/shared/empty-state";
import { VOICE_LIVE_MODEL_OPTIONS } from "@/components/admin/voice-live-model-select";
import type { HcpProfile } from "@/types/hcp";

function getVoiceLabel(voiceName: string): string {
  if (!voiceName) return "";
  // Extract short name from Azure voice ID
  // e.g., "en-US-AvaNeural" -> "Ava", "zh-CN-XiaoxiaoMultilingualNeural" -> "Xiaoxiao ML"
  const parts = voiceName.split("-");
  if (parts.length < 3) return voiceName;
  const namePart = parts.slice(2).join("-");
  const cleaned = namePart
    .replace("Neural", "")
    .replace("Multilingual", "ML")
    .replace(":DragonHDLatest", " HD");
  return cleaned || voiceName;
}

function getModelLabel(modelId: string, t: (key: string) => string): string {
  const found = VOICE_LIVE_MODEL_OPTIONS.find((m) => m.value === modelId);
  return found ? t(`hcp.${found.i18nKey}`) : modelId;
}

interface HcpTableProps {
  profiles: HcpProfile[];
  isLoading: boolean;
  onEdit: (profile: HcpProfile) => void;
  onDelete: (id: string) => void;
  onRetrySync: (id: string) => void;
}

type SortKey = "name" | "specialty";
type SortDirection = "asc" | "desc";

const AGENT_STATUS_STYLES: Record<string, string> = {
  synced: "bg-green-100 text-green-700",
  pending: "bg-amber-100 text-amber-700",
  failed: "bg-red-100 text-red-700",
  none: "bg-muted text-muted-foreground",
};

function AgentStatusBadge({
  status,
  error,
}: {
  status: HcpProfile["agent_sync_status"];
  error?: string;
}) {
  const { t } = useTranslation("admin");

  const statusLabels: Record<string, string> = {
    synced: t("hcp.agentSynced"),
    pending: t("hcp.agentPending"),
    failed: t("hcp.agentFailed"),
    none: t("hcp.agentNone"),
  };

  const tooltipTexts: Record<string, string> = {
    synced: t("hcp.agentSyncedTooltip"),
    pending: t("hcp.agentPendingTooltip"),
    none: t("hcp.agentNoneTooltip"),
  };

  const tooltipText =
    status === "failed" && error ? error : tooltipTexts[status] ?? "";

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          className={cn(
            "inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium",
            AGENT_STATUS_STYLES[status],
            status === "pending" && "animate-pulse",
          )}
        >
          {statusLabels[status] ?? status}
        </span>
      </TooltipTrigger>
      {tooltipText && <TooltipContent>{tooltipText}</TooltipContent>}
    </Tooltip>
  );
}

function getCommStyleDesc(value: number): string {
  return value < 50 ? "Direct" : "Indirect";
}

export function HcpTable({
  profiles,
  isLoading,
  onEdit,
  onDelete,
  onRetrySync,
}: HcpTableProps) {
  const { t } = useTranslation("admin");
  const [sortKey, setSortKey] = useState<SortKey>("name");
  const [sortDir, setSortDir] = useState<SortDirection>("asc");
  const [page, setPage] = useState(0);
  const pageSize = 10;

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  };

  const sorted = useMemo(() => {
    const arr = [...profiles];
    arr.sort((a, b) => {
      const valA = a[sortKey];
      const valB = b[sortKey];
      const cmp = String(valA).localeCompare(String(valB));
      return sortDir === "asc" ? cmp : -cmp;
    });
    return arr;
  }, [profiles, sortKey, sortDir]);

  const paged = sorted.slice(page * pageSize, (page + 1) * pageSize);
  const totalPages = Math.max(1, Math.ceil(sorted.length / pageSize));

  const getInitials = (name: string) =>
    name
      ? name
          .split(" ")
          .map((n) => n[0])
          .join("")
          .toUpperCase()
          .slice(0, 2) || "?"
      : "?";

  return (
    <div>
      <div className="rounded-md border">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b bg-muted/50">
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                <button
                  type="button"
                  className="flex items-center gap-1"
                  onClick={() => toggleSort("name")}
                >
                  {t("hcp.name")}
                  <ArrowUpDown className="size-3.5" />
                </button>
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                <button
                  type="button"
                  className="flex items-center gap-1"
                  onClick={() => toggleSort("specialty")}
                >
                  {t("hcp.specialty")}
                  <ArrowUpDown className="size-3.5" />
                </button>
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                {t("hcp.personalityType")}
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                {t("hcp.communicationStyleCol")}
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                {t("hcp.agentStatus")}
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                {t("hcp.knowledgeBaseCol")}
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                {t("hcp.voiceAvatarCol")}
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider text-muted-foreground">
                {t("hcp.actions")}
              </th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <tr key={i} className="border-b border-border">
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-3">
                      <Skeleton className="size-6 rounded-full" />
                      <Skeleton className="h-4 w-[120px] rounded" />
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <Skeleton className="h-4 w-[80px] rounded" />
                  </td>
                  <td className="px-4 py-3">
                    <Skeleton className="h-4 w-[60px] rounded" />
                  </td>
                  <td className="px-4 py-3">
                    <Skeleton className="h-4 w-[40px] rounded" />
                  </td>
                  <td className="px-4 py-3">
                    <Skeleton className="h-5 w-[60px] rounded-full" />
                  </td>
                  <td className="px-4 py-3">
                    <Skeleton className="h-5 w-[50px] rounded" />
                  </td>
                  <td className="px-4 py-3">
                    <Skeleton className="h-5 w-[100px] rounded" />
                  </td>
                  <td className="px-4 py-3">
                    <Skeleton className="size-5 rounded" />
                  </td>
                </tr>
              ))
            ) : paged.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-4 py-8">
                  <EmptyState
                    title={t("hcp.emptyTitle")}
                    body={t("hcp.emptyBody")}
                  />
                </td>
              </tr>
            ) : (
              paged.map((profile) => (
                <tr
                  key={profile.id}
                  className="border-b hover:bg-muted/50 transition-colors cursor-pointer"
                  onDoubleClick={() => onEdit(profile)}
                >
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-3">
                      <Avatar className="size-6">
                        <AvatarImage
                          src={profile.avatar_url}
                          alt={profile.name}
                        />
                        <AvatarFallback className="bg-blue-100 text-blue-700 text-xs">
                          {getInitials(profile.name)}
                        </AvatarFallback>
                      </Avatar>
                      <span className="font-medium">{profile.name}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {profile.specialty}
                  </td>
                  <td className="px-4 py-3">
                    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-muted text-foreground capitalize">
                      {profile.personality_type}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {profile.communication_style}{" "}
                    <span className="text-xs">
                      ({getCommStyleDesc(profile.communication_style)})
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <AgentStatusBadge
                      status={profile.agent_sync_status}
                      error={profile.agent_sync_error}
                    />
                  </td>
                  <td className="px-4 py-3">
                    {profile.knowledge_config_count > 0 ? (
                      <Badge variant="outline" className="text-xs gap-1">
                        <BookOpen className="size-3" />
                        {profile.knowledge_config_count} KB
                      </Badge>
                    ) : (
                      <span className="text-xs text-muted-foreground">
                        {t("hcp.noKb")}
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {profile.voice_live_instance?.voice_name ? (
                      <span className="flex flex-wrap items-center gap-1">
                        <Badge variant="outline" className="text-xs">
                          {getVoiceLabel(profile.voice_live_instance.voice_name)}
                        </Badge>
                        <Badge variant="outline" className="text-xs">
                          {profile.voice_live_instance.avatar_character}-
                          {profile.voice_live_instance.avatar_style}
                        </Badge>
                        {profile.voice_live_instance.enabled &&
                          profile.voice_live_instance.voice_live_model && (
                            <Badge variant="outline" className="text-xs">
                              {getModelLabel(
                                profile.voice_live_instance.voice_live_model,
                                t,
                              )}
                            </Badge>
                          )}
                      </span>
                    ) : (
                      <span className="text-xs text-muted-foreground">
                        {t("hcp.notConfigured")}
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex items-center justify-end gap-1">
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="size-8"
                            onClick={(e) => {
                              e.stopPropagation();
                              onEdit(profile);
                            }}
                          >
                            <Edit className="size-4" />
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent>{t("materials.edit")}</TooltipContent>
                      </Tooltip>
                      {(profile.agent_sync_status === "failed" ||
                        profile.agent_sync_status === "none" ||
                        !profile.agent_id) && (
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="size-8 text-amber-600 hover:text-amber-700"
                              onClick={(e) => {
                                e.stopPropagation();
                                onRetrySync(profile.id);
                              }}
                            >
                              <RefreshCw className="size-4" />
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent>{t("hcp.retrySync")}</TooltipContent>
                        </Tooltip>
                      )}
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="size-8 text-destructive hover:text-destructive"
                            onClick={(e) => {
                              e.stopPropagation();
                              onDelete(profile.id);
                            }}
                          >
                            <Trash2 className="size-4" />
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent>{t("common:delete")}</TooltipContent>
                      </Tooltip>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-between mt-4">
          <span className="text-sm text-muted-foreground">
            Page {page + 1} of {totalPages}
          </span>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={page === 0}
              onClick={() => setPage((p) => p - 1)}
            >
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= totalPages - 1}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
