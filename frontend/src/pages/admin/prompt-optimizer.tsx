import { useMemo, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { ArrowLeft, Check, Sparkles } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  useAdoptRun,
  useOptimizePrompt,
  useOptimizeText,
  usePrompt,
} from "@/hooks/use-prompts";
import type { OptimizeMode } from "@/types/prompt";

export type PromptOptimizerLocationState =
  | {
      source: "registry";
      returnTo: string;
      originalContent?: string;
      title?: string;
    }
  | {
      source: "text";
      returnTo: string;
      resultStorageKey: string;
      content: string;
      title?: string;
    };

function isOptimizerState(value: unknown): value is PromptOptimizerLocationState {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<PromptOptimizerLocationState>;
  if (candidate.source === "registry") {
    return typeof candidate.returnTo === "string";
  }
  if (candidate.source === "text") {
    return (
      typeof candidate.returnTo === "string" &&
      typeof candidate.resultStorageKey === "string" &&
      typeof candidate.content === "string"
    );
  }
  return false;
}

export default function PromptOptimizerPage() {
  const { key } = useParams<{ key: string }>();
  const location = useLocation();
  const navigate = useNavigate();
  const { t } = useTranslation("prompts");
  const state = isOptimizerState(location.state) ? location.state : null;

  const isRegistryPrompt = !!key;
  const { data: prompt, isError } = usePrompt(isRegistryPrompt ? key : undefined);
  const optimizePromptMutation = useOptimizePrompt(key);
  const adoptRunMutation = useAdoptRun(key);
  const optimizeTextMutation = useOptimizeText();

  const [mode, setMode] = useState<OptimizeMode>("system");
  const [requirements, setRequirements] = useState("");
  const [optimized, setOptimized] = useState<{ runId?: string; text: string } | null>(null);

  const returnTo = state?.returnTo ?? (key ? `/admin/prompts/${key}` : "/admin/prompts");
  const originalContent = useMemo(() => {
    if (state?.source === "text") return state.content;
    return prompt?.active_version?.content ?? state?.originalContent ?? "";
  }, [prompt, state]);
  const title = state?.title ?? prompt?.name ?? key ?? t("optimize.title");
  const canRun = !!originalContent.trim() && (mode !== "iterate" || !!requirements.trim());

  const handleBack = () => navigate(returnTo);

  const handleOptimize = () => {
    const payload = {
      mode,
      requirements: mode === "iterate" ? requirements : null,
    };

    if (isRegistryPrompt) {
      optimizePromptMutation.mutate(payload, {
        onSuccess: (res) => setOptimized({ runId: res.run_id, text: res.optimized_prompt }),
        onError: () => toast.error(t("optimize.failed")),
      });
      return;
    }

    optimizeTextMutation.mutate(
      {
        prompt: originalContent,
        ...payload,
      },
      {
        onSuccess: (res) => setOptimized({ text: res.optimized_prompt }),
        onError: () => toast.error(t("optimize.failed")),
      },
    );
  };

  const handleAdopt = () => {
    if (!optimized) return;

    if (isRegistryPrompt && optimized.runId) {
      adoptRunMutation.mutate(
        { run_id: optimized.runId },
        {
          onSuccess: () => {
            toast.success(t("optimize.adopted"));
            navigate(returnTo);
          },
        },
      );
      return;
    }

    if (state?.source === "text") {
      sessionStorage.setItem(state.resultStorageKey, optimized.text);
      toast.success(t("optimize.adoptedToEditor"));
      navigate(returnTo);
    }
  };

  if (isRegistryPrompt && isError) {
    return <div className="p-6 text-sm text-danger-600">{t("editor.loadError")}</div>;
  }

  if (!isRegistryPrompt && state?.source !== "text") {
    return (
      <div className="space-y-4">
        <Button variant="ghost" onClick={() => navigate("/admin/prompts")}>
          <ArrowLeft className="size-4" />
          {t("optimize.back")}
        </Button>
        <Card>
          <CardContent className="py-10 text-sm text-muted-foreground">
            {t("optimize.missingState")}
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6" data-testid="prompt-optimizer-page">
      <div className="flex items-center justify-between gap-4">
        <Button variant="ghost" onClick={handleBack} data-testid="optimizer-back">
          <ArrowLeft className="size-4" />
          {t("optimize.back")}
        </Button>
        <Badge variant="outline">{t("optimize.pageBadge")}</Badge>
      </div>

      <div>
        <h1 className="text-2xl font-medium text-foreground">{t("optimize.title")}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{title}</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{t("optimize.settings")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-2 md:grid-cols-[240px_1fr]">
            <div className="space-y-2">
              <Label>{t("optimize.mode")}</Label>
              <Select value={mode} onValueChange={(value) => setMode(value as OptimizeMode)}>
                <SelectTrigger data-testid="optimize-mode">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="system">{t("optimize.modeSystem")}</SelectItem>
                  <SelectItem value="user">{t("optimize.modeUser")}</SelectItem>
                  <SelectItem value="iterate">{t("optimize.modeIterate")}</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="optimize-requirements">{t("optimize.requirements")}</Label>
              <Textarea
                id="optimize-requirements"
                value={requirements}
                onChange={(event) => setRequirements(event.target.value)}
                placeholder={t("optimize.requirementsPlaceholder")}
                rows={3}
                disabled={mode !== "iterate"}
                data-testid="optimize-requirements"
              />
            </div>
          </div>

          <div className="flex justify-end">
            <Button
              onClick={handleOptimize}
              disabled={
                !canRun || optimizePromptMutation.isPending || optimizeTextMutation.isPending
              }
              data-testid="run-optimize"
            >
              <Sparkles className="size-4" />
              {optimizePromptMutation.isPending || optimizeTextMutation.isPending
                ? t("optimize.running")
                : t("optimize.run")}
            </Button>
          </div>
        </CardContent>
      </Card>

      <div
        className="grid gap-4 lg:grid-cols-2"
        data-testid={optimized ? "optimize-diff" : undefined}
      >
        <Card>
          <CardHeader>
            <CardTitle>{t("optimize.original")}</CardTitle>
          </CardHeader>
          <CardContent>
            <pre className="max-h-[58vh] overflow-auto whitespace-pre-wrap rounded-md border bg-muted/40 p-4 font-mono text-xs">
              {originalContent || t("optimize.noContent")}
            </pre>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between gap-3">
            <CardTitle>{t("optimize.optimized")}</CardTitle>
            {optimized && (
              <Button
                onClick={handleAdopt}
                disabled={adoptRunMutation.isPending}
                data-testid="adopt-run"
              >
                <Check className="size-4" />
                {isRegistryPrompt ? t("optimize.adopt") : t("optimize.adoptToEditor")}
              </Button>
            )}
          </CardHeader>
          <CardContent>
            <pre
              className="min-h-64 max-h-[58vh] overflow-auto whitespace-pre-wrap rounded-md border bg-success-50 p-4 font-mono text-xs"
              data-testid="optimized-text"
            >
              {optimized?.text ?? t("optimize.emptyOptimized")}
            </pre>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}