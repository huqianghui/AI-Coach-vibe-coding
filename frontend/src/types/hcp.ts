export interface HcpProfile {
  id: string;
  name: string;
  specialty: string;
  hospital: string;
  title: string;
  avatar_url: string;
  personality_type: "friendly" | "skeptical" | "busy" | "analytical" | "cautious";
  emotional_state: number; // 0-100
  communication_style: number; // 0-100
  expertise_areas: string[];
  prescribing_habits: string;
  concerns: string;
  objections: string[];
  probe_topics: string[];
  difficulty: "easy" | "medium" | "hard";
  is_active: boolean;
  created_by: string;
  created_at: string;
  updated_at: string;
  agent_id: string;
  agent_version: string;
  agent_sync_status: "synced" | "pending" | "failed" | "none";
  agent_sync_error: string;
  // Voice Live Instance reference
  voice_live_instance_id: string | null;
  voice_live_instance?: VoiceLiveInstanceSummary | null;
  avatar_enabled?: boolean;
  // Agent override (D-02)
  agent_instructions_override: string;
  // Knowledge Base config count (Phase 17)
  knowledge_config_count: number;
}

export interface VoiceLiveInstanceSummary {
  id: string;
  name: string;
  voice_live_model: string;
  enabled: boolean;
  voice_name: string;
  avatar_character: string;
  avatar_style: string;
  avatar_enabled?: boolean;
}

export interface HcpProfileCreate {
  name: string;
  specialty: string;
  hospital?: string;
  title?: string;
  avatar_url?: string;
  personality_type?: HcpProfile["personality_type"];
  emotional_state?: number;
  communication_style?: number;
  expertise_areas?: string[];
  prescribing_habits?: string;
  concerns?: string;
  objections?: string[];
  probe_topics?: string[];
  difficulty?: HcpProfile["difficulty"];
  voice_live_instance_id: string;
  agent_instructions_override?: string;
}

export interface HcpProfileUpdate extends Partial<HcpProfileCreate> {}
