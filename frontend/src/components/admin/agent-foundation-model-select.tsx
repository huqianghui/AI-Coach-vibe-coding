import { RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useAgentFoundationModels } from "@/hooks/use-agent-foundation-models";

interface AgentFoundationModelSelectProps {
  value: string;
  onValueChange: (value: string) => void;
  disabled?: boolean;
}

export function AgentFoundationModelSelect({
  value,
  onValueChange,
  disabled,
}: AgentFoundationModelSelectProps) {
  const { t } = useTranslation("admin");
  const { data, isLoading, isError, refetch } = useAgentFoundationModels();

  if (isLoading) {
    return (
      <Select disabled>
        <SelectTrigger className="h-8 text-xs">
          <SelectValue placeholder={t("hcp.foundationModelLoading")} />
        </SelectTrigger>
        <SelectContent />
      </Select>
    );
  }

  if (isError || data?.error) {
    return (
      <div className="flex items-center gap-2">
        <p className="text-xs text-destructive flex-1">
          {t("hcp.foundationModelError")}
        </p>
        <Button
          variant="ghost"
          size="icon"
          className="size-7 shrink-0"
          onClick={() => refetch()}
          aria-label={t("hcp.foundationModelError")}
        >
          <RefreshCw className="size-3.5" />
        </Button>
      </div>
    );
  }

  const models = data?.models ?? [];

  if (models.length === 0) {
    return (
      <p className="text-xs text-muted-foreground">
        {t("hcp.foundationModelEmpty")}
      </p>
    );
  }

  return (
    <Select value={value} onValueChange={onValueChange} disabled={disabled}>
      <SelectTrigger className="h-8 text-xs">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {models.map((model) => (
          <SelectItem key={model.id} value={model.id}>
            {model.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
