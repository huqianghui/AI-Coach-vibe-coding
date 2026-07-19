import { useState, useMemo } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Search } from "lucide-react";
import {
  Input,
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Skeleton,
} from "@/components/ui";
import { EmptyState } from "@/components/shared";
import { ScenarioCard } from "@/components/coach";
import { useActiveScenarioGroups, useCreateScenarioGroupRun } from "@/hooks/use-scenario-groups";
import { useActiveScenarios } from "@/hooks/use-scenarios";
import { useCreateSession } from "@/hooks/use-session";
import { useCreateConferenceSession } from "@/hooks/use-conference";
import { useFeatureFlags } from "@/hooks/use-config";
import type { Scenario } from "@/types/scenario";

const ALL_VALUE = "__all__";

function getScenarioModes(
  scenario: Scenario,
  features: { voice_live_enabled?: boolean; avatar_enabled?: boolean } | undefined,
) {
  const modes = ["text"];
  const hcp = scenario.hcp_profile;
  const voiceAvailable = Boolean(
    features?.voice_live_enabled && hcp?.voice_live_instance?.enabled,
  );
  const avatarAvailable = Boolean(
    voiceAvailable && features?.avatar_enabled && hcp?.avatar_enabled,
  );

  if (voiceAvailable) {
    modes.push("voice_realtime_model");
    if (avatarAvailable) {
      modes.push("digital_human_realtime_model");
    }
  }

  const defaultMode = avatarAvailable
    ? "digital_human_realtime_model"
    : voiceAvailable
      ? "voice_realtime_model"
      : "text";

  return { modes, defaultMode };
}

function getConferenceModes(
  scenario: Scenario,
  features:
    | {
        voice_enabled?: boolean;
        voice_live_enabled?: boolean;
        avatar_enabled?: boolean;
      }
    | undefined,
) {
  const voiceAvailable = Boolean(features?.voice_enabled);
  const hcp = scenario.hcp_profile;
  const avatarAvailable = Boolean(
    features?.voice_live_enabled &&
      features?.avatar_enabled &&
      hcp?.voice_live_instance?.enabled &&
      hcp?.avatar_enabled,
  );
  const modes = ["text"];
  if (voiceAvailable) {
    modes.push("voice_realtime_model");
  }
  if (avatarAvailable) {
    modes.push("digital_human_realtime_model");
  }

  return {
    modes,
    defaultMode: voiceAvailable
      ? "voice_realtime_model"
      : avatarAvailable
        ? "digital_human_realtime_model"
        : "text",
  };
}

