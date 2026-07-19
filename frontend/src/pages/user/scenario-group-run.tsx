import { useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { CheckCircle2, MessageSquareText, Mic, Play, RefreshCw, User } from "lucide-react";
import { Button, Badge } from "@/components/ui";
import { LoadingState } from "@/components/shared";
import { useFeatureFlags } from "@/hooks/use-config";
import {
  useCreateScenarioGroupRunSession,
  useRefreshScenarioGroupRunScore,
  useScenarioGroupRun,
} from "@/hooks/use-scenario-groups";
import { cn } from "@/lib/utils";
import type { ScenarioGroupRunItem } from "@/types/scenario-group";
import type { Scenario } from "@/types/scenario";

const TRAINING_MODES = [
  { value: "text", label: "文字", icon: MessageSquareText },
  { value: "voice_realtime_model", label: "语音", icon: Mic },
  { value: "digital_human_realtime_model", label: "数字人", icon: User },
] as const;

function getAvailableModes(
  scenario: Scenario | null | undefined,
  features:
    | {
        voice_enabled?: boolean;
        voice_live_enabled?: boolean;
        avatar_enabled?: boolean;
      }
    | undefined,
) {
  const modes = ["text"];
  const hcp = scenario?.hcp_profile;
  const voiceAvailable = scenario?.mode === "conference"
    ? Boolean(features?.voice_enabled)
    : Boolean(features?.voice_live_enabled && hcp?.voice_live_instance?.enabled);
  const avatarAvailable = scenario?.mode === "conference"
    ? Boolean(
        features?.voice_live_enabled &&
          features?.avatar_enabled &&
          hcp?.voice_live_instance?.enabled &&
          hcp?.avatar_enabled,
      )
    : Boolean(voiceAvailable && features?.avatar_enabled && hcp?.avatar_enabled);

  if (voiceAvailable) {
    modes.push("voice_realtime_model");
  }
  if (avatarAvailable) {
    modes.push("digital_human_realtime_model");
  }

  const defaultMode = avatarAvailable
    ? "digital_human_realtime_model"
    : voiceAvailable
      ? "voice_realtime_model"
      : "text";

  return { modes, defaultMode };
}

export default function ScenarioGroupRunPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const runId = searchParams.get("id") ?? "";
  const { data: run, isLoading } = useScenarioGroupRun(runId || undefined);
  const createSession = useCreateScenarioGroupRunSession();
  const refreshScore = useRefreshScenarioGroupRunScore();
  const { data: config } = useFeatureFlags(true);
  const [selectedModes, setSelectedModes] = useState<Record<string, string>>({});

  const sortedItems = useMemo(
    () => [...(run?.items ?? [])].sort((a, b) => a.sortOrder - b.sortOrder),
    [run?.items],
  );
  const completedCount = sortedItems.filter((item) =>
    item.status === "completed" || item.status === "scored"
  ).length;

  const getSelectedMode = (item: ScenarioGroupRunItem) => {
    const { modes, defaultMode } = getAvailableModes(item.scenario, config?.features);
    const selected = selectedModes[item.id];
    return selected && modes.includes(selected) ? selected : defaultMode;
  };

  const handleStartItem = async (item: ScenarioGroupRunItem, retrain = false) => {
    const mode = getSelectedMode(item);
    const session = item.sessionId && !retrain
      ? { id: item.sessionId }
      : await createSession.mutateAsync({ runId, runItemId: item.id, mode, retrain });
    if (item.scenario?.mode === "conference") {
      const inputMode = mode === "text" ? "text" : "audio";
      navigate(`/user/training/conference?id=${session.id}&inputMode=${inputMode}&groupRunId=${runId}`);
    } else {
      navigate(`/user/training/session?id=${session.id}&groupRunId=${runId}`);
    }
  };

  if (isLoading || !run) {
    return <LoadingState variant="card" />;
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-medium text-foreground">{run.groupName ?? "组合训练"}</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            已完成 {completedCount}/{sortedItems.length} 个场景
          </p>
        </div>
        <Button
          variant="outline"
          onClick={() => refreshScore.mutate(run.id)}
          disabled={refreshScore.isPending}
        >
          <RefreshCw className="size-4" />
          刷新成绩
        </Button>
      </div>

      {run.overallScore != null && (
        <div className="rounded-lg border border-border bg-card p-6">
          <div className="text-sm text-muted-foreground">组合总分</div>
          <div className="mt-2 flex items-end gap-3">
            <span className="text-4xl font-semibold text-foreground">{Math.round(run.overallScore)}</span>
            <span className="pb-1 text-sm text-muted-foreground">/ 100</span>
            <Badge variant={run.passed ? "success" : "destructive"}>
              {run.passed ? "通过" : "未通过"}
            </Badge>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {sortedItems.map((item, index) => (
          <div key={item.id} className="rounded-lg border border-border bg-card p-5">
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="text-xs font-medium text-muted-foreground">场景 {index + 1}</div>
                <h2 className="mt-1 text-lg font-semibold text-foreground">
                  {item.scenario?.name ?? item.scenarioId}
                </h2>
                <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">
                  {item.scenario?.description}
                </p>
              </div>
              <Badge variant="outline">权重 {item.weight}</Badge>
            </div>

            <div className="mt-4 space-y-4">
              <div>
                <div className="mb-1.5 text-xs font-medium text-muted-foreground">训练模式</div>
                <div className="grid grid-cols-3 gap-1 rounded-lg border border-border bg-muted/50 p-1">
                  {TRAINING_MODES.map((mode) => {
                    const { modes } = getAvailableModes(item.scenario, config?.features);
                    const Icon = mode.icon;
                    const isDisabled = !modes.includes(mode.value);
                    const isSelected = getSelectedMode(item) === mode.value;
                    return (
                      <button
                        key={mode.value}
                        type="button"
                        disabled={isDisabled}
                        onClick={() => setSelectedModes((prev) => ({ ...prev, [item.id]: mode.value }))}
                        className={cn(
                          "flex min-w-0 items-center justify-center gap-1 rounded-md px-2 py-1.5 text-xs font-medium transition-colors",
                          isDisabled
                            ? "cursor-not-allowed text-muted-foreground/40"
                            : isSelected
                              ? "bg-background text-foreground shadow-sm"
                              : "text-muted-foreground hover:text-foreground",
                        )}
                      >
                        <Icon className="size-3.5 shrink-0" />
                        <span className="truncate">{mode.label}</span>
                      </button>
                    );
                  })}
                </div>
                {item.sessionId && item.status === "in_progress" && (
                  <p className="mt-1 text-xs text-muted-foreground">继续当前训练会沿用已创建时的模式。</p>
                )}
              </div>

              <div className="flex items-center justify-between gap-3">
                <div className="text-sm text-muted-foreground">
                  {item.score != null ? (
                    <span className="inline-flex items-center gap-1 text-success-700">
                      <CheckCircle2 className="size-4" />
                      {Math.round(item.score)} 分
                    </span>
                  ) : item.status === "completed" ? (
                    "已完成，待评分"
                  ) : item.status === "in_progress" ? (
                    "训练中"
                  ) : (
                    "未开始"
                  )}
                </div>
                <div className="flex flex-wrap justify-end gap-2">
                  {item.sessionId && (item.status === "completed" || item.status === "scored") && (
                    <Button
                      variant="outline"
                      onClick={() => void handleStartItem(item, true)}
                      disabled={createSession.isPending}
                    >
                      <RefreshCw className="size-4" />
                      重新训练
                    </Button>
                  )}
                  <Button
                    onClick={() => void handleStartItem(item)}
                    disabled={createSession.isPending}
                  >
                    <Play className="size-4" />
                    {item.sessionId ? "继续/查看" : "开始训练"}
                  </Button>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
