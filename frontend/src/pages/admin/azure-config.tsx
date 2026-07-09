import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Brain,
  Mic,
  Volume2,
  User,
  FileSearch,
  Loader2,
  Phone,
  Server,
  ChevronDown,
  ChevronUp,
  Eye,
  EyeOff,
  Check,
  X,
  Info,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useServiceConfigs,
  useUpdateServiceConfig,
  useTestServiceConnection,
  useAIFoundryConfig,
  useUpdateAIFoundry,
  useTestAIFoundry,
} from "@/hooks/use-azure-config";
import { useRegionCapabilities } from "@/hooks/use-region-capabilities";
import type { RegionStatus } from "@/types/azure-config";

interface AzureServiceDef {
  key: string;
  backendKey: string;
  name: string;
  description: string;
  icon: React.ReactNode;
  modelPlaceholder: string;
  /** Show per-service endpoint override (for services on different Azure resource). */
  allowEndpointOverride?: boolean;
  endpointPlaceholder?: string;
}

const AZURE_SERVICES: AzureServiceDef[] = [
  {
    key: "openai",
    backendKey: "azure_openai",
    name: "Azure OpenAI",
    description: "LLM for AI coaching conversations and scoring",
    icon: <Brain className="size-5 text-primary" />,
    modelPlaceholder: "e.g. gpt-4o, gpt-5.4-mini",
  },
  {
    key: "speechStt",
    backendKey: "azure_speech_stt",
    name: "Azure Speech (STT)",
    description: "Speech-to-text for voice input recognition",
    icon: <Mic className="size-5 text-primary" />,
    modelPlaceholder: "",
    allowEndpointOverride: true,
    endpointPlaceholder: "https://{name}.cognitiveservices.azure.com",
  },
  {
    key: "speechTts",
    backendKey: "azure_speech_tts",
    name: "Azure Speech (TTS)",
    description: "Text-to-speech for HCP voice responses",
    icon: <Volume2 className="size-5 text-primary" />,
    modelPlaceholder: "",
    allowEndpointOverride: true,
    endpointPlaceholder: "https://{name}.cognitiveservices.azure.com",
  },
  {
    key: "avatar",
    backendKey: "azure_avatar",
    name: "Azure AI Avatar",
    description: "Digital human avatar for HCP visualization",
    icon: <User className="size-5 text-primary" />,
    modelPlaceholder: "Lisa-casual-sitting",
    allowEndpointOverride: true,
    endpointPlaceholder: "https://{name}.cognitiveservices.azure.com",
  },
  {
    key: "contentUnderstanding",
    backendKey: "azure_content",
    name: "Azure Content Understanding",
    description: "Multimodal evaluation for training materials",
    icon: <FileSearch className="size-5 text-primary" />,
    modelPlaceholder: "",
    allowEndpointOverride: true,
    endpointPlaceholder: "https://{name}.services.ai.azure.com",
  },
  {
    key: "realtime",
    backendKey: "azure_openai_realtime",
    name: "Azure OpenAI Realtime",
    description: "Real-time audio streaming for voice conversations",
    icon: <Mic className="size-5 text-primary" />,
    modelPlaceholder: "gpt-4o-realtime-preview",
  },
  {
    key: "voiceLive",
    backendKey: "azure_voice_live",
    name: "Azure Voice Live API",
    description: "Real-time voice coaching with configurable model",
    icon: <Phone className="size-5 text-primary" />,
    modelPlaceholder: "e.g. gpt-4o-realtime-preview",
  },
];

function ConfigSkeleton() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <Skeleton className="h-7 w-48" />
        <Skeleton className="h-9 w-36" />
      </div>
      <Skeleton className="h-64 w-full rounded-lg" />
      <div className="space-y-3">
        <Skeleton className="h-5 w-32" />
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-16 w-full rounded-lg" />
        ))}
      </div>
    </div>
  );
}

