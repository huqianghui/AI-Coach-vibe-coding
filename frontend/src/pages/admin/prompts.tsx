import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { Plus } from "lucide-react";
import { AxiosError } from "axios";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
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
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useCreatePrompt, usePrompts } from "@/hooks/use-prompts";
import type { PromptSummary } from "@/types/prompt";

const CATEGORY_OPTIONS = [
  "general",
  "conversation",
  "conference",
  "scoring",
  "skill",
  "dry_run",
] as const;

function formatDate(value: string | null, never: string): string {
  if (!value) return never;
  return new Date(value).toLocaleString();
}

export default function PromptsPage() {
  const { t } = useTranslation("prompts");
  const navigate = useNavigate();
  const { data } = usePrompts();
  const createMutation = useCreatePrompt();

  const prompts = useMemo<PromptSummary[]>(() => data ?? [], [data]);

  const [createOpen, setCreateOpen] = useState(false);
  const [form, setForm] = useState({
    key: "",
    name: "",
    category: "general",
    isSystem: false,
    description: "",
    variables: "",
    content: "",
  });

  function resetForm() {
    setForm({
      key: "",
      name: "",
      category: "general",
      isSystem: false,
      description: "",
      variables: "",
      content: "",
    });
  }

  async function handleCreate() {
    const variables = form.variables
      .split(",")
      .map((v) => v.trim())
      .filter(Boolean);
    try {
      const created = await createMutation.mutateAsync({
        key: form.key.trim(),
        name: form.name.trim(),
        content: form.content,
        category: form.category.trim() || "general",
        description: form.description,
        variables,
        is_system: form.isSystem,
      });
      toast.success(t("create.success"));
      setCreateOpen(false);
      resetForm();
      navigate(`/admin/prompts/${created.key}`);
    } catch (error) {
      const status = error instanceof AxiosError ? error.response?.status : undefined;
      toast.error(status === 409 ? t("create.errorDuplicate") : t("create.error"));
    }
  }

  const canSubmit = form.key.trim() !== "" && form.name.trim() !== "" && form.content !== "";

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-medium text-foreground">{t("list.title")}</h1>
          <p className="mt-1 text-sm text-muted-foreground">{t("list.description")}</p>
        </div>
        <Button data-testid="prompt-create-open" onClick={() => setCreateOpen(true)}>
          <Plus className="mr-2 h-4 w-4" />
          {t("list.create")}
        </Button>
      </div>

      <Card>
        <CardContent className="p-0">
          <table className="w-full text-sm" data-testid="prompts-table">
            <thead>
              <tr className="border-b text-left text-muted-foreground">
                <th className="px-4 py-3 font-medium">{t("list.columnKey")}</th>
                <th className="px-4 py-3 font-medium">{t("list.columnName")}</th>
                <th className="px-4 py-3 font-medium">{t("list.columnCategory")}</th>
                <th className="px-4 py-3 font-medium">{t("list.columnActiveVersion")}</th>
                <th className="px-4 py-3 font-medium">{t("list.columnLastOptimized")}</th>
              </tr>
            </thead>
            <tbody>
              {prompts.length === 0 ? (
                <tr>
                  <td className="px-4 py-6 text-center text-muted-foreground" colSpan={5}>
                    {t("list.empty")}
                  </td>
                </tr>
              ) : (
                prompts.map((prompt) => (
                  <tr
                    key={prompt.key}
                    data-testid={`prompt-row-${prompt.key}`}
                    className="cursor-pointer border-b transition-colors hover:bg-muted/50"
                    onClick={() => navigate(`/admin/prompts/${prompt.key}`)}
                  >
                    <td className="px-4 py-3">
                      <span className="font-mono text-xs">{prompt.key}</span>
                      {prompt.is_system && (
                        <Badge variant="secondary" className="ml-2">
                          {t("list.system")}
                        </Badge>
                      )}
                    </td>
                    <td className="px-4 py-3">{prompt.name}</td>
                    <td className="px-4 py-3">
                      {t(`create.categoryOptions.${prompt.category}`, {
                        defaultValue: prompt.category,
                      })}
                    </td>
                    <td className="px-4 py-3">
                      {prompt.active_version_no != null ? `v${prompt.active_version_no}` : "—"}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {formatDate(prompt.last_optimized_at, t("list.never"))}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </CardContent>
      </Card>

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="max-w-2xl" data-testid="prompt-create-dialog">
          <DialogHeader>
            <DialogTitle>{t("create.title")}</DialogTitle>
            <DialogDescription>{t("create.description")}</DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label htmlFor="create-key">{t("create.key")}</Label>
                <Input
                  id="create-key"
                  data-testid="create-key"
                  value={form.key}
                  placeholder={t("create.keyPlaceholder")}
                  onChange={(e) => setForm((f) => ({ ...f, key: e.target.value }))}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="create-name">{t("create.name")}</Label>
                <Input
                  id="create-name"
                  data-testid="create-name"
                  value={form.name}
                  onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label htmlFor="create-category">{t("create.category")}</Label>
                <Select
                  value={form.category}
                  onValueChange={(value) => setForm((f) => ({ ...f, category: value }))}
                >
                  <SelectTrigger id="create-category" data-testid="create-category">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {CATEGORY_OPTIONS.map((c) => (
                      <SelectItem key={c} value={c} data-testid={`create-category-${c}`}>
                        {t(`create.categoryOptions.${c}`)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="create-is-system">{t("create.isSystem")}</Label>
                <Select
                  value={form.isSystem ? "true" : "false"}
                  onValueChange={(value) =>
                    setForm((f) => ({ ...f, isSystem: value === "true" }))
                  }
                >
                  <SelectTrigger id="create-is-system" data-testid="create-is-system">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="false" data-testid="create-is-system-false">
                      {t("create.isSystemNo")}
                    </SelectItem>
                    <SelectItem value="true" data-testid="create-is-system-true">
                      {t("create.isSystemYes")}
                    </SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="create-description">{t("create.descriptionField")}</Label>
              <Input
                id="create-description"
                data-testid="create-description"
                value={form.description}
                onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="create-variables">{t("create.variables")}</Label>
              <Textarea
                id="create-variables"
                data-testid="create-variables"
                rows={2}
                value={form.variables}
                placeholder={t("create.variablesPlaceholder")}
                onChange={(e) => setForm((f) => ({ ...f, variables: e.target.value }))}
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="create-content">{t("create.content")}</Label>
              <Textarea
                id="create-content"
                data-testid="create-content"
                rows={8}
                value={form.content}
                onChange={(e) => setForm((f) => ({ ...f, content: e.target.value }))}
              />
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)}>
              {t("create.cancel")}
            </Button>
            <Button
              data-testid="create-submit"
              disabled={!canSubmit || createMutation.isPending}
              onClick={handleCreate}
            >
              {t("create.submit")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
