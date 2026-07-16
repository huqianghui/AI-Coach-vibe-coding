export type SessionStatus = "created" | "in_progress" | "completed" | "scored";

export interface KeyMessageStatus {
  message: string;
  delivered: boolean;
  detected_at: string | null;
}

export interface CoachingSession {
  id: string;
  user_id: string;
  scenario_id: string;
  scenario_name: string | null;
  status: SessionStatus;
  started_at: string | null;
  completed_at: string | null;
  duration_seconds: number | null;
  key_messages_status: KeyMessageStatus[];
  overall_score: number | null;
  passed: boolean | null;
  mode: string;
  message_count: number;
  created_at: string;
  updated_at: string;
}

export interface SessionMessage {
  id: string;
  session_id: string;
  role: "user" | "assistant";
  content: string;
  message_index: number;
  speaker_id?: string | null;
  speaker_name?: string;
  created_at: string;
}

export interface SendMessageRequest {
  message: string;
}

export interface CoachingHint {
  content: string;
  metadata?: Record<string, unknown>;
}

export interface SSEEvent {
  event: "text" | "hint" | "key_messages" | "done" | "error";
  data: string;
}
