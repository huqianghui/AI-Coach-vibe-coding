import { lazy, Suspense } from "react";
import { createBrowserRouter, Navigate } from "react-router-dom";
import { ProtectedRoute, AdminRoute, GuestRoute } from "./auth-guard";
import { UserLayout } from "@/components/layouts/user-layout";
import { AdminLayout } from "@/components/layouts/admin-layout";
import { AuthLayout } from "@/components/layouts/auth-layout";
import { LoadingFallback } from "@/components/shared/loading-fallback";

// Lazy-loaded page components for code splitting
const LoginPage = lazy(() => import("@/pages/login"));
const UserDashboard = lazy(() => import("@/pages/user/dashboard"));
const ScenarioSelection = lazy(() => import("@/pages/user/training"));
const ScoringFeedback = lazy(() => import("@/pages/user/scoring-feedback"));
const SessionHistory = lazy(() => import("@/pages/user/session-history"));
const UserReportsPage = lazy(() => import("@/pages/user/reports"));
const ConferenceSession = lazy(() => import("@/pages/user/conference-session"));
const UnifiedSession = lazy(() => import("@/pages/user/unified-session"));

const AdminDashboard = lazy(() => import("@/pages/admin/dashboard"));
const HcpProfilesPage = lazy(() => import("@/pages/admin/hcp-profiles"));
const HcpProfileEditorPage = lazy(() => import("@/pages/admin/hcp-profile-editor"));
const ScenariosPage = lazy(() => import("@/pages/admin/scenarios"));
const ScenarioEditorPage = lazy(() => import("@/pages/admin/scenario-editor"));
const AzureConfigPage = lazy(() => import("@/pages/admin/azure-config"));
const VoiceLiveManagementPage = lazy(() => import("@/pages/admin/voice-live-management"));
const VlInstanceEditorPage = lazy(() => import("@/pages/admin/vl-instance-editor"));
const ScoringRubricsPage = lazy(() => import("@/pages/admin/scoring-rubrics"));
const RubricEditorPage = lazy(() => import("@/pages/admin/rubric-editor"));
const TrainingMaterialsPage = lazy(() => import("@/pages/admin/training-materials"));
const AdminReportsPage = lazy(() => import("@/pages/admin/reports"));
const UserManagementPage = lazy(() => import("@/pages/admin/users"));
const AdminSettingsPage = lazy(() => import("@/pages/admin/settings"));
const SkillHubPage = lazy(() => import("@/pages/admin/skill-hub"));
const SkillEditorPage = lazy(() => import("@/pages/admin/skill-editor"));
const MetaSkillsPage = lazy(() => import("@/pages/admin/meta-skills"));
const PromptsPage = lazy(() => import("@/pages/admin/prompts"));
const PromptEditorPage = lazy(() => import("@/pages/admin/prompt-editor"));
const PromptOptimizerPage = lazy(() => import("@/pages/admin/prompt-optimizer"));
const SystemEnumsPage = lazy(() => import("@/pages/admin/system-enums"));
const DryRunReportPage = lazy(() => import("@/pages/admin/dry-run-report"));

const NotFound = lazy(() => import("@/pages/not-found"));

function SuspensePage({ children }: { children: React.ReactNode }) {
  return <Suspense fallback={<LoadingFallback />}>{children}</Suspense>;
}

