import { useState, useCallback, useEffect, useRef } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { toast } from "sonner";
import {
  ArrowLeft,
  Save,
  Rocket,
  RefreshCw,
  Download,
  FileText,
  FileCode,
  File as FileIcon,
  Check,
  XCircle,
  AlertTriangle,
  ExternalLink,
  Info,
  Cpu,
  ChevronDown,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { SopEditor } from "@/components/shared/sop-editor";
import { ConversionProgress } from "@/components/shared/conversion-progress";
import { SkillMaterialUploader } from "@/components/shared/skill-material-uploader";
import { FileTreeView } from "@/components/shared/file-tree-view";
import { QualityRadarChart } from "@/components/shared/quality-radar-chart";
import { QualityScoreCard } from "@/components/shared/quality-score-card";
import { PublishGateDialog } from "@/components/shared/publish-gate-dialog";
import { DryRunButton } from "@/components/shared/dry-run-button";
import { DryRunProgress as DryRunProgressComponent } from "@/components/shared/dry-run-progress";
import { DryRunHistoryList } from "@/components/shared/dry-run-history-list";
import { SkillFoundryStatusSection } from "@/components/admin/skill-foundry-status-section";
import {
  useSkill,
  useUpdateSkill,
  useCreateSkill,
  useRegenerateSop,
  useConversionStatus,
  useUploadAndConvert,
  useUploadResources,
  useRetryConversion,
  useCheckStructure,
  useEvaluateQuality,
  useSkillEvaluation,
  usePublishSkill,
  useRetryFoundrySync,
  skillKeys,
} from "@/hooks/use-skills";
import { downloadResource, downloadSkillZip } from "@/api/skills";
import { useQueryClient } from "@tanstack/react-query";
import { cn } from "@/lib/utils";
import type {
  SkillResource,
  ConversionStatus,
  QualityDimension,
  QualityEvaluation,
  EvaluationCriterion,
  EvaluationStatus,
} from "@/types/skill";

const VALID_TABS = new Set(["content", "resources", "quality", "settings"]);

// ---------------------------------------------------------------------------
// Settings form schema
// ---------------------------------------------------------------------------
const settingsSchema = z.object({
  name: z.string().min(2),
  description: z.string().optional(),
  product: z.string().optional(),
  therapeutic_area: z.string().optional(),
  tags: z.string().optional(),
  compatibility: z.string().optional(),
});

type SettingsFormValues = z.infer<typeof settingsSchema>;

export default function SkillEditorPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { t } = useTranslation("skill");
  const queryClient = useQueryClient();

  const isNew = !id;

  // ---------------------------------------------------------------------------
  // Data hooks
  // ---------------------------------------------------------------------------
  const { data: skill, isLoading } = useSkill(id);
  const updateMutation = useUpdateSkill();
  const createMutation = useCreateSkill();
  const regenerateMutation = useRegenerateSop();
  const uploadConvertMutation = useUploadAndConvert();
  const uploadResourcesMutation = useUploadResources();
  const retryConversionMutation = useRetryConversion();
  const checkStructureMutation = useCheckStructure();
  const evaluateQualityMutation = useEvaluateQuality();
  const publishMutation = usePublishSkill();
  const retryFoundrySyncMutation = useRetryFoundrySync();
  const { data: evaluationData, refetch: refetchEvaluation } =
    useSkillEvaluation(id);

  // Conversion polling: active when status is pending/processing
  const isConverting =
    skill?.conversion_status === "pending" ||
    skill?.conversion_status === "processing";
  const { data: conversionData } = useConversionStatus(id ?? "", isConverting);

  // ---------------------------------------------------------------------------
  // Local state
  // ---------------------------------------------------------------------------
  const [activeTab, setActiveTab] = useState("content");
  const [sopContent, setSopContent] = useState("");
  const [contentDirty, setContentDirty] = useState(false);
  const [highlighted, setHighlighted] = useState(false);
  const highlightTimerRef = useRef<ReturnType<typeof setTimeout>>();
  const [selectedResource, setSelectedResource] = useState<
    SkillResource | "SKILL.md" | null
  >(null);
  const [expandedDimensions, setExpandedDimensions] = useState<
    Record<string, boolean>
  >({});
  const [publishDialogOpen, setPublishDialogOpen] = useState(false);
  const [activeDryRunId, setActiveDryRunId] = useState<string | null>(null);

  // Settings form
  const settingsForm = useForm<SettingsFormValues>({
    resolver: zodResolver(settingsSchema),
    mode: "onChange",
    defaultValues: {
      name: "",
      description: "",
      product: "",
      therapeutic_area: "",
      tags: "",
      compatibility: "",
    },
  });

  // Header display name — watches settings form in real-time
  const headerName = settingsForm.watch("name");

  // Sync local state from fetched skill
  useEffect(() => {
    if (skill) {
      setSopContent(skill.content ?? "");
      setContentDirty(false);
      settingsForm.reset({
        name: skill.name ?? "",
        description: skill.description ?? "",
        product: skill.product ?? "",
        therapeutic_area: skill.therapeutic_area ?? "",
        tags: skill.tags ?? "",
        compatibility: skill.compatibility ?? "",
      });
    }
  }, [skill, settingsForm]);

  // On conversion completed, refetch skill
  useEffect(() => {
    if (
      conversionData?.status === "completed" &&
      skill?.conversion_status !== "completed"
    ) {
      queryClient.invalidateQueries({ queryKey: skillKeys.detail(id ?? "") });
    }
  }, [conversionData?.status, skill?.conversion_status, id, queryClient]);

  const handleTabChange = (value: string) => {
    setActiveTab(VALID_TABS.has(value) ? value : "content");
  };

  // ---------------------------------------------------------------------------
  // Handlers
  // ---------------------------------------------------------------------------
  const handleSaveDraft = useCallback(async () => {
    const nameToSave = (settingsForm.getValues("name") ?? "").trim() || t("editor.defaultSkillName");
    if (isNew) {
      createMutation.mutate(
        { name: nameToSave, content: sopContent },
        {
          onSuccess: (created) => {
            toast.success(
              t("editor.saved"),
            );
            navigate(`/admin/skills/${created.id}/edit`, { replace: true });
          },
          onError: () => toast.error(t("errors.saveFailed")),
        },
      );
    } else if (id) {
      updateMutation.mutate(
        { id, data: { name: nameToSave, content: sopContent } },
        {
          onSuccess: () => {
            setContentDirty(false);
            toast.success(
              t("editor.saved"),
            );
          },
          onError: () => toast.error(t("errors.saveFailed")),
        },
      );
    }
  }, [isNew, id, settingsForm, sopContent, createMutation, updateMutation, navigate, t]);

  const handleContentChange = useCallback((content: string) => {
    setSopContent(content);
    setContentDirty(true);
  }, []);

  const handleAiRegenerate = useCallback(
    async (feedback: string) => {
      if (!id) return;
      await regenerateMutation.mutateAsync({ id, feedback });
      // Trigger highlight animation
      setHighlighted(true);
      if (highlightTimerRef.current) clearTimeout(highlightTimerRef.current);
      highlightTimerRef.current = setTimeout(() => setHighlighted(false), 1500);
    },
    [id, regenerateMutation],
  );

  const handleMaterialUpload = useCallback(
    (files: File[]) => {
      const nameToSave = (settingsForm.getValues("name") ?? "").trim() || t("editor.defaultSkillName");
      if (isNew) {
        // Create skill first, then upload and convert
        createMutation.mutate(
          { name: nameToSave },
          {
            onSuccess: (created) => {
              navigate(`/admin/skills/${created.id}/edit`, { replace: true });
              uploadConvertMutation.mutate(
                { id: created.id, files },
                {
                  onSuccess: () => {
                    queryClient.invalidateQueries({
                      queryKey: skillKeys.detail(created.id),
                    });
                  },
                  onError: () => toast.error(t("errors.conversionFailed")),
                },
              );
            },
            onError: () => toast.error(t("errors.saveFailed")),
          },
        );
      } else if (id) {
        uploadConvertMutation.mutate(
          { id, files },
          {
            onSuccess: () => {
              queryClient.invalidateQueries({
                queryKey: skillKeys.detail(id),
              });
            },
            onError: () => toast.error(t("errors.conversionFailed")),
          },
        );
      }
    },
    [isNew, id, settingsForm, createMutation, uploadConvertMutation, navigate, queryClient, t],
  );

  const handleCreateEmpty = useCallback(() => {
    const nameToSave = (settingsForm.getValues("name") ?? "").trim() || t("editor.defaultSkillName");
    createMutation.mutate(
      { name: nameToSave, content: "" },
      {
        onSuccess: (created) => {
          navigate(`/admin/skills/${created.id}/edit`, { replace: true });
        },
        onError: () => toast.error(t("errors.saveFailed")),
      },
    );
  }, [settingsForm, createMutation, navigate, t]);

  const handleRetryConversion = useCallback(() => {
    if (!id) return;
    retryConversionMutation.mutate(id, {
      onError: () => toast.error(t("errors.conversionFailed")),
    });
  }, [id, retryConversionMutation, t]);

  const handleRetryFoundrySync = useCallback(() => {
    if (!id) return;
    retryFoundrySyncMutation.mutate(id, {
      onSuccess: () => toast.success(t("foundry.retrySuccess")),
      onError: (err) =>
        toast.error(t("foundry.retryError", { error: (err as Error).message })),
    });
  }, [id, retryFoundrySyncMutation, t]);

  const handleResourceUpload = useCallback(
    (files: File[], type: "reference" | "script" | "asset") => {
      if (!id) return;
      uploadResourcesMutation.mutate(
        { id, files, resourceType: type },
        {
          onSuccess: () =>
            toast.success(t("editor.filesUploaded")),
          onError: () => toast.error(t("errors.saveFailed")),
        },
      );
    },
    [id, uploadResourcesMutation, t],
  );

  const handleDownloadResource = useCallback(
    async (resource: SkillResource) => {
      if (!id) return;
      try {
        await downloadResource(id, resource.id, resource.filename);
      } catch {
        toast.error(t("errors.loadFailed"));
      }
    },
    [id, t],
  );

  const handleRequestReview = useCallback(async () => {
    if (!id) return;
    try {
      await checkStructureMutation.mutateAsync(id);
      await evaluateQualityMutation.mutateAsync(id);
      toast.success(t("quality.reviewStarted"));
      void refetchEvaluation();
    } catch {
      toast.error(t("errors.loadFailed"));
    }
  }, [id, checkStructureMutation, evaluateQualityMutation, refetchEvaluation, t]);

  const handleToggleDimension = useCallback((name: string) => {
    setExpandedDimensions((prev) => ({
      ...prev,
      [name]: !prev[name],
    }));
  }, []);

  const handleSettingsSave = useCallback(
    (values: SettingsFormValues) => {
      if (!id) return;
      updateMutation.mutate(
        { id, data: values },
        {
          onSuccess: () => {
            toast.success(t("editor.settingsSaved"));
          },
          onError: () => toast.error(t("errors.saveFailed")),
        },
      );
    },
    [id, updateMutation, t],
  );

  // State for auto-evaluation before publish
  const [isAutoEvaluating, setIsAutoEvaluating] = useState(false);

  // ---------------------------------------------------------------------------
  // Derived state
  // ---------------------------------------------------------------------------
  const conversionStatus: ConversionStatus | null =
    (conversionData?.status as ConversionStatus | undefined) ??
    skill?.conversion_status ??
    null;
  const conversionError = conversionData?.error ?? skill?.conversion_error ?? undefined;
  const hasContent = Boolean(skill?.content);
  const isProcessing =
    conversionStatus === "pending" || conversionStatus === "processing";
  const isSaving = updateMutation.isPending || createMutation.isPending;

  // Quality data extraction
  const structurePassed = evaluationData?.structure_check?.passed ?? skill?.structure_check_passed ?? null;
  const qualityScore = evaluationData?.quality?.score ?? skill?.quality_score ?? null;
  const qualityVerdict = evaluationData?.quality?.verdict ?? skill?.quality_verdict ?? null;
  const isStale = evaluationData?.quality?.is_stale ?? false;
  const qualityDetails: QualityEvaluation | null =
    evaluationData?.quality?.details &&
    "dimensions" in evaluationData.quality.details
      ? (evaluationData.quality.details as QualityEvaluation)
      : null;
  const dimensions: QualityDimension[] = qualityDetails?.dimensions ?? [];
  const evaluationStatus: EvaluationStatus | undefined =
    evaluationData?.quality?.evaluation_status;
  const modelUsed: string =
    evaluationData?.quality?.model_used ?? qualityDetails?.model_used ?? "";
  const errorDetail: string =
    evaluationData?.quality?.error_detail ?? qualityDetails?.error_detail ?? "";
  const evaluationCriteria: EvaluationCriterion[] =
    evaluationData?.evaluation_criteria ?? [];
  const isAiUnavailable =
    evaluationStatus === "ai_unavailable" || evaluationStatus === "ai_error";

  // Publish handlers (after derived state so structurePassed is available)
  const handlePublishClick = useCallback(async () => {
    if (!id) return;
    const needsEval = isStale
      || structurePassed === null
      || evaluationData?.quality?.score === null;

    if (needsEval) {
      setIsAutoEvaluating(true);
      try {
        await checkStructureMutation.mutateAsync(id);
        await evaluateQualityMutation.mutateAsync(id);
        const maxAttempts = 20;
        for (let i = 0; i < maxAttempts; i++) {
          await new Promise(r => setTimeout(r, 2000));
          const result = await refetchEvaluation();
          const evalData = result.data;
          if (evalData?.quality?.is_stale === false && evalData?.quality?.score !== null) {
            break;
          }
        }
      } catch {
        toast.error(t("errors.loadFailed"));
        setIsAutoEvaluating(false);
        return;
      }
      setIsAutoEvaluating(false);
    }
    setPublishDialogOpen(true);
  }, [id, isStale, structurePassed, evaluationData, checkStructureMutation, evaluateQualityMutation, refetchEvaluation, t]);

  const handlePublish = useCallback(() => {
    if (!id) return;
    publishMutation.mutate(id, {
      onSuccess: () => {
        toast.success(t("quality.publishSuccess"));
        setPublishDialogOpen(false);
        navigate("/admin/skills");
      },
      onError: () => toast.error(t("errors.publishFailed", { defaultValue: t("errors.saveFailed") })),
    });
  }, [id, publishMutation, navigate, t]);

  const isReviewing =
    checkStructureMutation.isPending || evaluateQualityMutation.isPending;

  // ---------------------------------------------------------------------------
  // Loading state
  // ---------------------------------------------------------------------------
  if (!isNew && isLoading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-3">
          <Skeleton className="h-8 w-32" />
          <Skeleton className="h-8 flex-1" />
        </div>
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-[500px] w-full" />
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------
  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3 min-w-0 flex-1">
          <Button
            variant="ghost"
            size="sm"
            className="shrink-0"
            onClick={() => navigate("/admin/skills")}
          >
            <ArrowLeft className="mr-1 size-4" />
            {t("editor.backToHub")}
          </Button>
          <span className="text-2xl font-semibold truncate px-2 py-1">
            {headerName || t("editor.defaultSkillName")}
          </span>
        </div>

        <div className="flex items-center gap-2">
          {!isNew && skill && (
            <DryRunButton
              skillId={id}
              hasContent={hasContent}
              isNew={isNew}
              skillStatus={skill.status}
              onDryRunCreated={(runId) => {
                setActiveDryRunId(runId);
                setActiveTab("quality");
              }}
            />
          )}
          <Button
            variant="outline"
            onClick={handleSaveDraft}
            disabled={isSaving || (!contentDirty && !settingsForm.formState.isDirty && !isNew)}
          >
            {isSaving ? (
              <RefreshCw className="mr-2 size-4 animate-spin" />
            ) : (
              <Save className="mr-2 size-4" />
            )}
            {t("editor.saveDraft")}
          </Button>
          <Button
            onClick={handlePublishClick}
            disabled={isNew || !skill || isAutoEvaluating}
          >
            {isAutoEvaluating ? (
              <RefreshCw className="mr-2 size-4 animate-spin" />
            ) : (
              <Rocket className="mr-2 size-4" />
            )}
            {isAutoEvaluating
              ? t("quality.evaluating", { defaultValue: "Evaluating..." })
              : t("editor.publishSkill")}
          </Button>
        </div>
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={handleTabChange}>
        <TabsList className="w-full bg-muted/60 border">
          <TabsTrigger
            value="content"
            className="flex-1 data-[state=active]:bg-primary data-[state=active]:text-primary-foreground"
          >
            {t("editor.tabContent")}
          </TabsTrigger>
          <TabsTrigger
            value="resources"
            className="flex-1 data-[state=active]:bg-primary data-[state=active]:text-primary-foreground"
          >
            {t("editor.tabResources")}
          </TabsTrigger>
          <TabsTrigger
            value="quality"
            className="flex-1 data-[state=active]:bg-primary data-[state=active]:text-primary-foreground"
          >
            {t("editor.tabQuality")}
          </TabsTrigger>
          <TabsTrigger
            value="settings"
            className="flex-1 data-[state=active]:bg-primary data-[state=active]:text-primary-foreground"
          >
            {t("editor.tabSettings")}
          </TabsTrigger>
        </TabsList>

        {/* ----- Content Tab ----- */}
        <TabsContent value="content" className="mt-6">
          {/* New skill without content: show upload zone */}
          {(isNew || (!hasContent && !isProcessing && conversionStatus !== "failed")) && (
            <div className="space-y-6">
              <SkillMaterialUploader
                onUpload={handleMaterialUpload}
                isUploading={uploadConvertMutation.isPending}
              />
              {isNew && (
                <div className="text-center">
                  <button
                    type="button"
                    className="text-sm text-primary underline hover:text-primary/80"
                    onClick={handleCreateEmpty}
                  >
                    {t("editor.createEmpty")}
                  </button>
                </div>
              )}
            </div>
          )}

          {/* Converting: show progress */}
          {isProcessing && (
            <ConversionProgress
              status={conversionStatus}
              error={conversionError}
              progress={conversionData?.progress}
              onRetry={handleRetryConversion}
            />
          )}

          {/* Conversion failed: show error */}
          {conversionStatus === "failed" && (
            <ConversionProgress
              status={conversionStatus}
              error={conversionError}
              onRetry={handleRetryConversion}
            />
          )}

          {/* Content exists: show SOP editor */}
          {hasContent && !isProcessing && (
            <SopEditor
              content={sopContent}
              onChange={handleContentChange}
              onAiRegenerate={handleAiRegenerate}
              isRegenerating={regenerateMutation.isPending}
              highlighted={highlighted}
            />
          )}
        </TabsContent>

        {/* ----- Resources Tab ----- */}
        <TabsContent value="resources" className="mt-6 space-y-4">
          {/* Source materials (shown when skill was converted from materials) */}
          {!isNew && skill && skill.source_materials && skill.source_materials.length > 0 && (
            <div className="rounded-lg border border-border bg-muted/30 p-4">
              <h4 className="text-sm font-medium mb-2">
                {t("editor.sourceMaterials")}
              </h4>
              <div className="flex flex-wrap gap-2">
                {skill.source_materials.map((mat) => (
                  <Link
                    key={mat.id}
                    to={`/admin/materials?search=${encodeURIComponent(mat.name)}`}
                    className="inline-flex items-center gap-1.5 rounded-full bg-primary/10 px-3 py-1 text-xs font-medium text-primary hover:bg-primary/20 transition-colors"
                  >
                    <FileText className="size-3" />
                    {mat.name}
                    <ExternalLink className="size-3 opacity-60" />
                  </Link>
                ))}
              </div>
            </div>
          )}

          {!isNew && skill ? (
            <div className="rounded-lg border border-border overflow-hidden">
              {/* Download Package toolbar */}
              <div className="flex items-center justify-between border-b border-border px-4 py-2 bg-muted/30">
                <span className="text-sm font-medium text-muted-foreground">
                  {t("editor.tabResources")}
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    if (!id) return;
                    downloadSkillZip(id, skill.name).catch(() =>
                      toast.error(t("errors.loadFailed")),
                    );
                  }}
                >
                  <Download className="mr-2 size-4" />
                  {t("fileTree.downloadPackage")}
                </Button>
              </div>
              <div className="grid grid-cols-1 gap-0 lg:grid-cols-[280px_1fr]">
              {/* Left: File tree */}
              <div className="border-b lg:border-b-0 lg:border-r border-border bg-muted/30">
                <FileTreeView
                  resources={skill.resources}
                  onSelectFile={setSelectedResource}
                  selectedId={
                    selectedResource === "SKILL.md"
                      ? "__SKILL_MD__"
                      : selectedResource
                        ? (selectedResource as SkillResource).id
                        : undefined
                  }
                  onUpload={handleResourceUpload}
                />
              </div>

              {/* Right: Preview panel */}
              <div className="min-h-[400px]">
                {!selectedResource && (
                  <div className="flex h-full items-center justify-center p-8">
                    <p className="text-sm text-muted-foreground">
                      {t("fileTree.selectFile")}
                    </p>
                  </div>
                )}

                {/* SKILL.md preview — render as raw text to preserve YAML frontmatter */}
                {selectedResource === "SKILL.md" && (
                  <ScrollArea className="h-[500px]">
                    <pre className="p-6 text-sm font-mono leading-relaxed whitespace-pre-wrap overflow-x-auto">
                      {skill.content || ""}
                    </pre>
                  </ScrollArea>
                )}

                {/* Resource file preview */}
                {selectedResource &&
                  selectedResource !== "SKILL.md" &&
                  (() => {
                    const resource = selectedResource as SkillResource;
                    const isScript = resource.resource_type === "script";
                    return (
                      <div className="p-6 space-y-4">
                        <ResourceInfoCard resource={resource} />
                        {isScript && (
                          <pre className="rounded-lg bg-muted/50 p-4 text-sm font-mono overflow-x-auto">
                            {resource.filename}
                          </pre>
                        )}
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleDownloadResource(resource)}
                        >
                          <Download className="mr-2 size-4" />
                          {t("fileTree.download")}
                        </Button>
                      </div>
                    );
                  })()}
              </div>
              </div>
            </div>
          ) : (
            <div className="flex items-center justify-center rounded-lg border bg-muted/50 py-24 text-muted-foreground">
              {t("editor.saveFirstForResources")}
            </div>
          )}
        </TabsContent>

        {/* ----- Quality Tab ----- */}
        <TabsContent value="quality" className="mt-6">
          {isNew ? (
            <div className="flex items-center justify-center rounded-lg border bg-muted/50 py-24 text-muted-foreground">
              {t("editor.saveFirstForResources")}
            </div>
          ) : (
            <div className="space-y-6">
              {/* Request review button when not yet evaluated */}
              {qualityScore === null && !isReviewing && (
                <div className="flex flex-col items-center justify-center gap-4 rounded-lg border bg-muted/50 py-12">
                  <p className="text-sm text-muted-foreground">
                    {t("quality.notEvaluated")}
                  </p>
                  <Button onClick={handleRequestReview}>
                    {t("quality.requestReview")}
                  </Button>
                </div>
              )}

              {/* Reviewing state */}
              {isReviewing && (
                <div className="flex items-center justify-center gap-3 rounded-lg border bg-muted/50 py-12">
                  <RefreshCw className="size-5 animate-spin text-primary" />
                  <span className="text-sm text-muted-foreground">
                    {t("quality.evaluating")}
                  </span>
                </div>
              )}

              {/* AI Unavailable / Error Banner */}
              {isAiUnavailable && !isReviewing && (
                <div
                  className={cn(
                    "flex items-start gap-3 rounded-lg border p-4",
                    evaluationStatus === "ai_unavailable"
                      ? "border-weakness/30 bg-weakness/5"
                      : "border-destructive/30 bg-destructive/5",
                  )}
                >
                  <AlertTriangle
                    className={cn(
                      "mt-0.5 size-5 shrink-0",
                      evaluationStatus === "ai_unavailable"
                        ? "text-weakness"
                        : "text-destructive",
                    )}
                  />
                  <div className="space-y-1">
                    <p
                      className={cn(
                        "text-sm font-medium",
                        evaluationStatus === "ai_unavailable"
                          ? "text-weakness"
                          : "text-destructive",
                      )}
                    >
                      {evaluationStatus === "ai_unavailable"
                        ? t("quality.aiUnavailable")
                        : t("quality.aiError")}
                    </p>
                    <p className="text-sm text-muted-foreground">
                      {evaluationStatus === "ai_unavailable"
                        ? t("quality.aiUnavailableDesc")
                        : t("quality.aiErrorDesc", { error: errorDetail })}
                    </p>
                  </div>
                </div>
              )}

              {/* L1 Structure Check Banner */}
              {structurePassed !== null && (
                <div
                  className={cn(
                    "flex items-start gap-3 rounded-lg border p-4",
                    structurePassed
                      ? "border-strength/30 bg-strength/5"
                      : "border-destructive/30 bg-destructive/5",
                  )}
                >
                  {structurePassed ? (
                    <Check className="mt-0.5 size-5 shrink-0 text-strength" />
                  ) : (
                    <XCircle className="mt-0.5 size-5 shrink-0 text-destructive" />
                  )}
                  <div>
                    <p
                      className={cn(
                        "text-sm font-medium",
                        structurePassed ? "text-strength" : "text-destructive",
                      )}
                    >
                      {structurePassed
                        ? t("quality.l1Pass")
                        : t("quality.l1Fail", {
                            reason: skill?.structure_check_details ?? "",
                          })}
                    </p>
                  </div>
                </div>
              )}

              {/* Stale evaluation warning */}
              {isStale && (
                <div className="flex items-start gap-3 rounded-lg border border-weakness/30 bg-weakness/5 p-4">
                  <AlertTriangle className="mt-0.5 size-5 shrink-0 text-weakness" />
                  <p className="text-sm text-foreground">
                    {t("confirm.staleEvaluation")}
                  </p>
                </div>
              )}

              {/* L2 Radar Chart + Dimension Cards */}
              {dimensions.length > 0 && !isAiUnavailable && (
                <>
                  <QualityRadarChart
                    dimensions={dimensions}
                    overallScore={qualityScore ?? undefined}
                    overallVerdict={qualityVerdict ?? undefined}
                  />

                  {/* Evaluation metadata: model + timestamp */}
                  <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
                    <div className="flex items-center gap-4">
                      {modelUsed && (
                        <span className="inline-flex items-center gap-1">
                          <Cpu className="size-3" />
                          {t("quality.modelUsed")}: {modelUsed}
                        </span>
                      )}
                    </div>
                    {qualityDetails?.evaluated_at && (
                      <span>
                        {t("quality.evaluatedAt")}:{" "}
                        {new Date(qualityDetails.evaluated_at).toLocaleString()}
                      </span>
                    )}
                  </div>

                  <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                    {dimensions.map((dim) => (
                      <QualityScoreCard
                        key={dim.name}
                        dimension={dim}
                        isExpanded={expandedDimensions[dim.name] ?? false}
                        onToggle={() => handleToggleDimension(dim.name)}
                      />
                    ))}
                  </div>
                </>
              )}

              {/* Evaluation Criteria transparency (always visible after first evaluation) */}
              {evaluationCriteria.length > 0 && (
                <EvaluationCriteriaPanel criteria={evaluationCriteria} />
              )}

              {/* Re-run review button when already evaluated */}
              {qualityScore !== null && !isReviewing && (
                <div className="flex justify-center">
                  <Button variant="outline" onClick={handleRequestReview}>
                    <RefreshCw className="mr-2 size-4" />
                    {t("quality.requestReview")}
                  </Button>
                </div>
              )}

              {/* Dry Run Progress -- shown when a dry run is actively running */}
              {activeDryRunId && id && (
                <DryRunProgressComponent
                  skillId={id}
                  runId={activeDryRunId}
                  onCompleted={() => {
                    setActiveDryRunId(null);
                    queryClient.invalidateQueries({
                      queryKey: ["skills", "detail", id, "dry-runs"],
                    });
                  }}
                  onCancel={() => setActiveDryRunId(null)}
                />
              )}

              {/* Dry Run History -- shown below L1/L2 results */}
              {id && !activeDryRunId && (
                <DryRunHistoryList
                  skillId={id}
                  onRunClick={(runId) =>
                    navigate(`/admin/skills/${id}/dry-run/${runId}`)
                  }
                />
              )}
            </div>
          )}
        </TabsContent>

        {/* ----- Settings Tab ----- */}
        <TabsContent value="settings" className="mt-6" forceMount hidden={activeTab !== "settings"}>
          {isNew ? (
            <div className="flex items-center justify-center rounded-lg border bg-muted/50 py-24 text-muted-foreground">
              {t("editor.saveFirstForResources")}
            </div>
          ) : (
            <>
              {skill && (
                <div className="max-w-2xl mb-6">
                  <SkillFoundryStatusSection
                    skill={skill}
                    onRetrySync={handleRetryFoundrySync}
                    retrySyncPending={retryFoundrySyncMutation.isPending}
                  />
                </div>
              )}
              <form
                onSubmit={settingsForm.handleSubmit(handleSettingsSave)}
                className="max-w-2xl space-y-6"
              >
              {/* Name */}
              <div className="space-y-2">
                <Label htmlFor="settings-name">
                  {t("editor.settingsName")} *
                </Label>
                <Input
                  id="settings-name"
                  {...settingsForm.register("name")}
                  placeholder={t("editor.settingsName")}
                />
                {settingsForm.formState.errors.name && (
                  <p className="text-xs text-destructive">
                    {t("editor.settingsNameRequired")}
                  </p>
                )}
              </div>

              {/* Description */}
              <div className="space-y-2">
                <Label htmlFor="settings-description">
                  {t("editor.settingsDescription")}
                </Label>
                <Textarea
                  id="settings-description"
                  {...settingsForm.register("description")}
                  rows={3}
                  placeholder={t("editor.settingsDescription")}
                />
              </div>

              {/* Product */}
              <div className="space-y-2">
                <Label htmlFor="settings-product">
                  {t("editor.settingsProduct")}
                </Label>
                <Input
                  id="settings-product"
                  {...settingsForm.register("product")}
                  placeholder={t("editor.settingsProduct")}
                />
              </div>

              {/* Therapeutic Area */}
              <div className="space-y-2">
                <Label htmlFor="settings-therapeutic-area">
                  {t("editor.settingsTherapeuticArea")}
                </Label>
                <Input
                  id="settings-therapeutic-area"
                  {...settingsForm.register("therapeutic_area")}
                  placeholder={t("editor.settingsTherapeuticArea")}
                />
              </div>

              {/* Tags */}
              <div className="space-y-2">
                <Label htmlFor="settings-tags">
                  {t("editor.settingsTags")}
                </Label>
                <Input
                  id="settings-tags"
                  {...settingsForm.register("tags")}
                  placeholder={t("editor.settingsTagsHint")}
                />
                <p className="text-xs text-muted-foreground">
                  {t("editor.settingsTagsHint")}
                </p>
              </div>

              {/* Compatibility */}
              <div className="space-y-2">
                <Label htmlFor="settings-compatibility">
                  {t("editor.settingsCompatibility")}
                </Label>
                <Input
                  id="settings-compatibility"
                  {...settingsForm.register("compatibility")}
                  placeholder={t("editor.settingsCompatibilityHint")}
                />
                <p className="text-xs text-muted-foreground">
                  {t("editor.settingsCompatibilityHint")}
                </p>
              </div>

              {/* Save button */}
              <div className="flex justify-end">
                <Button
                  type="submit"
                  disabled={updateMutation.isPending}
                >
                  {updateMutation.isPending ? (
                    <RefreshCw className="mr-2 size-4 animate-spin" />
                  ) : (
                    <Save className="mr-2 size-4" />
                  )}
                  {t("editor.saveDraft")}
                </Button>
              </div>
              </form>
            </>
          )}
        </TabsContent>
      </Tabs>

      {/* Publish Gate Dialog */}
      {skill && (
        <PublishGateDialog
          open={publishDialogOpen}
          onOpenChange={setPublishDialogOpen}
          skill={skill}
          evaluation={qualityDetails}
          structurePassed={structurePassed}
          isStale={isStale}
          onPublish={handlePublish}
          onCancel={() => setPublishDialogOpen(false)}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Evaluation criteria transparency sub-component
// ---------------------------------------------------------------------------

const DIMENSION_I18N_MAP: Record<string, string> = {
  sop_completeness: "sopCompleteness",
  assessment_coverage: "assessmentCoverage",
  knowledge_accuracy: "knowledgeAccuracy",
  difficulty_calibration: "difficultyBalance",
  conversation_logic: "dialogLogic",
  executability: "executability",
};

function EvaluationCriteriaPanel({
  criteria,
}: {
  criteria: EvaluationCriterion[];
}) {
  const { t } = useTranslation("skill");
  const [open, setOpen] = useState(false);

  return (
    <div className="rounded-lg border border-border bg-card">
      <button
        type="button"
        className="flex w-full items-center justify-between gap-3 p-4 text-left hover:bg-muted/50 transition-colors"
        onClick={() => setOpen((prev) => !prev)}
        aria-expanded={open}
      >
        <div className="flex items-center gap-2">
          <Info className="size-4 text-primary" />
          <span className="text-sm font-medium text-foreground">
            {t("quality.criteriaTitle")}
          </span>
        </div>
        <ChevronDown
          className={cn(
            "size-4 shrink-0 text-muted-foreground transition-transform",
            open && "rotate-180",
          )}
        />
      </button>
      {open && (
        <div className="border-t border-border px-4 py-3 space-y-3">
          <p className="text-sm text-muted-foreground">
            {t("quality.criteriaDescription")}
          </p>
          <div className="space-y-2">
            {criteria.map((c) => {
              const i18nKey = DIMENSION_I18N_MAP[c.name] ?? c.name;
              const label = t(`quality.dimensions.${i18nKey}`, {
                defaultValue: c.name,
              });
              return (
                <div key={c.name} className="space-y-0.5">
                  <p className="text-sm font-medium text-foreground">
                    {label}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {c.description}
                  </p>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Resource info sub-component
// ---------------------------------------------------------------------------

function ResourceInfoCard({ resource }: { resource: SkillResource }) {
  const { t } = useTranslation("skill");

  function formatSize(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  function getIcon(filename: string) {
    const ext = filename.split(".").pop()?.toLowerCase() ?? "";
    if (["py", "js", "ts", "sh", "json"].includes(ext)) return FileCode;
    if (["md", "txt", "pdf", "docx", "doc"].includes(ext)) return FileText;
    return FileIcon;
  }

  const Icon = getIcon(resource.filename);

  return (
    <div className="flex items-start gap-4 rounded-lg border border-border bg-card p-4">
      <Icon className="mt-0.5 size-8 text-muted-foreground" />
      <div className="space-y-1">
        <p className="font-medium text-foreground">{resource.filename}</p>
        <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
          <span>{resource.content_type}</span>
          <span>{formatSize(resource.file_size)}</span>
          <span>
            {t("fileTree.type")}: {resource.resource_type}
          </span>
          <span>
            {new Date(resource.created_at).toLocaleDateString()}
          </span>
        </div>
      </div>
    </div>
  );
}
