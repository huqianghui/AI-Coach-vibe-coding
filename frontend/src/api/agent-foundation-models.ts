import apiClient from "@/api/client";
import type { AgentFoundationModelsResponse } from "@/types/agent-foundation-model";

export async function fetchAgentFoundationModels(): Promise<AgentFoundationModelsResponse> {
  const response = await apiClient.get<AgentFoundationModelsResponse>(
    "/agent-foundation-models",
  );
  return response.data;
}
