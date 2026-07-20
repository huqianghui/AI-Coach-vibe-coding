/**
 * Integration tests for Voice Live token API using REAL backend server and REAL HCP profiles.
 *
 * These tests call the actual backend API (http://localhost:8000) with real credentials
 * from .env to verify the voice-live token endpoint works correctly with configured HCPs.
 *
 * Prerequisites:
 *   - Backend running on localhost:8000
 *   - Real Azure AI Foundry credentials in backend/.env
 *   - Seeded HCP profiles in database
 *
 * Tests are skipped if backend is not available.
 */
import { describe, it, expect, beforeAll } from "vitest";

const API_BASE = "http://localhost:8000/api/v1";

let accessToken = "";
let adminToken = "";
let backendAvailable = false;

interface VoiceLiveInstanceSummary {
  id: string;
  name: string;
  voice_name: string;
  voice_type: string;
  avatar_character: string;
  avatar_style: string;
  avatar_enabled: boolean;
}

interface HcpProfile {
  id: string;
  name: string;
  agent_id?: string;
  agent_sync_status?: string;
  is_active: boolean;
  // Voice/avatar config now lives on the linked Voice Live Instance --
  // Phase 29 dropped the 14 inline voice/avatar columns from HCP profiles.
  voice_live_instance_id?: string | null;
  voice_live_instance?: VoiceLiveInstanceSummary | null;
}

interface VoiceLiveTokenResponse {
  endpoint: string;
  token: string;
  region: string;
  model: string;
  avatar_enabled: boolean;
  avatar_character: string;
  voice_name: string;
  agent_id?: string | null;
  project_name?: string | null;
  avatar_style: string;
  avatar_customized: boolean;
  voice_type: string;
  voice_temperature: number;
  turn_detection_type: string;
  noise_suppression: boolean;
  echo_cancellation: boolean;
  recognition_language: string;
}

async function checkBackend(): Promise<boolean> {
  try {
    const resp = await fetch(`http://localhost:8000/api/health`, {
      signal: AbortSignal.timeout(3000),
    });
    return resp.ok;
  } catch {
    return false;
  }
}

async function login(username: string, password: string): Promise<string> {
  const resp = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!resp.ok) throw new Error(`Login failed: ${resp.status}`);
  const data = (await resp.json()) as { access_token: string };
  return data.access_token;
}

async function getHcpProfiles(token: string): Promise<{ items: HcpProfile[] }> {
  const resp = await fetch(`${API_BASE}/hcp-profiles?page_size=50`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!resp.ok) throw new Error(`Get HCP profiles failed: ${resp.status}`);
  return resp.json() as Promise<{ items: HcpProfile[] }>;
}

async function getVoiceLiveToken(
  token: string,
  hcpProfileId?: string,
): Promise<VoiceLiveTokenResponse> {
  const url = hcpProfileId
    ? `${API_BASE}/voice-live/token?hcp_profile_id=${hcpProfileId}`
    : `${API_BASE}/voice-live/token`;
  const resp = await fetch(url, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!resp.ok) throw new Error(`Get voice-live token failed: ${resp.status}`);
  return resp.json() as Promise<VoiceLiveTokenResponse>;
}

beforeAll(async () => {
  backendAvailable = await checkBackend();
  if (!backendAvailable) {
    console.warn("[Integration] Backend not available at localhost:8000, skipping real API tests");
    return;
  }

  try {
    accessToken = await login("user1", "user123");
    adminToken = await login("admin", "admin123");
  } catch (e) {
    console.warn("[Integration] Login failed, skipping:", e);
    backendAvailable = false;
  }
});

