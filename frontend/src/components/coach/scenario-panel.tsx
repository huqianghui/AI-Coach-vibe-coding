import { useTranslation } from "react-i18next";
import { ChevronLeft, ChevronRight } from "lucide-react";
import {
  ScrollArea,
  Avatar,
  AvatarFallback,
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui";
import { KeyMessages } from "./key-messages";
import type { Scenario } from "@/types/scenario";
import type { KeyMessageStatus } from "@/types/session";

interface ScenarioPanelProps {
  scenario: Scenario;
  keyMessagesStatus: KeyMessageStatus[];
  isCollapsed: boolean;
  onToggle: () => void;
}

export function ScenarioPanel({
  scenario,
  keyMessagesStatus,
  isCollapsed,
  onToggle,
}: ScenarioPanelProps) {
  const { t } = useTranslation("coach");

  // Extract product and area from tags (format: "product:X", "area:Y")
  const product = scenario.tags?.find((t) => t.startsWith("product:"))?.split(":", 2)[1] ?? "";
  const area =
    scenario.tags?.find((t) => t.startsWith("area:") || t.startsWith("therapeutic_area:"))
      ?.split(":", 2)[1] ?? "";

  const hcpInitials = scenario.hcp_profile?.name
    ? scenario.hcp_profile.name
        .split(" ")
        .map((n) => n[0])
        .join("")
        .toUpperCase()
        .slice(0, 2) || "HC"
    : "HC";

  if (isCollapsed) {
    return (
      <div className="flex w-12 flex-col items-center border-r border-border bg-muted/50 pt-4">
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          onClick={onToggle}
          aria-expanded={false}
          aria-label={t("session.trainingPanel")}
        >
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>
    );
  }

  // Scoring criteria display removed — rubric dimensions are now displayed
  // via the rubric associated with rubric_id (rendered in ScenarioEditor).

  return (
    <div className="flex w-[280px] flex-col border-r border-border bg-muted/50">
      <div className="flex h-14 items-center justify-between border-b border-border px-4">
        <h2 className="text-sm font-medium text-foreground">{t("session.trainingPanel")}</h2>
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          onClick={onToggle}
          aria-expanded={true}
        >
          <ChevronLeft className="h-4 w-4" />
        </Button>
      </div>

      <ScrollArea className="flex-1 overflow-y-auto p-4">
        {/* Scenario Briefing */}
        <Card className="mb-4 bg-card">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">{t("session.scenarioBriefing")}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Product</span>
              <span className="font-medium text-foreground">{product || "—"}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Area</span>
              <span className="font-medium text-foreground">{area || "—"}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Difficulty</span>
              <Badge variant="secondary" className="text-xs">
                {scenario.difficulty}
              </Badge>
            </div>
          </CardContent>
        </Card>

        {/* HCP Profile */}
        {scenario.hcp_profile && (
          <Card className="mb-4 bg-card">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">{t("session.hcpProfile")}</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex items-center gap-3">
                <Avatar className="h-[60px] w-[60px]">
                  <AvatarFallback className="bg-primary/10 text-primary">
                    {hcpInitials}
                  </AvatarFallback>
                </Avatar>
                <div>
                  <p className="font-medium text-foreground">{scenario.hcp_profile.name}</p>
                  <p className="text-sm text-muted-foreground">
                    {scenario.hcp_profile.specialty}
                  </p>
                  <p className="text-sm text-muted-foreground">
                    {scenario.hcp_profile.personality_type}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Key Messages */}
        <Card className="mb-4 bg-card">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">{t("session.keyMessages")}</CardTitle>
          </CardHeader>
          <CardContent>
            <KeyMessages messages={keyMessagesStatus} />
          </CardContent>
        </Card>

        {/* Scoring Criteria — rubric-based (dimensions shown via rubric) */}
        <Card className="mb-4 bg-card">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">{t("session.scoringCriteria")}</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">
            <p>{t("session.rubricBased", "Rubric-based scoring")}</p>
          </CardContent>
        </Card>
      </ScrollArea>
    </div>
  );
}