export const router = createBrowserRouter([
  {
    element: <GuestRoute />,
    children: [
      {
        element: <AuthLayout />,
        children: [{ path: "/login", element: <SuspensePage><LoginPage /></SuspensePage> }],
      },
    ],
  },
  {
    element: <ProtectedRoute />,
    children: [
      {
        path: "/user",
        element: <UserLayout />,
        children: [
          { path: "dashboard", element: <SuspensePage><UserDashboard /></SuspensePage> },
          { path: "training", element: <SuspensePage><ScenarioSelection /></SuspensePage> },
          { path: "scoring/:sessionId", element: <SuspensePage><ScoringFeedback /></SuspensePage> },
          { path: "history", element: <SuspensePage><SessionHistory /></SuspensePage> },
          { path: "reports", element: <SuspensePage><UserReportsPage /></SuspensePage> },
        ],
      },
      {
        path: "/user/training/session",
        element: <SuspensePage><UnifiedSession /></SuspensePage>,
      },
      {
        path: "/user/training/conference",
        element: <SuspensePage><ConferenceSession /></SuspensePage>,
      },
      {
        path: "/user/training/voice",
        element: <Navigate to="/user/training/session" replace />,
      },
      {
        element: <AdminRoute />,
        children: [
          {
            path: "/admin",
            element: <AdminLayout />,
            children: [
              { path: "dashboard", element: <SuspensePage><AdminDashboard /></SuspensePage> },
              { path: "hcp-profiles", element: <SuspensePage><HcpProfilesPage /></SuspensePage> },
              { path: "hcp-profiles/new", element: <SuspensePage><HcpProfileEditorPage /></SuspensePage> },
              { path: "hcp-profiles/:id", element: <SuspensePage><HcpProfileEditorPage /></SuspensePage> },
              { path: "hcp-profiles/:id/edit", element: <SuspensePage><HcpProfileEditorPage /></SuspensePage> },
              { path: "scenarios", element: <SuspensePage><ScenariosPage /></SuspensePage> },
              { path: "scenarios/new", element: <SuspensePage><ScenarioEditorPage /></SuspensePage> },
              { path: "scenarios/:id", element: <SuspensePage><ScenarioEditorPage /></SuspensePage> },
              { path: "azure-config", element: <SuspensePage><AzureConfigPage /></SuspensePage> },
              { path: "voice-live", element: <SuspensePage><VoiceLiveManagementPage /></SuspensePage> },
              { path: "voice-live/new", element: <SuspensePage><VlInstanceEditorPage /></SuspensePage> },
              { path: "voice-live/:id/edit", element: <SuspensePage><VlInstanceEditorPage /></SuspensePage> },
              { path: "scoring-rubrics", element: <SuspensePage><ScoringRubricsPage /></SuspensePage> },
              { path: "scoring-rubrics/new", element: <SuspensePage><RubricEditorPage /></SuspensePage> },
              { path: "scoring-rubrics/:id", element: <SuspensePage><RubricEditorPage /></SuspensePage> },
              { path: "prompts", element: <SuspensePage><PromptsPage /></SuspensePage> },
              { path: "prompts/:key/optimize", element: <SuspensePage><PromptOptimizerPage /></SuspensePage> },
              { path: "prompts/:key", element: <SuspensePage><PromptEditorPage /></SuspensePage> },
              { path: "prompt-optimizer", element: <SuspensePage><PromptOptimizerPage /></SuspensePage> },
              { path: "materials", element: <SuspensePage><TrainingMaterialsPage /></SuspensePage> },
              { path: "skills", element: <SuspensePage><SkillHubPage /></SuspensePage> },
              { path: "skills/new", element: <SuspensePage><SkillEditorPage /></SuspensePage> },
              { path: "skills/:id/edit", element: <SuspensePage><SkillEditorPage /></SuspensePage> },
              { path: "skills/:id/dry-run/:runId", element: <SuspensePage><DryRunReportPage /></SuspensePage> },
              { path: "reports", element: <SuspensePage><AdminReportsPage /></SuspensePage> },
              { path: "users", element: <SuspensePage><UserManagementPage /></SuspensePage> },
              { path: "meta-skills", element: <SuspensePage><MetaSkillsPage /></SuspensePage> },
              { path: "system-enums", element: <SuspensePage><SystemEnumsPage /></SuspensePage> },
              { path: "settings", element: <SuspensePage><AdminSettingsPage /></SuspensePage> },
            ],
          },
        ],
      },
    ],
  },
  { path: "/", element: <Navigate to="/login" replace /> },
  { path: "*", element: <SuspensePage><NotFound /></SuspensePage> },
]);
