// Prompt management types — mirror backend app/schemas/prompt.py

export interface PromptVersion {
  id: string;
  template_id: string;
  version_no: number;
  content: string;
  source: string; // seed | manual | optimized | iterate
  parent_version_id: string | null;
  note: string;
  created_by: string | null;
  is_active: boolean;
  created_at: string;
}

export interface PromptSummary {
  key: string;
  name: string;
  category: string;
  is_system: boolean;
  active_version_no: number | null;
  updated_at: string;
  last_optimized_at: string | null;
}

export interface Prompt {
  key: string;
  name: string;
  category: string;
  description: string;
  is_system: boolean;
  variables: string[];
  active_version: PromptVersion | null;
}

export interface PromptRun {
  id: string;
  template_id: string;
  base_version_id: string | null;
  mode: string; // system | user | iterate
  optimizer_template: string | null;
  requirements: string | null;
  result_content: string;
  model: string;
  status: string; // success | error
  error_message: string | null;
  resulting_version_id: string | null;
  created_by: string | null;
  created_at: string;
}

export type OptimizeMode = "system" | "user" | "iterate";

export interface PromptUpdateRequest {
  content: string;
  note?: string;
}

export interface PromptCreateRequest {
  key: string;
  name: string;
  content: string;
  category?: string;
  description?: string;
  variables?: string[];
  is_system?: boolean;
}

export interface PromptMetaUpdateRequest {
  name?: string;
  category?: string;
  description?: string;
  variables?: string[];
  is_system?: boolean;
}

export interface OptimizeRequest {
  mode: OptimizeMode;
  requirements?: string | null;
  template?: string | null;
}

export interface OptimizeRunResponse {
  run_id: string;
  optimized_prompt: string;
}

export interface AdoptRunRequest {
  run_id: string;
  note?: string;
}

// Stateless optimization (no persistence) — POST /prompts/optimize.
// Used by the standalone prompt optimizer page for per-entity prompts.
export interface OptimizeTextRequest {
  prompt: string;
  mode: OptimizeMode;
  requirements?: string | null;
  template?: string | null;
}

export interface OptimizeTextResponse {
  optimized_prompt: string;
}
