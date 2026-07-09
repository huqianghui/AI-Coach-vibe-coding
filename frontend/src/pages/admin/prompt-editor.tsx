import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { ArrowLeft, Eye, RotateCcw, Save, Sparkles } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
import {
  useActivateVersion,
  usePrompt,
  usePromptVersions,
  useSaveVersion,
  useUpdatePromptMeta,
} from "@/hooks/use-prompts";
import type { PromptOptimizerLocationState } from "./prompt-optimizer";
import type { PromptVersion } from "@/types/prompt";

const CATEGORY_OPTIONS = [
  "general",
  "conversation",
  "conference",
  "scoring",
  "skill",
  "dry_run",
] as const;

export default function PromptEditorPage() {
  const { key } = useParams<{ key: string }>();
  const navigate = useNavigate();
  const { t } = useTranslation("prompts");

  const { data: prompt, isError } = usePrompt(key);
  const { data: versions } = usePromptVersions(key);
  const saveMutation = useSaveVersion(key);
  const activateMutation = useActivateVersion(key);
  const metaMutation = useUpdatePromptMeta(key);

  const [content, setContent] = useState("");
  const [note, setNote] = useState("");
  const [meta, setMeta] = useState({
    name: "",
    category: "general",
    isSystem: false,
    description: "",
    variables: "",
  });
  const [viewVersion, setViewVersion] = useState<PromptVersion | null>(null);

  useEffect(() => {
    if (prompt?.active_version) {
      setContent(prompt.active_version.content);
    }
  }, [prompt]);

  useEffect(() => {
    if (prompt) {
      setMeta({
        name: prompt.name,
        category: prompt.category,
        isSystem: prompt.is_system,
        description: prompt.description ?? "",
        variables: (prompt.variables ?? []).join(", "),
      });
    }
  }, [prompt]);

  if (isError) {
    return <div className="p-6 text-sm text-danger-600">{t("editor.loadError")}</div>;
  }

  const handleSave = () => {
    saveMutation.mutate(
      { content, note },
      {
        onSuccess: () => {
          toast.success(t("editor.saved"));
          setNote("");
        },
      },
    );
  };

  const handleSaveMeta = () => {
    const variables = meta.variables
      .split(",")
      .map((v) => v.trim())
      .filter(Boolean);
    metaMutation.mutate(
      {
        name: meta.name.trim(),
        category: meta.category.trim() || "general",
        description: meta.description,
        variables,
        is_system: meta.isSystem,
      },
      {
        onSuccess: () => toast.success(t("editor.metaSaved")),
        onError: () => toast.error(t("editor.metaError")),
      },
    );
  };

  const handleRollback = (versionNo: number) => {
    activateMutation.mutate(versionNo, {
      onSuccess: () => toast.success(t("editor.rolledBack")),
    });
  };

  const openOptimize = () => {
    if (!key) return;
    const state: PromptOptimizerLocationState = {
      source: "registry",
      returnTo: `/admin/prompts/${key}`,
      originalContent: prompt?.active_version?.content ?? content,
      title: prompt?.name ?? key,
    };
    navigate(`/admin/prompts/${key}/optimize`, { state });
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <Button variant="ghost" onClick={() => navigate("/admin/prompts")}>
          <ArrowLeft className="size-4" />
          {t("editor.back")}
        </Button>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={openOptimize} data-testid="optimize-open">
            <Sparkles className="size-4" />
            {t("editor.optimize")}
          </Button>
          <Button onClick={handleSave} disabled={saveMutation.isPending} data-testid="save-version">
            <Save className="size-4" />
            {t("editor.save")}
          </Button>
        </div>
      </div>

      <div>
        <h1 className="text-2xl font-medium text-foreground">{prompt?.name ?? key}</h1>
        <p className="mt-1 font-mono text-xs text-muted-foreground">{key}</p>
      </div>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>{t("editor.basicInfo")}</CardTitle>
          <Button
            size="sm"
            onClick={handleSaveMeta}
            disabled={metaMutation.isPending}
            data-testid="save-meta"
          >
            <Save className="size-4" />
            {t("editor.saveMeta")}
          </Button>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label htmlFor="meta-name">{t("create.name")}</Label>
              <Input
                id="meta-name"
                data-testid="meta-name"
                value={meta.name}
                onChange={(e) => setMeta((m) => ({ ...m, name: e.target.value }))}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="meta-category">{t("create.category")}</Label>
              <Select
                value={meta.category}
                onValueChange={(value) => setMeta((m) => ({ ...m, category: value }))}
              >
                <SelectTrigger id="meta-category" data-testid="meta-category">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {CATEGORY_OPTIONS.map((c) => (
                    <SelectItem key={c} value={c} data-testid={`meta-category-${c}`}>
                      {t(`create.categoryOptions.${c}`)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label htmlFor="meta-is-system">{t("create.isSystem")}</Label>
              <Select
                value={meta.isSystem ? "true" : "false"}
                onValueChange={(value) =>
                  setMeta((m) => ({ ...m, isSystem: value === "true" }))
                }
              >
                <SelectTrigger id="meta-is-system" data-testid="meta-is-system">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="false" data-testid="meta-is-system-false">
                    {t("create.isSystemNo")}
                  </SelectItem>
                  <SelectItem value="true" data-testid="meta-is-system-true">
                    {t("create.isSystemYes")}
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="meta-description">{t("create.descriptionField")}</Label>
              <Input
                id="meta-description"
                data-testid="meta-description"
                value={meta.description}
                onChange={(e) => setMeta((m) => ({ ...m, description: e.target.value }))}
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="meta-variables">{t("create.variables")}</Label>
            <Textarea
              id="meta-variables"
              data-testid="meta-variables"
              rows={2}
              value={meta.variables}
              placeholder={t("create.variablesPlaceholder")}
              onChange={(e) => setMeta((m) => ({ ...m, variables: e.target.value }))}
            />
            {prompt?.variables && prompt.variables.length > 0 && (
              <div className="flex flex-wrap gap-2 pt-1">
                {prompt.variables.map((v) => (
                  <Badge key={v} variant="secondary" className="font-mono">
                    {`{{${v}}}`}
                  </Badge>
                ))}
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t("editor.content")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <Textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            rows={14}
            className="font-mono text-sm"
            data-testid="prompt-content"
          />
          <div className="space-y-2">
            <Label htmlFor="version-note">{t("editor.note")}</Label>
            <Input
              id="version-note"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder={t("editor.notePlaceholder")}
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t("editor.versionHistory")}</CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="space-y-2" data-testid="version-history">
            {(versions ?? []).map((version) => (
              <li
                key={version.id}
                className="flex items-center justify-between rounded-md border px-4 py-3"
              >
                <div className="flex items-center gap-3">
                  <span className="font-medium">
                    {t("editor.versionLabel", { no: version.version_no })}
                  </span>
                  <Badge variant="outline">{version.source}</Badge>
                  {version.is_active && (
                    <Badge className={cn("bg-success-600")}>{t("editor.active")}</Badge>
                  )}
                  <span className="text-xs text-muted-foreground">
                    {new Date(version.created_at).toLocaleString()}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setViewVersion(version)}
                    data-testid={`version-view-${version.version_no}`}
                  >
                    <Eye className="size-4" />
                    {t("editor.viewContent")}
                  </Button>
                  {!version.is_active && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleRollback(version.version_no)}
                      data-testid={`rollback-${version.version_no}`}
                    >
                      <RotateCcw className="size-4" />
                      {t("editor.rollback")}
                    </Button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>

      <Dialog open={viewVersion !== null} onOpenChange={(open) => !open && setViewVersion(null)}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>
              {t("editor.versionContentTitle", { no: viewVersion?.version_no })}
            </DialogTitle>
            <DialogDescription>
              {`${t("editor.source")}: ${viewVersion?.source ?? ""}`}
              {viewVersion?.note ? ` · ${viewVersion.note}` : ""}
            </DialogDescription>
          </DialogHeader>

          <pre
            className="max-h-[60vh] overflow-auto whitespace-pre-wrap rounded-md border bg-muted/30 p-4 font-mono text-xs"
            data-testid="version-view-content"
          >
            {viewVersion?.content}
          </pre>

          <DialogFooter>
            <Button variant="outline" onClick={() => setViewVersion(null)}>
              {t("editor.close")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