describe("Voice Live Token API — Real Backend Integration", () => {
  it("voice-live/token endpoint returns valid response structure", async () => {
    if (!backendAvailable) return;

    const tokenData = await getVoiceLiveToken(accessToken);

    // Verify required fields exist
    expect(tokenData.endpoint).toBeTruthy();
    expect(typeof tokenData.endpoint).toBe("string");
    expect(tokenData.token).toBeTruthy();
    expect(typeof tokenData.token).toBe("string");
    expect(typeof tokenData.region).toBe("string");
    expect(typeof tokenData.model).toBe("string");
    expect(typeof tokenData.avatar_enabled).toBe("boolean");
    expect(typeof tokenData.voice_name).toBe("string");
    expect(tokenData.voice_name.length).toBeGreaterThan(0);
  });

  it("endpoint is a valid URL that can be converted to wss://", async () => {
    if (!backendAvailable) return;

    const tokenData = await getVoiceLiveToken(accessToken);

    // Endpoint should be convertible to wss:// for RTClient
    const wsUrl = tokenData.endpoint.replace(/^https?:\/\//, "wss://");
    const url = new URL(wsUrl);
    expect(url.protocol).toBe("wss:");
    expect(url.hostname).toBeTruthy();
    // URL should be a base URL — no path segments like /openai/realtime
    // SDK handles path construction internally
    expect(url.pathname).toBe("/");
  });

  it("voice-live/token with HCP profile returns per-HCP settings", async () => {
    if (!backendAvailable) return;

    // Get HCP profiles (admin only)
    const profiles = await getHcpProfiles(adminToken);
    expect(profiles.items.length).toBeGreaterThan(0);

    const firstProfile = profiles.items[0]!;
    const tokenData = await getVoiceLiveToken(accessToken, firstProfile.id);

    // Per-HCP fields should reflect the profile's configuration
    expect(typeof tokenData.voice_name).toBe("string");
    expect(tokenData.voice_name.length).toBeGreaterThan(0);
    expect(typeof tokenData.avatar_character).toBe("string");
    expect(typeof tokenData.avatar_style).toBe("string");
    expect(typeof tokenData.voice_type).toBe("string");
    expect(typeof tokenData.voice_temperature).toBe("number");
    expect(tokenData.voice_temperature).toBeGreaterThan(0);
    expect(tokenData.voice_temperature).toBeLessThanOrEqual(2);
    expect(typeof tokenData.turn_detection_type).toBe("string");
  });

  it("HCP profile with agent_id returns agent mode token", async () => {
    if (!backendAvailable) return;

    const profiles = await getHcpProfiles(adminToken);

    // Find an HCP with a synced agent
    const agentProfile = profiles.items.find(
      (p) => p.agent_id && p.agent_sync_status === "synced",
    );

    if (!agentProfile) {
      console.warn("[Integration] No HCP with synced agent found, skipping agent mode test");
      return;
    }

    const tokenData = await getVoiceLiveToken(accessToken, agentProfile.id);

    // Agent mode: should have agent_id and project_name in the token
    // Note: agent_id in token depends on system-level agent mode being enabled
    if (tokenData.agent_id) {
      expect(typeof tokenData.agent_id).toBe("string");
      expect(tokenData.agent_id.length).toBeGreaterThan(0);
      if (tokenData.project_name) {
        expect(typeof tokenData.project_name).toBe("string");
      }
      console.info(`[Integration] Agent mode token: agent_id=${tokenData.agent_id}`);
    } else {
      // System might not be in agent mode even though HCP has agent_id
      console.warn("[Integration] HCP has agent but token returned model mode — system not in agent mode");
      expect(typeof tokenData.model).toBe("string");
    }
  });

  it("HCP profile with avatar_enabled returns avatar configuration", async () => {
    if (!backendAvailable) return;

    const profiles = await getHcpProfiles(adminToken);

    // Find an HCP with avatar enabled via its linked Voice Live Instance
    const avatarProfile = profiles.items.find(
      (p) =>
        p.voice_live_instance?.avatar_character &&
        p.voice_live_instance.avatar_character.length > 0,
    );

    if (!avatarProfile) {
      console.warn("[Integration] No HCP with avatar configured found, skipping avatar test");
      return;
    }

    const tokenData = await getVoiceLiveToken(accessToken, avatarProfile.id);

    // If avatar is enabled system-wide, verify avatar configuration fields
    if (tokenData.avatar_enabled) {
      expect(typeof tokenData.avatar_character).toBe("string");
      expect(typeof tokenData.avatar_style).toBe("string");
      expect(typeof tokenData.avatar_customized).toBe("boolean");
      console.info(`[Integration] Avatar config: character="${tokenData.avatar_character}", style="${tokenData.avatar_style}"`);
    }
  });

  it("all active HCP profiles return valid voice-live tokens", async () => {
    if (!backendAvailable) return;

    const profiles = await getHcpProfiles(adminToken);
    const activeProfiles = profiles.items.filter((p) => p.is_active);
    expect(activeProfiles.length).toBeGreaterThan(0);

    for (const profile of activeProfiles) {
      const tokenData = await getVoiceLiveToken(accessToken, profile.id);

      // Every active HCP should produce a valid token
      expect(tokenData.endpoint).toBeTruthy();
      expect(tokenData.token).toBeTruthy();
      expect(tokenData.voice_name).toBeTruthy();

      // Log mode info for debugging
      const mode = tokenData.avatar_enabled && tokenData.agent_id
        ? "digital_human_realtime_agent"
        : tokenData.avatar_enabled
          ? "digital_human_realtime_model"
          : tokenData.agent_id
            ? "voice_realtime_agent"
            : "voice_realtime_model";
      console.info(`[Integration] HCP "${profile.name}" → mode: ${mode}`);
    }
  });

  it("voice-live/status endpoint returns availability info", async () => {
    if (!backendAvailable) return;

    const resp = await fetch(`${API_BASE}/voice-live/status`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    expect(resp.ok).toBe(true);

    const status = (await resp.json()) as {
      voice_live_available: boolean;
      avatar_available: boolean;
      voice_name: string;
      avatar_character: string;
    };

    expect(typeof status.voice_live_available).toBe("boolean");
    expect(typeof status.avatar_available).toBe("boolean");
    expect(typeof status.voice_name).toBe("string");
    expect(typeof status.avatar_character).toBe("string");

    // With real .env credentials, voice_live should be available
    if (status.voice_live_available) {
      console.info("[Integration] Voice Live is available");
    } else {
      console.warn("[Integration] Voice Live is NOT available — check Azure credentials");
    }
  });

  it("token endpoint validates modelOrAgent format for RTClient construction", async () => {
    if (!backendAvailable) return;

    const profiles = await getHcpProfiles(adminToken);
    const firstProfile = profiles.items[0]!;
    const tokenData = await getVoiceLiveToken(accessToken, firstProfile.id);

    // Simulate what the frontend does when constructing RTClient options.
    // GA api-version (D-02) — azure-ai-voicelive SDK 1.3.0, do not revert to a
    // preview literal (see backend/app/config.py voice_live_api_version).
    const GA_API_VERSION = "2026-07-15";
    if (tokenData.agent_id) {
      // Agent mode: modelOrAgent should be { agentId, projectName }
      const options = {
        modelOrAgent: {
          agentId: tokenData.agent_id,
          projectName: tokenData.project_name || "",
        },
        apiVersion: GA_API_VERSION,
      };
      expect(options.modelOrAgent.agentId).toBeTruthy();
      expect(typeof options.modelOrAgent.projectName).toBe("string");
      expect(options.apiVersion).toBe(GA_API_VERSION);
    } else {
      // Model mode: modelOrAgent should be the model string
      const options = {
        modelOrAgent: tokenData.model,
        apiVersion: GA_API_VERSION,
      };
      expect(typeof options.modelOrAgent).toBe("string");
      expect(options.apiVersion).toBe(GA_API_VERSION);
    }
  });

  it("session config built from token matches expected structure", async () => {
    if (!backendAvailable) return;

    const tokenData = await getVoiceLiveToken(accessToken);

    // Simulate building session config as in use-voice-live.ts
    const sessionConfig: Record<string, unknown> = {
      modalities: ["text", "audio"],
      voice: {
        type: tokenData.voice_type || "azure-standard",
        name: tokenData.voice_name,
        temperature: tokenData.voice_temperature ?? 0.9,
      },
      input_audio_transcription: {
        model: "azure-fast-transcription",
        language: tokenData.recognition_language === "auto" ? "zh-CN" : tokenData.recognition_language,
      },
      turn_detection: {
        type: tokenData.turn_detection_type || "server_vad",
      },
    };

    // Validate structure
    expect(sessionConfig.modalities).toEqual(["text", "audio"]);
    const voice = sessionConfig.voice as Record<string, unknown>;
    expect(voice.name).toBeTruthy();
    expect(typeof voice.temperature).toBe("number");

    // Avatar config if enabled
    if (tokenData.avatar_enabled) {
      sessionConfig["avatar"] = {
        character: tokenData.avatar_character,
        style: tokenData.avatar_style || "casual",
        customized: tokenData.avatar_customized || false,
        video: {
          codec: "h264",
          crop: { top_left: [560, 0], bottom_right: [1360, 1080] },
        },
      };
      const avatar = sessionConfig["avatar"] as Record<string, unknown>;
      expect(typeof avatar.character).toBe("string");
      expect(typeof avatar.style).toBe("string");
    }

    // Noise suppression
    if (tokenData.noise_suppression) {
      sessionConfig["input_audio_noise_reduction"] = {
        type: "azure_deep_noise_suppression",
      };
    }

    // Echo cancellation
    if (tokenData.echo_cancellation) {
      sessionConfig["input_audio_echo_cancellation"] = {
        type: "server_echo_cancellation",
      };
    }
  });
});
