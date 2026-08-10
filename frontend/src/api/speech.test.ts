import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@/api/client", () => ({
  default: {
    post: vi.fn(),
    get: vi.fn(),
  },
}));

import apiClient from "@/api/client";
import { transcribeAudio, synthesizeSpeech, getSpeechStatus } from "./speech";

describe("transcribeAudio", () => {
  beforeEach(() => vi.clearAllMocks());

  it("sends FormData with audio blob and language query param", async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({
      data: { text: "hello", language: "zh-CN" },
    });
    const blob = new Blob(["audio"], { type: "audio/webm" });
    await transcribeAudio(blob, "en-US");
    expect(apiClient.post).toHaveBeenCalledWith(
      "/speech/transcribe?language=en-US",
      expect.any(FormData),
      { headers: { "Content-Type": "multipart/form-data" } },
    );
  });

  it("uses default language zh-CN", async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({
      data: { text: "你好", language: "zh-CN" },
    });
    const blob = new Blob(["audio"], { type: "audio/webm" });
    await transcribeAudio(blob);
    expect(apiClient.post).toHaveBeenCalledWith(
      "/speech/transcribe?language=zh-CN",
      expect.any(FormData),
      expect.any(Object),
    );
  });

  it("uses a WAV filename and URL-encodes the requested language", async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({
      data: { text: "hello", language: "en US" },
    });
    const blob = new Blob(["wav"], { type: "audio/wav" });

    await transcribeAudio(blob, "en US");

    expect(apiClient.post).toHaveBeenCalledWith(
      "/speech/transcribe?language=en%20US",
      expect.any(FormData),
      expect.any(Object),
    );
    const form = vi.mocked(apiClient.post).mock.calls[0]?.[1] as FormData;
    expect((form.get("audio") as File).name).toBe("recording.wav");
  });

  it("returns transcription response", async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({
      data: { text: "hello doctor", language: "en-US" },
    });
    const result = await transcribeAudio(new Blob(["audio"]), "en-US");
    expect(result).toEqual({ text: "hello doctor", language: "en-US" });
  });

  it("propagates API errors", async () => {
    vi.mocked(apiClient.post).mockRejectedValueOnce(new Error("401"));
    await expect(transcribeAudio(new Blob([]))).rejects.toThrow("401");
  });

  it("maps STT backend failures to a user-friendly message", async () => {
    vi.mocked(apiClient.post).mockRejectedValueOnce({
      isAxiosError: true,
      response: {
        data: {
          code: "STT_TRANSCRIPTION_FAILED",
          message: "Speech transcription failed.",
        },
      },
    });
    await expect(transcribeAudio(new Blob(["audio"]))).rejects.toThrow(
      "语音转写失败，请重试或使用文字输入。",
    );
  });

  it("maps Azure Speech configuration errors to an actionable message", async () => {
    vi.mocked(apiClient.post).mockRejectedValueOnce({
      isAxiosError: true,
      response: {
        data: {
          code: "AZURE_SPEECH_NOT_CONFIGURED",
          message: "Azure Speech requires its own API key and region.",
        },
      },
    });
    await expect(transcribeAudio(new Blob(["audio"]))).rejects.toThrow(
      "Azure Speech 未配置独立的 Key 和区域，请在管理员设置中配置 Speech STT/TTS。",
    );
  });

  it("uses the backend Axios message when no known error code is present", async () => {
    vi.mocked(apiClient.post).mockRejectedValueOnce({
      isAxiosError: true,
      response: { data: { message: "Custom speech failure" } },
    });

    await expect(transcribeAudio(new Blob(["audio"]))).rejects.toThrow(
      "Custom speech failure",
    );
  });

  it("uses the generic fallback for an Axios error without response data", async () => {
    vi.mocked(apiClient.post).mockRejectedValueOnce({ isAxiosError: true });

    await expect(transcribeAudio(new Blob(["audio"]))).rejects.toThrow(
      "语音转写失败，请重试或使用文字输入。",
    );
  });
});

describe("synthesizeSpeech", () => {
  beforeEach(() => vi.clearAllMocks());

  it("sends JSON body with text, language, voice and responseType blob", async () => {
    const audioBlob = new Blob(["audio data"]);
    vi.mocked(apiClient.post).mockResolvedValueOnce({ data: audioBlob });
    await synthesizeSpeech("hello", "en-US", "en-US-JennyNeural");
    expect(apiClient.post).toHaveBeenCalledWith(
      "/speech/synthesize",
      { text: "hello", language: "en-US", voice: "en-US-JennyNeural" },
      { responseType: "blob" },
    );
  });

  it("uses default language zh-CN", async () => {
    vi.mocked(apiClient.post).mockResolvedValueOnce({ data: new Blob([]) });
    await synthesizeSpeech("你好");
    expect(apiClient.post).toHaveBeenCalledWith(
      "/speech/synthesize",
      { text: "你好", language: "zh-CN", voice: undefined },
      { responseType: "blob" },
    );
  });

  it("returns audio blob", async () => {
    const audioBlob = new Blob(["RIFF audio data"]);
    vi.mocked(apiClient.post).mockResolvedValueOnce({ data: audioBlob });
    const result = await synthesizeSpeech("test");
    expect(result).toBe(audioBlob);
  });
});

describe("getSpeechStatus", () => {
  beforeEach(() => vi.clearAllMocks());

  it("calls GET /speech/status", async () => {
    const status = {
      stt_available: true,
      tts_available: true,
      stt_provider: "azure",
      tts_provider: "azure",
    };
    vi.mocked(apiClient.get).mockResolvedValueOnce({ data: status });
    const result = await getSpeechStatus();
    expect(apiClient.get).toHaveBeenCalledWith("/speech/status");
    expect(result).toEqual(status);
  });

  it("propagates errors", async () => {
    vi.mocked(apiClient.get).mockRejectedValueOnce(new Error("Network Error"));
    await expect(getSpeechStatus()).rejects.toThrow("Network Error");
  });
});
