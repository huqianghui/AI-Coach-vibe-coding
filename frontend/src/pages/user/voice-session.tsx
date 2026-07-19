import { useSearchParams, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Loader2, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui";
import { VoiceSession } from "@/components/voice/voice-session";
import { useSession } from "@/hooks/use-session";
import { useScenario } from "@/hooks/use-scenarios";

/**
 * Voice session page component.
 * Full-screen page (no UserLayout wrapper), following conference-session.tsx pattern.
 * Reads session parameters from URL search params.
 * Mode is auto-resolved from token broker (D-10) -- no manual mode selection.
 */
export default function VoiceSessionPage() {
  const { t, i18n } = useTranslation("voice");
  const { t: tc } = useTranslation("common");
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const sessionId = searchParams.get("id") ?? "";

  // Fetch session and scenario data
  const { data: session, isLoading: sessionLoading, isError: sessionError } = useSession(
    sessionId || undefined,
  );
  const { data: scenario, isLoading: scenarioLoading, isError: scenarioError } = useScenario(
    session?.scenario_id,
  );

  // Error state — show actionable message instead of perpetual spinner
  if (sessionError || scenarioError) {
    return (
      <div className="flex h-screen w-screen items-center justify-center bg-background">
        <div className="flex flex-col items-center gap-4">
          <AlertTriangle className="h-10 w-10 text-destructive" />
          <p className="text-sm text-muted-foreground">{t("error.loadFailed")}</p>
          <Button variant="outline" onClick={() => navigate("/user/training")}>
            {tc("back")}
          </Button>
        </div>
      </div>
    );
  }

  // Block on BOTH session AND scenario loading — VoiceSession needs hcpProfileId
  // from scenario to fetch per-HCP voice/avatar config from token broker (D-08)
  if (sessionLoading || !session || (session.scenario_id && scenarioLoading)) {
    return (
      <div className="flex h-screen w-screen items-center justify-center bg-background">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
          <p className="text-sm text-muted-foreground">{t("title")}</p>
        </div>
      </div>
    );
  }

  const hcpProfileId = scenario?.hcp_profile_id ?? "";
  const hcpName = scenario?.hcp_profile?.name ?? "HCP";
  const systemPrompt = scenario?.description ?? "";
  const language = i18n.language || "zh-CN";
  const avatarCharacter =
    scenario?.hcp_profile?.voice_live_instance?.avatar_character ?? "lisa";
  const avatarStyle = scenario?.hcp_profile?.voice_live_instance?.avatar_style ?? "";
  const voiceName = scenario?.hcp_profile?.voice_live_instance?.voice_name ?? "";

  return (
    <VoiceSession
      sessionId={session.id}
      scenarioId={session.scenario_id}
      hcpProfileId={hcpProfileId}
      hcpName={hcpName}
      systemPrompt={systemPrompt}
      language={language}
      avatarCharacter={avatarCharacter}
      avatarStyle={avatarStyle}
      voiceName={voiceName}
    />
  );
}
