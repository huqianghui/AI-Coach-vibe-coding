import type { VoiceLiveInstanceSummary } from "./hcp";

export interface ModeratorRemarks {
  zh: string;
  en: string;
}

export interface HcpProfileSummary {
  id: string;
  name: string;
  specialty: string;
  avatar_url: string;
  personality_type: string;
  voice_live_instance_id: string | null;
  voice_live_instance?: VoiceLiveInstanceSummary | null;
}

export interface ConferencePromptConfig {
  speaker_order_policy: string;
  audience_prompt_template: string;
  moderator_remarks: Record<"invite" | "opening" | "handoff" | "closing", ModeratorRemarks>;
}

export interface Scenario {
  id: string;
  name: string;
  description: string;
  tags?: string[];
  product?: string;
  therapeutic_area?: string;
  estimated_duration?: number;
  mode: "f2f" | "conference";
  difficulty: "easy" | "medium" | "hard";
  status: "draft" | "active" | "archived";
  hcp_profile_id: string;
  hcp_profile?: HcpProfileSummary;
  key_messages: string[];
  conference_prompt_config?: ConferencePromptConfig;
  skill_id: string | null;
  skill_version_id: string | null;
  rubric_id: string;
  pass_threshold: number;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface ScenarioCreate {
  name: string;
  tags?: string[];
  product?: string;
  therapeutic_area?: string;
  hcp_profile_id: string;
  skill_id?: string;
  rubric_id: string;
  description?: string;
  mode?: Scenario["mode"];
  difficulty?: Scenario["difficulty"];
  key_messages?: string[];
  conference_prompt_config?: ConferencePromptConfig;
  pass_threshold?: number;
}

export interface ScenarioUpdate {
  name?: string;
  tags?: string[];
  hcp_profile_id?: string;
  skill_id?: string;
  rubric_id?: string;
  description?: string;
  mode?: Scenario["mode"];
  difficulty?: Scenario["difficulty"];
  key_messages?: string[];
  conference_prompt_config?: ConferencePromptConfig;
  pass_threshold?: number;
}
