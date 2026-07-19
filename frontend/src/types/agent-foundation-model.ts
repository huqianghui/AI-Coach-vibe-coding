export interface AgentFoundationModelInfo {
  id: string;
  label: string;
}

export interface AgentFoundationModelsResponse {
  models: AgentFoundationModelInfo[];
  stale: boolean;
  error: string | null;
}
