import { useTranslation } from "react-i18next";
import {
  Download,
  Printer,
  TrendingUp,
  Target,
  Award,
} from "lucide-react";
import {
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui";
import { LoadingState, EmptyState } from "@/components/shared";
import { PerformanceRadar, TrendLineChart } from "@/components/analytics";
import {
  useDashboardStats,
  useDimensionTrends,
  useRecommendedScenarios,
  useExportSessionsExcel,
} from "@/hooks/use-analytics";

export default function UserReportsPage() {
  const { t } = useTranslation("analytics");
  const { data: dashStats, isLoading: statsLoading } = useDashboardStats();
  const { data: trends, isLoading: trendsLoading } = useDimensionTrends(20);
  const { data: recommendations } = useRecommendedScenarios(3);
  const exportExcel = useExportSessionsExcel();

  const isLoading = statsLoading || trendsLoading;

  // Extract current and previous dimension scores from trends data for radar
  const currentScores =
    trends && trends.length > 0 && trends[0]
      ? trends[0].dimensions.map((d) => ({
          dimension: d.dimension,
          score: d.score,
        }))
      : [];

  const previousScores =
    trends && trends.length > 1 && trends[1]
      ? trends[1].dimensions.map((d) => ({
          dimension: d.dimension,
          score: d.score,
        }))
      : [];

  if (isLoading) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-medium text-foreground">
          {t("pageTitle")}
        </h1>
        <LoadingState variant="card" />
      </div>
    );
  }

  // Empty state: no sessions yet
  if (dashStats?.total_sessions === 0) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-medium text-foreground">
          {t("pageTitle")}
        </h1>
        <EmptyState
          title={t("noData")}
          body={t("noDataBody")}
        />
      </div>
    );
  }

  return (
    <div className="print-content space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-2xl font-medium text-foreground">
          {t("pageTitle")}
        </h1>
        <div className="no-print flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => window.print()}
            className="transition-colors duration-150"
          >
            <Printer className="mr-1.5 size-4" />
            {t("exportPdf")}
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => exportExcel.mutate()}
            disabled={exportExcel.isPending}
            className="transition-colors duration-150"
          >
            <Download className="mr-1.5 size-4" />
            {t("exportExcel")}
          </Button>
        </div>
      </div>

      {/* Compact summary bar */}
      <div className="print-avoid-break flex flex-wrap items-center gap-6 rounded-lg border border-border bg-card px-6 py-4">
        <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground">{t("totalSessions")}:</span>
          <span className="text-lg font-semibold text-foreground">{dashStats?.total_sessions ?? 0}</span>
        </div>
        <div className="h-4 w-px bg-border" />
        <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground">{t("avgScore")}:</span>
          <span className="text-lg font-semibold text-foreground">{dashStats?.avg_score ?? 0}</span>
        </div>
        <div className="h-4 w-px bg-border" />
        <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground">{t("sessionsThisWeek")}:</span>
          <span className="text-lg font-semibold text-foreground">{dashStats?.this_week ?? 0}</span>
        </div>
        <div className="h-4 w-px bg-border" />
        <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground">{t("improvement")}:</span>
          <span className="text-lg font-semibold text-foreground">
            {dashStats?.improvement != null
              ? `${dashStats.improvement > 0 ? "+" : ""}${dashStats.improvement}`
              : t("noImprovement")}
          </span>
        </div>
      </div>

      {/* Charts grid */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Performance Trend */}
        <Card className="print-avoid-break bg-card">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base font-medium">
              <TrendingUp className="size-5 text-primary" />
              {t("performanceTrend")}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {trends && trends.length >= 2 ? (
              <TrendLineChart data={trends} height={300} />
            ) : (
              <p className="py-8 text-center text-sm text-muted-foreground">
                {t("noData")}
              </p>
            )}
          </CardContent>
        </Card>

        {/* Skill Radar */}
        <Card className="print-avoid-break bg-card">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base font-medium">
              <Target className="size-5 text-primary" />
              {t("skillGapHeatmap")}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {currentScores.length > 0 ? (
              <PerformanceRadar
                currentScores={currentScores}
                previousScores={previousScores.length > 0 ? previousScores : undefined}
                height={300}
              />
            ) : (
              <p className="py-8 text-center text-sm text-muted-foreground">
                {t("noData")}
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Recommendations */}
      {recommendations && recommendations.length > 0 && (
        <Card className="print-avoid-break bg-card">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base font-medium">
              <Award className="size-5 text-primary" />
              {t("recommendations")}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid gap-6 sm:grid-cols-3">
              {recommendations.map((rec) => (
                <div
                  key={rec.scenario_id}
                  className="rounded-lg border border-border bg-muted/40 p-4"
                >
                  <p className="font-medium text-foreground">{rec.scenario_name}</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {rec.product} &middot; {rec.difficulty}
                  </p>
                  <p className="mt-2 text-sm text-muted-foreground">
                    {rec.reason}
                  </p>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
