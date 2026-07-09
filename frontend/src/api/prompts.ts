import apiClient from "./client";
import type {
  AdoptRunRequest,
  OptimizeRequest,
  OptimizeRunResponse,
  OptimizeTextRequest,
  OptimizeTextResponse,
  Prompt,
  PromptCreateRequest,
  PromptMetaUpdateRequest,
  PromptRun,
  PromptSummary,
  PromptUpdateRequest,
  PromptVersion,
} from "@/types/prompt";

export const promptsApi = {
  async list() {
    const { data } = await apiClient.get<PromptSummary[]>("/prompts");
    return data;
  },

  async get(key: string) {
    const { data } = await apiClient.get<Prompt>(`/prompts/${key}`);
    return data;
  },

  async create(payload: PromptCreateRequest) {
    const { data } = await apiClient.post<Prompt>("/prompts", payload);
    return data;
  },

  async versions(key: string) {
    const { data } = await apiClient.get<PromptVersion[]>(`/prompts/${key}/versions`);
    return data;
  },

  async runs(key: string) {
    const { data } = await apiClient.get<PromptRun[]>(`/prompts/${key}/runs`);
    return data;
  },

  async saveVersion(key: string, payload: PromptUpdateRequest) {
    const { data } = await apiClient.put<PromptVersion>(`/prompts/${key}`, payload);
    return data;
  },

  async updateMeta(key: string, payload: PromptMetaUpdateRequest) {
    const { data } = await apiClient.patch<Prompt>(`/prompts/${key}`, payload);
    return data;
  },

  async activateVersion(key: string, versionNo: number) {
    const { data } = await apiClient.post<PromptVersion>(
      `/prompts/${key}/activate/${versionNo}`,
    );
    return data;
  },

  async optimize(key: string, payload: OptimizeRequest) {
    const { data } = await apiClient.post<OptimizeRunResponse>(
      `/prompts/${key}/optimize`,
      payload,
    );
    return data;
  },

  async adoptRun(key: string, payload: AdoptRunRequest) {
    const { data } = await apiClient.post<PromptVersion>(`/prompts/${key}/adopt`, payload);
    return data;
  },

  async optimizeText(payload: OptimizeTextRequest) {
    const { data } = await apiClient.post<OptimizeTextResponse>("/prompts/optimize", payload);
    return data;
  },
};
