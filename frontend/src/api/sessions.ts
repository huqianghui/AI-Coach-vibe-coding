import apiClient from "./client";
import type {
  CoachingHint,
  CoachingSession,
  KeyMessageStatus,
  SendMessageRequest,
  SessionMessage,
  SessionStreamError,
  SessionTurnState,
} from "@/types/session";

export interface SessionMessageStreamCallbacks {
  onState: (state: SessionTurnState) => void;
  onText: (chunk: string) => void;
  onHint: (hint: CoachingHint) => void;
  onKeyMessages: (status: KeyMessageStatus[]) => void;
  onDone: () => void;
  onError: (error: SessionStreamError) => void;
}

function parseStreamError(data: string): SessionStreamError {
  try {
    const parsed = JSON.parse(data) as SessionStreamError;
    return { ...parsed, message: parsed.message || data };
  } catch {
    return { message: data };
  }
}

function dispatchSessionEvent(
  event: string,
  data: string,
  callbacks: SessionMessageStreamCallbacks,
): void {
  switch (event) {
    case "state":
      callbacks.onState(JSON.parse(data) as SessionTurnState);
      break;
    case "text":
      callbacks.onText(data);
      break;
    case "hint":
      callbacks.onHint(JSON.parse(data) as CoachingHint);
      break;
    case "key_messages":
      callbacks.onKeyMessages(JSON.parse(data) as KeyMessageStatus[]);
      break;
    case "done":
      callbacks.onDone();
      break;
    case "error":
      callbacks.onError(parseStreamError(data));
      break;
  }
}

export async function streamSessionMessage(
  sessionId: string,
  message: string,
  callbacks: SessionMessageStreamCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  const request: SendMessageRequest = { message };
  const token = localStorage.getItem("access_token");
  const response = await fetch(`/api/v1/sessions/${sessionId}/message`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(request),
    signal,
  });
  if (!response.ok || !response.body) {
    throw new Error(`Stream failed: ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let currentEvent = "";
  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });
    const lines = buffer.split("\n");
    buffer = done ? "" : (lines.pop() ?? "");
    for (const rawLine of lines) {
      const line = rawLine.endsWith("\r") ? rawLine.slice(0, -1) : rawLine;
      if (line.startsWith("event:")) {
        currentEvent = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        dispatchSessionEvent(currentEvent, line.slice(5).trimStart(), callbacks);
      }
    }
    if (done) break;
  }
}

export async function createSession(scenarioId: string, mode: string = "voice_realtime_model") {
  const { data } = await apiClient.post<CoachingSession>("/sessions", {
    scenario_id: scenarioId,
    mode,
  });
  return data;
}

export async function getUserSessions(params?: {
  page?: number;
  page_size?: number;
}) {
  const { data } = await apiClient.get<{
    items: CoachingSession[];
    total: number;
    page: number;
    page_size: number;
    total_pages: number;
  }>("/sessions", { params });
  return data;
}

export async function getActiveSession() {
  const { data } = await apiClient.get<CoachingSession>("/sessions/active");
  return data;
}

export async function getSession(id: string) {
  const { data } = await apiClient.get<CoachingSession>(`/sessions/${id}`);
  return data;
}

export async function getSessionMessages(sessionId: string) {
  const { data } = await apiClient.get<SessionMessage[]>(
    `/sessions/${sessionId}/messages`,
  );
  return data;
}

export async function endSession(sessionId: string) {
  const { data } = await apiClient.post<CoachingSession>(
    `/sessions/${sessionId}/end`,
  );
  return data;
}
