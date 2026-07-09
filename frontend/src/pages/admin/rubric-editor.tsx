import { useEffect, useRef } from "react";
import { useParams, useNavigate, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useForm, useFieldArray, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { toast } from "sonner";
import { ArrowLeft, Save, Trash2, Plus, RefreshCw, Sparkles } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Slider } from "@/components/ui/slider";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
import {
  createDefaultRubricDimension,
  toRubricDimensionFormValues,
  toRubricDimensions,
  type RubricDimensionFormValue,
} from "@/lib/rubric-form";
import {
  useRubric,
  useCreateRubric,
  useUpdateRubric,
  useDefaultPromptTemplate,
  useDefaultRubricTemplate,
} from "@/hooks/use-rubrics";
import { CuStatusSection } from "@/components/admin/cu-status-section";
import type { PromptOptimizerLocationState } from "./prompt-optimizer";
import type { RubricCreate, RubricUpdate } from "@/types/rubric";

const RUBRIC_PROMPT_OPTIMIZER_RESULT_KEY = "promptOptimizer:rubric:promptTemplate";

const dimensionSchema = z.object({
  name: z.string().min(1, "Dimension name is required"),
  weight: z.number().min(0).max(100),
  criteria: z.string(),
  max_score: z.number().min(1),
});

const rubricSchema = z.object({
  name: z.string().min(1, "Name is required"),
  description: z.string().optional(),
  scenario_type: z.string().optional(),
  is_default: z.boolean().optional(),
  dimensions: z.array(dimensionSchema).min(1, "At least one dimension required"),
  prompt_template: z.string().optional(),
  content_weight: z.number().min(0).max(100),
});

type RubricFormValues = Omit<z.infer<typeof rubricSchema>, "dimensions"> & {
  dimensions: RubricDimensionFormValue[];
};

