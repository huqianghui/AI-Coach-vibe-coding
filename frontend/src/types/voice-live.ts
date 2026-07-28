/** Audio transport mode: WebSocket proxy (default) or direct WebRTC to Azure (preview). */
export type VoiceTransport = "websocket" | "webrtc";

export type SessionMode =
  | "text"
  | "voice_pipeline"
  | "digital_human_pipeline"
  | "voice_realtime_model"
  | "digital_human_realtime_model"
  | "voice_realtime_agent"
  | "digital_human_realtime_agent";

export interface VoiceLiveToken {
  endpoint: string;
  /** Masked token ("***configured***") -- auth is handled server-side by the WebSocket proxy. */
  token: string;
  auth_type?: "key" | "bearer"; // "key" for API key, "bearer" for STS bearer token
  region: string;
  model: string;
  avatar_enabled: boolean;
  avatar_character: string;
  voice_name: string;
  agent_id?: string;
  agent_version?: string;
  project_name?: string;
  // Per-HCP fields from token broker (D-08)
  avatar_style?: string;
  avatar_customized?: boolean;
  voice_type?: string;
  voice_temperature?: number;
  voice_custom?: boolean;
  turn_detection_type?: string;
  noise_suppression?: boolean;
  echo_cancellation?: boolean;
  eou_detection?: boolean;
  recognition_language?: string;
}

export interface VoiceLiveConfigStatus {
  voice_live_available: boolean;
  avatar_available: boolean;
  voice_name: string;
  avatar_character: string;
}

export interface VoiceLiveModelInfo {
  id: string;
  label: string;
  tier: string;
  description: string;
}

export interface VoiceLiveModelsResponse {
  models: VoiceLiveModelInfo[];
}

export type VoiceConnectionState =
  | "disconnected"
  | "connecting"
  | "connected"
  | "reconnecting"
  | "error";

export type AudioState = "idle" | "listening" | "speaking" | "muted";

export interface TranscriptSegment {
  id: string;
  role: "user" | "assistant";
  content: string;
  isFinal: boolean;
  timestamp: number;
}

export interface VoiceLiveOptions {
  language: string;
  systemPrompt: string;
  onTranscript?: (segment: TranscriptSegment) => void;
  /** Called for each `response.audio.delta` event with base64-encoded PCM16 audio. */
  onAudioDelta?: (base64Audio: string) => void;
  onConnectionStateChange?: (state: VoiceConnectionState) => void;
  onAudioStateChange?: (state: AudioState) => void;
  onResponseDone?: () => void;
  onError?: (error: Error) => void;
}

export interface VoiceLiveControls {
  connect: (
    hcpProfileId: string,
    systemPrompt?: string,
  ) => Promise<{
    avatarEnabled: boolean;
    model: string;
    iceServers: RTCIceServer[];
  }>;
  disconnect: () => Promise<void>;
  toggleMute: () => void;
  sendTextMessage: (text: string) => Promise<void>;
  /** Send audio data (PCM16 base64-encoded) via backend proxy. */
  sendAudio: (base64Audio: string) => void;
  /** Send raw Azure RT protocol message via backend proxy. */
  send: (data: unknown) => void;
  isMuted: boolean;
  connectionState: VoiceConnectionState;
  audioState: AudioState;
  avatarSdpCallbackRef: React.MutableRefObject<
    ((serverSdp: string) => void) | null
  >;
}

/** Runtime voice configuration settings for the config panel. */
export interface VoiceConfigSettings {
  /** Speech input language code (e.g. "zh-CN", "en-US") or "auto" for auto-detect. */
  language: string;
  /** Whether to auto-detect the spoken language. */
  autoDetect: boolean;
  /** Show partial AI responses while still generating. */
  interimResponse: boolean;
  /** AI initiates conversation proactively. */
  proactiveEngagement: boolean;
}

/** Response from POST /api/v1/voice-live/webrtc/session */
export interface WebRTCSessionConfig {
  signaling_url: string;
  auth_token: string;
  auth_type: string;
  model: string;
  mode: "agent" | "model";
  session_config: Record<string, unknown>;
  agent_id?: string;
  agent_version?: string;
  project_name?: string;
  avatar_warning?: string;
}

export interface AvatarCharacterStyle {
  id: string;
  display_name: string;
}

export interface AvatarCharacterInfo {
  id: string;
  display_name: string;
  gender: string;
  is_photo_avatar: boolean;
  styles: AvatarCharacterStyle[];
  default_style: string;
  thumbnail_url: string;
}

export interface AvatarCharactersResponse {
  characters: AvatarCharacterInfo[];
}

export interface AvatarStreamControls {
  /** Start avatar WebRTC handshake. Sends SDP offer via VoiceLive session event. */
  connect: (
    iceServers: RTCIceServer[],
    sendSdpOffer: (sdp: string) => Promise<void>,
  ) => Promise<void>;
  /** Handle SDP answer from server (via onSessionAvatarConnecting handler). */
  handleServerSdp: (serverSdp: string) => Promise<void>;
  disconnect: () => void;
  isConnected: boolean;
}

// ── Voice Live Instance (reusable configuration entity) ────────────────

export interface VoiceLiveInstance {
  id: string;
  name: string;
  description: string;
  voice_live_model: string;
  enabled: boolean;
  voice_name: string;
  voice_type: string;
  voice_temperature: number;
  voice_custom: boolean;
  avatar_character: string;
  avatar_style: string;
  avatar_customized: boolean;
  turn_detection_type: string;
  noise_suppression: boolean;
  echo_cancellation: boolean;
  eou_detection: boolean;
  recognition_language: string;
  // AI Foundry Playground fields (n17a)
  response_temperature: number;
  proactive_engagement: boolean;
  auto_detect_language: boolean;
  playback_speed: number;
  custom_lexicon_enabled: boolean;
  custom_lexicon_url: string;
  avatar_enabled: boolean;
  model_instruction: string;
  hcp_count: number;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface VoiceLiveInstanceSummary {
  id: string;
  name: string;
  voice_live_model: string;
  voice_name: string;
  avatar_character: string;
  hcp_count: number;
}

export interface VoiceLiveInstanceCreate {
  name: string;
  description?: string;
  voice_live_model?: string;
  enabled?: boolean;
  voice_name?: string;
  voice_type?: string;
  voice_temperature?: number;
  voice_custom?: boolean;
  avatar_character?: string;
  avatar_style?: string;
  avatar_customized?: boolean;
  turn_detection_type?: string;
  noise_suppression?: boolean;
  echo_cancellation?: boolean;
  eou_detection?: boolean;
  recognition_language?: string;
  // AI Foundry Playground fields
  response_temperature?: number;
  proactive_engagement?: boolean;
  auto_detect_language?: boolean;
  playback_speed?: number;
  custom_lexicon_enabled?: boolean;
  custom_lexicon_url?: string;
  avatar_enabled?: boolean;
  model_instruction?: string;
}

export type VoiceLiveInstanceUpdate = Partial<VoiceLiveInstanceCreate>;

export interface VoiceLiveInstanceListResponse {
  items: VoiceLiveInstance[];
  total: number;
}

export interface VoiceLiveInstanceAssign {
  hcp_profile_id: string;
}

export interface VoiceLiveInstanceUnassign {
  hcp_profile_id: string;
}