export default function AzureConfigPage() {
  const { t } = useTranslation("admin");
  const { data: savedConfigs, isLoading: configsLoading } = useServiceConfigs();
  const { data: aiFoundryData, isLoading: foundryLoading } = useAIFoundryConfig();
  const updateServiceMutation = useUpdateServiceConfig();
  const testMutation = useTestServiceConnection();
  const updateFoundryMutation = useUpdateAIFoundry();
  const testFoundryMutation = useTestAIFoundry();

  // AI Foundry form state
  const [aiFoundryEndpoint, setAiFoundryEndpoint] = useState("");
  const [aiFoundryRegion, setAiFoundryRegion] = useState("");
  const [aiFoundryApiKey, setAiFoundryApiKey] = useState("");
  const [aiFoundryModel, setAiFoundryModel] = useState("");
  const [aiFoundryProject, setAiFoundryProject] = useState("");
  const [showApiKey, setShowApiKey] = useState(false);

  // Initialize AI Foundry form from loaded data
  useEffect(() => {
    if (aiFoundryData) {
      setAiFoundryEndpoint(aiFoundryData.endpoint || "");
      setAiFoundryRegion(aiFoundryData.region || "");
      setAiFoundryModel(aiFoundryData.model_or_deployment || "");
      setAiFoundryProject(aiFoundryData.default_project || "");
    }
  }, [aiFoundryData]);

  // Per-service expanded state
  const [expandedService, setExpandedService] = useState<string | null>(null);

  // Test all state
  const [testingAll, setTestingAll] = useState(false);

  // Region capabilities
  const regionForCaps = aiFoundryRegion || savedConfigs?.find((c) => c.region)?.region;
  const { data: regionCaps, isError: regionCapsError } = useRegionCapabilities(regionForCaps);

  const getRegionStatus = (backendKey: string): RegionStatus | undefined => {
    if (!regionForCaps) return undefined;
    if (regionCapsError) return "unknown";
    if (!regionCaps) return undefined;
    const svc = regionCaps.services[backendKey];
    if (!svc) return "unknown";
    return svc.available ? "available" : "unavailable";
  };

  const getSavedConfig = (backendKey: string) => {
    return savedConfigs?.find((c) => c.service_name === backendKey);
  };

  const handleSaveFoundry = () => {
    updateFoundryMutation.mutate(
      {
        endpoint: aiFoundryEndpoint,
        region: aiFoundryRegion,
        api_key: aiFoundryApiKey,
        model_or_deployment: aiFoundryModel,
        default_project: aiFoundryProject,
      },
      {
        onSuccess: () => {
          toast.success(t("azureConfig.saved"));
          setAiFoundryApiKey("");
        },
        onError: () => toast.error(t("azureConfig.saveFailed")),
      },
    );
  };

  const handleTestFoundry = () => {
    // Save first, then test
    updateFoundryMutation.mutate(
      {
        endpoint: aiFoundryEndpoint,
        region: aiFoundryRegion,
        api_key: aiFoundryApiKey,
        model_or_deployment: aiFoundryModel,
        default_project: aiFoundryProject,
      },
      {
        onSuccess: () => {
          setAiFoundryApiKey("");
          testFoundryMutation.mutate(undefined, {
            onSuccess: (result) => {
              if (result.success) {
                toast.success(`AI Foundry: ${result.message}`);
                if (result.region) {
                  setAiFoundryRegion(result.region);
                }
              } else {
                toast.error(`AI Foundry: ${result.message}`);
              }
            },
            onError: () => toast.error("AI Foundry: Connection test failed"),
          });
        },
        onError: () => toast.error(t("azureConfig.saveFailed")),
      },
    );
  };

  const handleTestAll = async () => {
    setTestingAll(true);
    try {
      const configuredServices = savedConfigs?.filter((c) => c.is_active && c.endpoint) ?? [];
      for (const svc of configuredServices) {
        try {
          const result = await testMutation.mutateAsync(svc.service_name);
          if (result.success) {
            toast.success(`${svc.display_name}: ${result.message}`);
          } else {
            toast.error(`${svc.display_name}: ${result.message}`);
          }
        } catch {
          toast.error(`${svc.display_name}: Connection failed`);
        }
      }
    } finally {
      setTestingAll(false);
    }
  };

  const handleToggleService = (backendKey: string, enabled: boolean) => {
    const existing = getSavedConfig(backendKey);
    updateServiceMutation.mutate({
      serviceName: backendKey,
      config: {
        endpoint: existing?.endpoint ?? "",
        api_key: "",
        model_or_deployment: existing?.model_or_deployment ?? "",
        region: existing?.region ?? "",
        is_active: enabled,
      },
    });
  };

  const handleSaveServiceConfig = (
    backendKey: string,
    opts: { model?: string; endpoint?: string; apiKey?: string },
  ) => {
    const existing = getSavedConfig(backendKey);
    updateServiceMutation.mutate(
      {
        serviceName: backendKey,
        config: {
          endpoint: opts.endpoint ?? existing?.endpoint ?? "",
          api_key: opts.apiKey ?? "",
          model_or_deployment: opts.model ?? existing?.model_or_deployment ?? "",
          region: existing?.region ?? "",
        },
      },
      {
        onSuccess: () => toast.success(t("azureConfig.saved")),
        onError: () => toast.error(t("azureConfig.saveFailed")),
      },
    );
  };

  const handleTestService = async (backendKey: string) => {
    try {
      const result = await testMutation.mutateAsync(backendKey);
      if (result.success) {
        toast.success(result.message);
      } else {
        toast.error(result.message);
      }
    } catch {
      toast.error(t("azureConfig.connectionFailed"));
    }
  };

  if (configsLoading || foundryLoading) {
    return <ConfigSkeleton />;
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-medium text-foreground">{t("azureConfig.title")}</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {t("azureConfig.description")}
          </p>
        </div>
        <Button variant="outline" onClick={handleTestAll} disabled={testingAll}>
          {testingAll && <Loader2 className="size-4 animate-spin" />}
          {t("azureConfig.testAll")}
        </Button>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Section 1: AI Foundry Master Config Card - full width */}
        <Card className="bg-card rounded-lg border border-primary/30 shadow-sm lg:col-span-2">
          <CardHeader>
            <div className="flex items-center gap-3">
              <div className="flex size-10 items-center justify-center rounded-lg bg-primary/10">
                <Server className="size-5 text-primary" />
              </div>
              <div>
                <CardTitle className="text-lg font-medium">{t("azureConfig.aiFoundry.title")}</CardTitle>
                <CardDescription>{t("azureConfig.aiFoundry.description")}</CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div className="grid gap-2">
                <Label>{t("azureConfig.aiFoundry.endpoint")}</Label>
                <Input
                  value={aiFoundryEndpoint}
                  onChange={(e) => setAiFoundryEndpoint(e.target.value)}
                  placeholder={t("azureConfig.aiFoundry.endpointPlaceholder")}
                />
              </div>
              <div className="grid gap-2">
                <Label>{t("azureConfig.aiFoundry.project")}</Label>
                <Input
                  value={aiFoundryProject}
                  onChange={(e) => setAiFoundryProject(e.target.value)}
                  placeholder={t("azureConfig.aiFoundry.projectPlaceholder")}
                />
                <p className="text-xs text-muted-foreground">
                  {t("azureConfig.aiFoundry.projectHint")}
                </p>
              </div>
              <div className="grid gap-2">
                <Label>{t("azureConfig.aiFoundry.model")}</Label>
                <Input
                  value={aiFoundryModel}
                  onChange={(e) => setAiFoundryModel(e.target.value)}
                  placeholder={t("azureConfig.aiFoundry.modelPlaceholder")}
                />
                <p className="text-xs text-muted-foreground">
                  {t("azureConfig.aiFoundry.modelHint")}
                </p>
              </div>
            </div>
            <div className="grid gap-2">
              <Label>{t("azureConfig.aiFoundry.apiKey")}</Label>
              <div className="relative max-w-md">
                <Input
                  type={showApiKey ? "text" : "password"}
                  value={aiFoundryApiKey}
                  onChange={(e) => setAiFoundryApiKey(e.target.value)}
                  placeholder={t("azureConfig.aiFoundry.apiKeyPlaceholder")}
                  className="pr-10"
                />
                <button
                  type="button"
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground transition-colors duration-150 hover:text-foreground"
                  onClick={() => setShowApiKey((v) => !v)}
                  tabIndex={-1}
                >
                  {showApiKey ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                </button>
              </div>
              {aiFoundryData?.masked_key && (
                <p className="text-xs text-muted-foreground">
                  Current: {aiFoundryData.masked_key}
                </p>
              )}
              <p className="text-xs text-muted-foreground">
                {t("azureConfig.aiFoundry.apiKeyHint")}
              </p>
            </div>
            <div className="grid gap-2 max-w-sm">
              <Label>{t("azureConfig.aiFoundry.region")}</Label>
              <Input
                value={aiFoundryRegion}
                onChange={(e) => setAiFoundryRegion(e.target.value)}
                placeholder={t("azureConfig.aiFoundry.regionPlaceholder")}
              />
            </div>
            <div className="flex items-center gap-3 pt-2">
              <Button
                onClick={handleSaveFoundry}
                disabled={updateFoundryMutation.isPending}
              >
                {updateFoundryMutation.isPending && (
                  <Loader2 className="size-4 animate-spin" />
                )}
                {t("azureConfig.saveConfig")}
              </Button>
              <Button
                variant="outline"
                onClick={handleTestFoundry}
                disabled={testFoundryMutation.isPending || updateFoundryMutation.isPending}
              >
                {(testFoundryMutation.isPending || updateFoundryMutation.isPending) && (
                  <Loader2 className="size-4 animate-spin" />
                )}
                {t("azureConfig.testConnection")}
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Section 2: Per-Service Toggle List */}
        <div className="space-y-3 lg:col-span-2">
          <div>
            <h2 className="text-lg font-medium text-foreground">{t("azureConfig.services.title")}</h2>
            <p className="text-sm text-muted-foreground">{t("azureConfig.services.description")}</p>
          </div>

          <div className="grid grid-cols-1 items-start gap-3 lg:grid-cols-2">
            {AZURE_SERVICES.map((svc) => {
              const saved = getSavedConfig(svc.backendKey);
              const isActive = saved?.is_active ?? false;
              const isExpanded = expandedService === svc.key;
              const regionStatus = getRegionStatus(svc.backendKey);

              return (
                <Card key={svc.key} className="bg-card overflow-hidden border border-border shadow-sm">
                  <div className="flex items-center justify-between px-4 py-3">
                    <button
                      type="button"
                      className="flex flex-1 items-center gap-3 text-left transition-colors duration-150"
                      onClick={() => setExpandedService(isExpanded ? null : svc.key)}
                    >
                      <div className="flex size-9 items-center justify-center rounded-md bg-primary/10">
                        {svc.icon}
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium text-foreground">{svc.name}</span>
                          {/* Status dot */}
                          <span
                            className={`inline-block w-2.5 h-2.5 rounded-full ${
                              isActive
                                ? "bg-strength"
                                : "bg-muted-foreground"
                            }`}
                          />
                          {regionStatus && (
                            <RegionBadge status={regionStatus} region={regionForCaps ?? ""} t={t} />
                          )}
                        </div>
                        <p className="text-xs text-muted-foreground truncate">{svc.description}</p>
                      </div>
                      {isExpanded ? (
                        <ChevronUp className="size-4 text-muted-foreground shrink-0" />
                      ) : (
                        <ChevronDown className="size-4 text-muted-foreground shrink-0" />
                      )}
                    </button>
                    <div className="ml-3 shrink-0">
                      <Switch
                        checked={isActive}
                        onCheckedChange={(checked) => handleToggleService(svc.backendKey, checked)}
                        aria-label={`Enable ${svc.name}`}
                      />
                    </div>
                  </div>

                  {isExpanded && (
                    <ServiceExpandedContent
                      svc={svc}
                      saved={saved}
                      onSaveConfig={handleSaveServiceConfig}
                      onTest={handleTestService}
                      testMutation={testMutation}
                      t={t}
                    />
                  )}
                </Card>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}

/** Region availability badge. */
function RegionBadge({
  status,
  region,
  t,
}: {
  status: RegionStatus;
  region: string;
  t: (key: string, opts?: Record<string, string>) => string;
}) {
  if (status === "available") {
    return (
      <span
        role="status"
        className="inline-flex items-center gap-1 rounded-sm border border-strength/20 bg-strength/10 px-1.5 py-0.5 text-[10px] font-medium text-strength"
      >
        <Check className="size-2.5" aria-hidden="true" />
        {t("azureConfig.regionAvailable", { region })}
      </span>
    );
  }
  if (status === "unavailable") {
    return (
      <span
        role="status"
        className="inline-flex items-center gap-1 rounded-sm border border-chart-2/20 bg-chart-2/10 px-1.5 py-0.5 text-[10px] font-medium text-chart-2"
      >
        <X className="size-2.5" aria-hidden="true" />
        {t("azureConfig.regionUnavailable", { region })}
      </span>
    );
  }
  return (
    <span
      role="status"
      className="inline-flex items-center gap-1 rounded-sm border border-border bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground"
    >
      <Info className="size-2.5" aria-hidden="true" />
      {t("azureConfig.regionUnknown")}
    </span>
  );
}

/** Expanded row content for a per-service toggle. */
function ServiceExpandedContent({
  svc,
  saved,
  onSaveConfig,
  onTest,
  testMutation,
  t,
}: {
  svc: AzureServiceDef;
  saved: { model_or_deployment?: string; endpoint?: string; masked_key?: string } | undefined;
  onSaveConfig: (
    backendKey: string,
    opts: { model?: string; endpoint?: string; apiKey?: string },
  ) => void;
  onTest: (backendKey: string) => Promise<void>;
  testMutation: { isPending: boolean };
  t: (key: string, opts?: Record<string, string>) => string;
}) {
  const [modelValue, setModelValue] = useState(saved?.model_or_deployment ?? "");
  const [endpointValue, setEndpointValue] = useState(saved?.endpoint ?? "");
  const [apiKeyValue, setApiKeyValue] = useState("");
  const [showKey, setShowKey] = useState(false);

  const hasModelConfig = !!svc.modelPlaceholder;
  const hasEndpointOverride = !!svc.allowEndpointOverride;
  const hasAnyConfig = hasModelConfig || hasEndpointOverride;

  const handleSave = () => {
    onSaveConfig(svc.backendKey, {
      model: hasModelConfig ? modelValue : undefined,
      endpoint: hasEndpointOverride ? endpointValue : undefined,
      apiKey: hasEndpointOverride ? apiKeyValue : undefined,
    });
    if (apiKeyValue) setApiKeyValue("");
  };

  return (
    <div className="border-t border-border px-4 py-3 space-y-3 bg-muted/30">
      {hasEndpointOverride && (
        <div className="space-y-2">
          <p className="text-[11px] text-muted-foreground">
            {t("azureConfig.endpointOverrideHint")}
          </p>
          <div className="grid gap-2 max-w-md">
            <Label className="text-xs">
              {t("azureConfig.endpoint")}
            </Label>
            <Input
              value={endpointValue}
              onChange={(e) => setEndpointValue(e.target.value)}
              placeholder={svc.endpointPlaceholder ?? "https://...azure.com"}
              className="h-8 text-sm font-mono"
            />
          </div>
          <div className="grid gap-2 max-w-md">
            <Label className="text-xs">
              {t("azureConfig.apiKeyOverride")}
            </Label>
            <div className="relative">
              <Input
                type={showKey ? "text" : "password"}
                value={apiKeyValue}
                onChange={(e) => setApiKeyValue(e.target.value)}
                placeholder={saved?.masked_key || t("azureConfig.apiKeyPlaceholder")}
                className="h-8 pr-8 text-sm font-mono"
              />
              <button
                type="button"
                className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                onClick={() => setShowKey(!showKey)}
              >
                {showKey ? <EyeOff className="size-3.5" /> : <Eye className="size-3.5" />}
              </button>
            </div>
          </div>
        </div>
      )}
      {hasModelConfig && (
        <div className="grid gap-2 max-w-sm">
          <Label className="text-xs">{t("azureConfig.model")}</Label>
          <Input
            value={modelValue}
            onChange={(e) => setModelValue(e.target.value)}
            placeholder={svc.modelPlaceholder}
            className="h-8 text-sm"
          />
        </div>
      )}
      <div className="flex items-center gap-2">
        {hasAnyConfig && (
          <Button size="sm" variant="default" onClick={handleSave}>
            {t("azureConfig.saveConfig")}
          </Button>
        )}
        <Button
          size="sm"
          variant={hasAnyConfig ? "outline" : "default"}
          onClick={() => void onTest(svc.backendKey)}
          disabled={testMutation.isPending}
        >
          {testMutation.isPending && <Loader2 className="size-3 animate-spin" />}
          {t("azureConfig.testConnection")}
        </Button>
      </div>
    </div>
  );
}
