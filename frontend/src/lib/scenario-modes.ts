import type { Scenario } from "@/types/scenario";

/** Feature flags relevant to voice/avatar mode gating. */
export interface ScenarioModeFeatures {
  voice_enabled?: boolean;
  voice_live_enabled?: boolean;
  avatar_enabled?: boolean;
}

/**
 * Single source of truth for which training modes (text / voice / digital human)
 * are available for a scenario, given the HCP's bound VoiceLiveInstance and the
 * platform's feature flags.
 *
 * f2f: voice requires `features.voice_live_enabled && hcp.voice_live_instance.enabled`;
 *      avatar additionally requires `features.avatar_enabled && hcp.voice_live_instance.avatar_enabled`.
 * conference: voice requires `features.voice_enabled` alone; avatar requires the full
 *      VL Instance gating (`voice_live_enabled` + `avatar_enabled` + instance flags).
 *
 * Extracted (WR-02, Phase 30 review) so `training.tsx` and `scenario-group-run.tsx`
 * cannot silently drift out of sync -- exactly the class of bug the D-10 avatar
 * propagation fix addressed.
 */
export function getAvailableModes(
  scenario: Scenario | null | undefined,
  features: ScenarioModeFeatures | undefined,
) {
  const modes = ["text"];
  const hcp = scenario?.hcp_profile;
  const voiceAvailable =
    scenario?.mode === "conference"
      ? Boolean(features?.voice_enabled)
      : Boolean(features?.voice_live_enabled && hcp?.voice_live_instance?.enabled);
  const avatarAvailable =
    scenario?.mode === "conference"
      ? Boolean(
          features?.voice_live_enabled &&
            features?.avatar_enabled &&
            hcp?.voice_live_instance?.enabled &&
            hcp?.voice_live_instance?.avatar_enabled,
        )
      : Boolean(
          voiceAvailable && features?.avatar_enabled && hcp?.voice_live_instance?.avatar_enabled,
        );

  if (voiceAvailable) {
    modes.push("voice_realtime_model");
  }
  if (avatarAvailable) {
    modes.push("digital_human_realtime_model");
  }

  const defaultMode = avatarAvailable
    ? "digital_human_realtime_model"
    : voiceAvailable
      ? "voice_realtime_model"
      : "text";

  return { modes, defaultMode };
}