export default function RubricEditorPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const { t } = useTranslation(["admin", "common"]);
  const isNew = !id;

  const { data: rubric, isLoading: rubricLoading } = useRubric(id);
  const { data: defaultPromptTemplate } = useDefaultPromptTemplate();
  const { data: defaultRubricTemplate } = useDefaultRubricTemplate();
  const createMutation = useCreateRubric();
  const updateMutation = useUpdateRubric();
  const defaultPrompt =
    defaultRubricTemplate?.prompt_template ?? defaultPromptTemplate?.prompt_template ?? "";
  const defaultRubricApplied = useRef(false);

  const form = useForm<RubricFormValues>({
    resolver: zodResolver(rubricSchema),
    defaultValues: {
      name: "",
      description: "",
      scenario_type: "f2f",
      is_default: false,
      dimensions: [createDefaultRubricDimension()],
      prompt_template: "",
      content_weight: 60,
    },
  });

  const { fields, append, remove } = useFieldArray({
    control: form.control,
    name: "dimensions",
  });

  const watchedDimensions = form.watch("dimensions") ?? [];
  const contentWeight = form.watch("content_weight") ?? 0;
  const weightSum = watchedDimensions.reduce(
    (sum, d) => sum + (d.weight || 0),
    0,
  );
  const isWeightValid = weightSum === 100;

  useEffect(() => {
    if (rubric) {
      form.reset({
        name: rubric.name,
        description: rubric.description ?? "",
        scenario_type: rubric.scenario_type ?? "f2f",
        is_default: rubric.is_default,
        dimensions: toRubricDimensionFormValues(rubric.dimensions),
        prompt_template: rubric.prompt_template || defaultPrompt,
        content_weight: rubric.content_weight ?? 60,
      });
    }
  }, [rubric, defaultPrompt, form]);

  useEffect(() => {
    if (isNew && defaultRubricTemplate && !defaultRubricApplied.current) {
      defaultRubricApplied.current = true;
      form.reset({
        name: defaultRubricTemplate.name,
        description: defaultRubricTemplate.description,
        scenario_type: defaultRubricTemplate.scenario_type,
        is_default: defaultRubricTemplate.is_default,
        dimensions: toRubricDimensionFormValues(defaultRubricTemplate.dimensions),
        prompt_template: defaultRubricTemplate.prompt_template,
        content_weight: defaultRubricTemplate.content_weight,
      });
    } else if (isNew && defaultPrompt && !form.getValues("prompt_template")) {
      form.setValue("prompt_template", defaultPrompt);
    }
  }, [isNew, defaultRubricTemplate, defaultPrompt, form]);

  useEffect(() => {
    if (!isNew && !rubric) return;
    const optimizedText = sessionStorage.getItem(RUBRIC_PROMPT_OPTIMIZER_RESULT_KEY);
    if (!optimizedText) return;
    sessionStorage.removeItem(RUBRIC_PROMPT_OPTIMIZER_RESULT_KEY);
    defaultRubricApplied.current = true;
    form.setValue("prompt_template", optimizedText, { shouldDirty: true });
  }, [form, isNew, rubric]);

  const openPromptOptimizer = () => {
    const state: PromptOptimizerLocationState = {
      source: "text",
      returnTo: `${location.pathname}${location.search}`,
      resultStorageKey: RUBRIC_PROMPT_OPTIMIZER_RESULT_KEY,
      content: form.getValues("prompt_template") ?? "",
      title: t("admin:rubrics.promptTemplate"),
    };
    navigate("/admin/prompt-optimizer", { state });
  };

  const handleSubmit = (values: RubricFormValues) => {
    const payload: RubricCreate = {
      name: values.name,
      description: values.description,
      scenario_type: values.scenario_type,
      is_default: values.is_default,
      dimensions: toRubricDimensions(values.dimensions),
      prompt_template: values.prompt_template ?? "",
      content_weight: values.content_weight,
      voice_weight: 100 - values.content_weight,
    };

    if (isNew) {
      createMutation.mutate(payload, {
        onSuccess: () => {
          toast.success(t("admin:rubrics.saved"));
          navigate("/admin/scoring-rubrics");
        },
        onError: () => toast.error(t("admin:errors.rubricSaveFailed")),
      });
    } else if (id) {
      updateMutation.mutate(
        { id, data: payload as RubricUpdate },
        {
          onSuccess: () => {
            toast.success(t("admin:rubrics.saved"));
            navigate("/admin/scoring-rubrics");
          },
          onError: () => toast.error(t("admin:errors.rubricSaveFailed")),
        },
      );
    }
  };

  if (!isNew && rubricLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="size-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => navigate("/admin/scoring-rubrics")}
          >
            <ArrowLeft className="size-5" />
          </Button>
          <div>
            <h1 className="text-2xl font-medium">
              {isNew
                ? t("admin:rubrics.createButton")
                : `${t("admin:rubrics.editTitle", { name: rubric?.name ?? "" })}`}
            </h1>
          </div>
        </div>
        <Button
          onClick={form.handleSubmit(handleSubmit)}
          disabled={!isWeightValid || createMutation.isPending || updateMutation.isPending}
        >
          <Save className="size-4 mr-2" />
          {createMutation.isPending || updateMutation.isPending
            ? t("common:saving")
            : t("admin:rubrics.save")}
        </Button>
      </div>

      {/* Basic Info Card */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base font-semibold">
            {t("admin:rubrics.basicInfo")}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Name */}
          <div className="grid gap-2">
            <Label>{t("admin:rubrics.name")} *</Label>
            <Input {...form.register("name")} />
            {form.formState.errors.name && (
              <p className="text-sm text-destructive">
                {form.formState.errors.name.message}
              </p>
            )}
          </div>

          {/* Description */}
          <div className="grid gap-2">
            <Label>{t("admin:rubrics.description")}</Label>
            <Textarea rows={2} {...form.register("description")} />
          </div>

          {/* Scenario Type + Default */}
          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label>{t("admin:rubrics.scenarioType")}</Label>
              <Controller
                control={form.control}
                name="scenario_type"
                render={({ field }) => (
                  <Select
                    value={field.value ?? "f2f"}
                    onValueChange={field.onChange}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="f2f">
                        {t("admin:rubrics.f2f")}
                      </SelectItem>
                      <SelectItem value="conference">
                        {t("admin:rubrics.conference")}
                      </SelectItem>
                    </SelectContent>
                  </Select>
                )}
              />
            </div>
            <div className="grid gap-2">
              <Label>{t("admin:rubrics.isDefault")}</Label>
              <Controller
                control={form.control}
                name="is_default"
                render={({ field }) => (
                  <Switch
                    checked={field.value ?? false}
                    onCheckedChange={field.onChange}
                  />
                )}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Prompt Template Card */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base font-semibold">
            {t("admin:rubrics.promptTemplate")}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid gap-2">
            <div className="flex items-center justify-between gap-3">
              <Label>{t("admin:rubrics.promptTemplate")}</Label>
              <div className="flex items-center gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={openPromptOptimizer}
                  data-testid="optimize-prompt"
                >
                  <Sparkles className="mr-2 size-3.5" />
                  {t("prompts:actions.optimize", { defaultValue: "AI \u4f18\u5316" })}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={!defaultPrompt}
                  onClick={() =>
                    form.setValue("prompt_template", defaultPrompt, {
                      shouldDirty: true,
                    })
                  }
                >
                  <RefreshCw className="mr-2 size-3.5" />
                  {t("admin:rubrics.useDefaultPromptTemplate")}
                </Button>
              </div>
            </div>
            <Textarea
              rows={10}
              {...form.register("prompt_template")}
              placeholder={t("admin:rubrics.promptTemplateHint")}
            />
            <p className="text-xs text-muted-foreground">
              {t("admin:rubrics.promptTemplateHint")}
            </p>
            {!isNew && rubric && (
              <p className="text-xs text-muted-foreground">
                {t("admin:rubrics.promptVersion")}: {rubric.prompt_version ?? 1} · {t("admin:rubrics.updatedAt")}: {new Date(rubric.updated_at).toLocaleString()}
              </p>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Dimensions Card */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base font-semibold flex items-center justify-between">
            <span>{t("admin:rubrics.dimensions")}</span>
            <span
              className={cn(
                "text-sm font-medium",
                isWeightValid ? "text-green-600" : "text-red-600",
              )}
            >
              {t("admin:rubrics.weightSum")}: {weightSum}/100
            </span>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {!isWeightValid && (
            <p className="text-sm text-destructive">
              {t("admin:rubrics.weightSumError")}
            </p>
          )}

          {fields.map((field, index) => (
            <div
              key={field.id}
              className="rounded-md border p-3 space-y-3"
            >
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">
                  {t("admin:rubrics.dimensionName")} {index + 1}
                </span>
                {fields.length > 1 && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="size-7 text-destructive"
                    onClick={() => remove(index)}
                  >
                    <Trash2 className="size-3.5" />
                  </Button>
                )}
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="grid gap-1">
                  <Label className="text-xs">
                    {t("admin:rubrics.dimensionName")}
                  </Label>
                  <Input
                    {...form.register(`dimensions.${index}.name`)}
                    placeholder="e.g. Key Message Delivery"
                  />
                </div>
                <div className="grid gap-1">
                  <Label className="text-xs">
                    {t("admin:rubrics.weight")} ({watchedDimensions[index]?.weight ?? 0}%)
                  </Label>
                  <Controller
                    control={form.control}
                    name={`dimensions.${index}.weight`}
                    render={({ field: sliderField }) => (
                      <Slider
                        min={0}
                        max={100}
                        step={5}
                        value={[sliderField.value]}
                        onValueChange={(vals) => {
                          const val = vals[0];
                          if (val !== undefined) {
                            sliderField.onChange(val);
                          }
                        }}
                      />
                    )}
                  />
                </div>
              </div>

              <div className="grid gap-1">
                <Label className="text-xs">{t("admin:rubrics.criteria")}</Label>
                <Input
                  {...form.register(`dimensions.${index}.criteria`)}
                  placeholder="criterion 1, criterion 2, ..."
                />
              </div>
            </div>
          ))}

          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() =>
              append({ ...createDefaultRubricDimension(), weight: 0 })
            }
          >
            <Plus className="mr-1 size-4" />
            {t("admin:rubrics.addDimension")}
          </Button>
        </CardContent>
      </Card>

      {/* Category Weights Card */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base font-semibold">
            {t("admin:rubrics.categoryWeights")}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label className="text-sm">{t("admin:rubrics.contentWeight")}</Label>
              <span className="text-sm text-muted-foreground">{contentWeight}%</span>
            </div>
            <Controller
              name="content_weight"
              control={form.control}
              render={({ field }) => (
                <Slider
                  value={[field.value]}
                  onValueChange={(val) => {
                    const v = val[0];
                    if (v !== undefined) {
                      field.onChange(v);
                    }
                  }}
                  min={0}
                  max={100}
                  step={5}
                />
              )}
            />
            <div className="flex items-center justify-between">
              <Label className="text-sm">{t("admin:rubrics.voiceWeight")}</Label>
              <span className="text-sm text-muted-foreground">{100 - contentWeight}%</span>
            </div>
            <p className="text-xs text-muted-foreground">{t("admin:rubrics.voiceWeightHint")}</p>
          </div>
        </CardContent>
      </Card>

      {/* CU Analyzers Card (only in edit mode) */}
      {!isNew && <CuStatusSection rubricId={id} />}
    </div>
  );
}
