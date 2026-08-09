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
  agent_name: string | null;
  agent_version: string | null;
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

export type SessionTurnStatus =
  | "idle"
  | "accepted"
  | "in_progress"
  | "reconciling"
  | "succeeded"
  | "failed_terminal"
  | "disconnected";

export interface SessionTurnState {
  code:
    | "SESSION_TURN_ACCEPTED"
    | "SESSION_TURN_RESUMED"
    | "SESSION_TURN_IN_PROGRESS"
    | "SESSION_TURN_RECONCILING"
    | "SESSION_TURN_FAILED";
  status: "in_progress" | "reconciling" | "failed_terminal";
}

export interface SessionStreamError {
  code?: string;
  message: string;
  details?: Record<string, unknown>;
}

export interface SSEEvent {
  event: "state" | "text" | "hint" | "key_messages" | "done" | "error";
  data: string;
}
