import apiClient from "@/api/client";
import type {
  VoiceLiveToken,
  VoiceLiveConfigStatus,
  VoiceLiveModelsResponse,
  AvatarCharactersResponse,
  VoiceLiveInstance,
  VoiceLiveInstanceCreate,
  VoiceLiveInstanceUpdate,
  VoiceLiveInstanceListResponse,
  WebRTCSessionConfig,
} from "@/types/voice-live";

export async function fetchVoiceLiveToken(hcpProfileId?: string): Promise<VoiceLiveToken> {
  const params = hcpProfileId ? { hcp_profile_id: hcpProfileId } : {};
  const response = await apiClient.post<VoiceLiveToken>("/voice-live/token", null, { params });
  return response.data;
}

export async function fetchWebRTCSession(
  hcpProfileId?: string,
  vlInstanceId?: string,
  sessionId?: string,
): Promise<WebRTCSessionConfig> {
  const params: Record<string, string> = {};
  if (hcpProfileId) params.hcp_profile_id = hcpProfileId;
  if (vlInstanceId) params.vl_instance_id = vlInstanceId;
  if (sessionId) params.session_id = sessionId;
  const res = await apiClient.post<WebRTCSessionConfig>(
    "/voice-live/webrtc/session",
    null,
    { params },
  );
  return res.data;
}

export async function fetchVoiceLiveStatus(): Promise<VoiceLiveConfigStatus> {
  const response = await apiClient.get<VoiceLiveConfigStatus>("/voice-live/status");
  return response.data;
}

export async function fetchVoiceLiveModels(): Promise<VoiceLiveModelsResponse> {
  const response = await apiClient.get<VoiceLiveModelsResponse>("/voice-live/models");
  return response.data;
}

export async function fetchAvatarCharacters(): Promise<AvatarCharactersResponse> {
  const response = await apiClient.get<AvatarCharactersResponse>("/voice-live/avatar-characters");
  return response.data;
}

export async function persistTranscriptMessage(
  sessionId: string,
  role: "user" | "assistant",
  content: string,
): Promise<void> {
  await apiClient.post(`/sessions/${sessionId}/transcript`, {
    message: content,
    role,
  });
}

// ── Voice Live Instance CRUD ───────────────────────────────────────────

export async function fetchVoiceLiveInstances(params?: {
  page?: number;
  page_size?: number;
}): Promise<VoiceLiveInstanceListResponse> {
  const response = await apiClient.get<VoiceLiveInstanceListResponse>(
    "/voice-live/instances",
    { params },
  );
  return response.data;
}

export async function fetchVoiceLiveInstance(
  id: string,
): Promise<VoiceLiveInstance> {
  const response = await apiClient.get<VoiceLiveInstance>(
    `/voice-live/instances/${id}`,
  );
  return response.data;
}

export async function createVoiceLiveInstance(
  data: VoiceLiveInstanceCreate,
): Promise<VoiceLiveInstance> {
  const response = await apiClient.post<VoiceLiveInstance>(
    "/voice-live/instances",
    data,
  );
  return response.data;
}

export async function updateVoiceLiveInstance(
  id: string,
  data: VoiceLiveInstanceUpdate,
): Promise<VoiceLiveInstance> {
  const response = await apiClient.put<VoiceLiveInstance>(
    `/voice-live/instances/${id}`,
    data,
  );
  return response.data;
}

export async function deleteVoiceLiveInstance(id: string): Promise<void> {
  await apiClient.delete(`/voice-live/instances/${id}`);
}

export async function assignVoiceLiveInstance(
  instanceId: string,
  hcpProfileId: string,
): Promise<VoiceLiveInstance> {
  const response = await apiClient.post<VoiceLiveInstance>(
    `/voice-live/instances/${instanceId}/assign`,
    { hcp_profile_id: hcpProfileId },
  );
  return response.data;
}

export async function unassignVoiceLiveInstance(
  hcpProfileId: string,
): Promise<{ hcp_profile_id: string; voice_live_instance_id: null }> {
  const response = await apiClient.post<{ hcp_profile_id: string; voice_live_instance_id: null }>(
    "/voice-live/instances/unassign",
    { hcp_profile_id: hcpProfileId },
  );
  return response.data;
}