export default function ScenarioSelection() {
  const { t } = useTranslation("coach");
  const { t: tc } = useTranslation("common");
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const [searchTerm, setSearchTerm] = useState("");
  const [selectedProduct, setSelectedProduct] = useState(ALL_VALUE);
  const [selectedDifficulty, setSelectedDifficulty] = useState(ALL_VALUE);
  const [selectedMode, setSelectedMode] = useState<"f2f" | "conference" | "group">(
    searchParams.get("mode") === "group"
      ? "group"
      : searchParams.get("mode") === "conference"
        ? "conference"
        : "f2f",
  );

  const { data, isLoading } = useActiveScenarios();
  const { data: groups, isLoading: groupsLoading } = useActiveScenarioGroups();
  const createSession = useCreateSession();
  const createConferenceSession = useCreateConferenceSession();
  const createGroupRun = useCreateScenarioGroupRun();
  const { data: config } = useFeatureFlags(true);

  const scenarios = data ?? [];

  const products = useMemo(
    () => [...new Set(scenarios.map((s) => s.product).filter(Boolean))] as string[],
    [scenarios]
  );
  const difficulties = useMemo(
    () => [...new Set(scenarios.map((s) => s.difficulty))],
    [scenarios]
  );

  const filteredScenarios = useMemo(() => {
    return scenarios.filter((s) => {
      const matchesSearch =
        searchTerm === "" ||
        s.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        s.description.toLowerCase().includes(searchTerm.toLowerCase());
      const matchesProduct =
        selectedProduct === ALL_VALUE || s.product === selectedProduct;
      const matchesDifficulty =
        selectedDifficulty === ALL_VALUE ||
        s.difficulty === selectedDifficulty;
      return matchesSearch && matchesProduct && matchesDifficulty;
    });
  }, [scenarios, searchTerm, selectedProduct, selectedDifficulty]);

  const handleStartTraining = async (scenarioId: string, mode: string) => {
    try {
      const session = await createSession.mutateAsync({ scenarioId, mode });
      navigate(`/user/training/session?id=${session.id}`);
    } catch {
      // Error handled by TanStack Query
    }
  };

  const handleStartConference = async (scenarioId: string, mode: string) => {
    try {
      const session = await createConferenceSession.mutateAsync({ scenarioId, mode });
      const isAudioMode =
        mode === "voice_realtime_model" || mode === "digital_human_realtime_model";
      const inputMode = isAudioMode ? "audio" : "text";
      navigate(`/user/training/conference?id=${session.id}&inputMode=${inputMode}`);
    } catch {
      // Error handled by TanStack Query
    }
  };

  const handleStartGroup = async (groupId: string) => {
    try {
      const run = await createGroupRun.mutateAsync(groupId);
      navigate(`/user/training/groups?id=${run.id}`);
    } catch {
      // Error handled by TanStack Query
    }
  };

  const handleModeChange = (mode: string) => {
    const nextMode = mode === "conference" ? "conference" : mode === "group" ? "group" : "f2f";
    setSelectedMode(nextMode);
    const nextParams = new URLSearchParams(searchParams);
    nextParams.set("mode", nextMode);
    setSearchParams(nextParams, { replace: true });
  };

  const filterRow = (
    <div className="mb-6 flex flex-wrap items-center gap-4">
      <Select value={selectedProduct} onValueChange={setSelectedProduct}>
        <SelectTrigger className="w-[180px]">
          <SelectValue placeholder={t("scenarioSelection.filterAllDifficulties")} />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ALL_VALUE}>{tc("allProducts")}</SelectItem>
          {products.map((product) => (
            <SelectItem key={product} value={product}>
              {product}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Select
        value={selectedDifficulty}
        onValueChange={setSelectedDifficulty}
      >
        <SelectTrigger className="w-[180px]">
          <SelectValue placeholder={t("scenarioSelection.filterAllDifficulties")} />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ALL_VALUE}>
            {t("scenarioSelection.filterAllDifficulties")}
          </SelectItem>
          {difficulties.map((d) => (
            <SelectItem key={d} value={d}>
              {d}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <div className="relative flex-1">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          className="pl-9"
          placeholder={t("scenarioSelection.searchPlaceholder")}
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
        />
      </div>
    </div>
  );

  const renderGrid = (mode: "f2f" | "conference", onStart: (scenarioId: string, trainingMode: string) => void) => {
    if (isLoading) {
      return (
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="overflow-hidden rounded-lg border border-border bg-card">
              <Skeleton className="h-48 w-full" />
              <div className="space-y-3 p-6">
                <Skeleton className="h-5 w-3/4" />
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-1/2" />
              </div>
            </div>
          ))}
        </div>
      );
    }

    const modeScenarios = filteredScenarios.filter((s) => s.mode === mode);

    if (modeScenarios.length === 0) {
      return (
        <EmptyState
          title={t("scenarioSelection.emptyTitle")}
          body={t("scenarioSelection.emptyBody")}
        />
      );
    }

    return (
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
        {modeScenarios.map((scenario) => {
          const { modes, defaultMode } =
            mode === "conference"
              ? getConferenceModes(scenario, config?.features)
              : getScenarioModes(scenario, config?.features);
          return (
            <ScenarioCard
              key={scenario.id}
              scenario={scenario}
              onStart={onStart}
              availableModes={modes}
              defaultMode={defaultMode}
            />
          );
        })}
      </div>
    );
  };

  const renderGroupGrid = () => {
    if (groupsLoading) {
      return (
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="overflow-hidden rounded-lg border border-border bg-card p-6">
              <Skeleton className="h-5 w-3/4" />
              <Skeleton className="mt-4 h-4 w-full" />
              <Skeleton className="mt-2 h-4 w-1/2" />
            </div>
          ))}
        </div>
      );
    }
    const activeGroups = groups ?? [];
    if (activeGroups.length === 0) {
      return <EmptyState title="暂无组合训练" body="管理员发布组合场景后会显示在这里。" />;
    }
    return (
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
        {activeGroups.map((group) => (
          <div key={group.id} className="rounded-lg border border-border bg-card p-6 shadow-sm">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold text-foreground">{group.name}</h2>
                <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">
                  {group.description}
                </p>
              </div>
              <span className="rounded-full bg-primary/10 px-2 py-1 text-xs font-medium text-primary">
                {group.items.length} 个场景
              </span>
            </div>
            <div className="mt-4 space-y-2">
              {group.items.slice(0, 3).map((item) => (
                <div key={item.id} className="flex items-center justify-between text-sm">
                  <span className="truncate text-muted-foreground">{item.scenario?.name}</span>
                  <span className="ml-2 text-xs text-muted-foreground">{item.weight}</span>
                </div>
              ))}
            </div>
            <button
              type="button"
              onClick={() => void handleStartGroup(group.id)}
              className="mt-5 w-full rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-primary/90"
            >
              开始组合训练
            </button>
          </div>
        ))}
      </div>
    );
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-medium text-foreground">
        {t("scenarioSelection.title")}
      </h1>

      <Tabs value={selectedMode} onValueChange={handleModeChange}>
        <TabsList>
          <TabsTrigger value="f2f">
            {t("scenarioSelection.tabF2F")}
          </TabsTrigger>
          <TabsTrigger value="conference">
            {t("scenarioSelection.tabConference")}
          </TabsTrigger>
          <TabsTrigger value="group">组合训练</TabsTrigger>
        </TabsList>

        <TabsContent value="f2f" className="mt-6">
          {filterRow}
          {renderGrid("f2f", handleStartTraining)}
        </TabsContent>

        <TabsContent value="conference" className="mt-6">
          {filterRow}
          {renderGrid("conference", handleStartConference)}
        </TabsContent>

        <TabsContent value="group" className="mt-6">
          {filterRow}
          {renderGroupGrid()}
        </TabsContent>
      </Tabs>
    </div>
  );
}
