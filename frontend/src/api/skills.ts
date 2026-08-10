import apiClient from "./client";
import type {
  PaginatedSkills,
  Skill,
  SkillCreate,
  SkillFoundryPortalUrlResponse,
  SkillResource,
  SkillUpdate,
  StructureCheckResult,
  QualityEvaluation,
  SkillEvaluationSummary,
  ResourceType,
} from "@/types/skill";

// ---------------------------------------------------------------------------
// Skill CRUD
// ---------------------------------------------------------------------------

export async function getSkills(params?: {
  page?: number;
  page_size?: number;
  status?: string;
  product?: string;
  search?: string;
}): Promise<PaginatedSkills> {
  const { data } = await apiClient.get<PaginatedSkills>("/skills", { params });
  return data;
}

export async function getPublishedSkills(params?: {
  page?: number;
  page_size?: number;
  search?: string;
}): Promise<PaginatedSkills> {
  const { data } = await apiClient.get<PaginatedSkills>("/skills/published", {
    params,
  });
  return data;
}

export async function getSkill(id: string): Promise<Skill> {
  const { data } = await apiClient.get<Skill>(`/skills/${id}`);
  return data;
}

export async function createSkill(payload: SkillCreate): Promise<Skill> {
  const { data } = await apiClient.post<Skill>("/skills", payload);
  return data;
}

export async function updateSkill(
  id: string,
  payload: SkillUpdate,
): Promise<Skill> {
  const { data } = await apiClient.put<Skill>(`/skills/${id}`, payload);
  return data;
}

export async function deleteSkill(id: string): Promise<void> {
  await apiClient.delete(`/skills/${id}`);
}

// ---------------------------------------------------------------------------
// Lifecycle transitions
// ---------------------------------------------------------------------------

export async function publishSkill(id: string): Promise<Skill> {
  const { data } = await apiClient.post<Skill>(`/skills/${id}/publish`);
  return data;
}

export async function archiveSkill(id: string): Promise<Skill> {
  const { data } = await apiClient.post<Skill>(`/skills/${id}/archive`);
  return data;
}

export async function restoreSkill(id: string): Promise<Skill> {
  const { data } = await apiClient.post<Skill>(`/skills/${id}/restore`);
  return data;
}

export async function createNewVersion(id: string): Promise<Skill> {
  const { data } = await apiClient.post<Skill>(`/skills/${id}/new-version`);
  return data;
}

export async function retryFoundrySync(id: string): Promise<Skill> {
  const { data } = await apiClient.post<Skill>(`/skills/${id}/foundry-sync`);
  return data;
}

export interface BatchFoundrySyncResult {
  synced: number;
  failed: number;
  total: number;
}

export async function batchFoundrySync(): Promise<BatchFoundrySyncResult> {
  const { data } = await apiClient.post<BatchFoundrySyncResult>(
    "/skills/batch-foundry-sync",
  );
  return data;
}

export async function getSkillFoundryPortalUrl(
  id: string,
): Promise<SkillFoundryPortalUrlResponse> {
  const { data } = await apiClient.get<SkillFoundryPortalUrlResponse>(
    `/skills/${id}/foundry-portal-url`,
  );
  return data;
}

export async function createSkillFromMaterials(
  materialIds: string[],
  name?: string,
  product?: string,
): Promise<{ id: string; status: string; method?: string; materials_copied: number }> {
  const { data } = await apiClient.post<{
    id: string;
    status: string;
    method?: string;
    materials_copied: number;
  }>("/skills/create-from-agent", {
    material_ids: materialIds,
    ...(name && { name }),
    ...(product && { product }),
  });
  return data;
}

// ---------------------------------------------------------------------------
// Conversion
// ---------------------------------------------------------------------------

export async function startConversion(id: string): Promise<Skill> {
  const { data } = await apiClient.post<Skill>(`/skills/${id}/convert`);
  return data;
}

export async function retryConversion(id: string): Promise<Skill> {
  const { data } = await apiClient.post<Skill>(`/skills/${id}/retry-conversion`);
  return data;
}

export interface ConversionProgressStep {
  step: number;
  name: string;
  status: "pending" | "in_progress" | "completed";
}

export interface ConversionProgressInfo {
  current_step: number;
  total_steps: number;
  step_name: string;
  steps: ConversionProgressStep[];
}

export interface ConversionStatusResponse {
  status: string;
  error: string | null;
  progress?: ConversionProgressInfo;
}

export async function getConversionStatus(
  id: string,
): Promise<ConversionStatusResponse> {
  const { data } = await apiClient.get<ConversionStatusResponse>(
    `/skills/${id}/conversion-status`,
  );
  return data;
}

export async function uploadAndConvert(
  id: string,
  files: File[],
): Promise<Skill> {
  const formData = new FormData();
  for (const file of files) {
    formData.append("files", file);
  }
  const { data } = await apiClient.post<Skill>(
    `/skills/${id}/upload-and-convert`,
    formData,
    { headers: { "Content-Type": "multipart/form-data" } },
  );
  return data;
}

// ---------------------------------------------------------------------------
// Quality gates
// ---------------------------------------------------------------------------

export async function checkStructure(
  id: string,
): Promise<StructureCheckResult> {
  const { data } = await apiClient.post<StructureCheckResult>(
    `/skills/${id}/check-structure`,
  );
  return data;
}

export async function evaluateQuality(
  id: string,
): Promise<QualityEvaluation> {
  const { data } = await apiClient.post<QualityEvaluation>(
    `/skills/${id}/evaluate-quality`,
  );
  return data;
}

export async function getEvaluation(id: string): Promise<SkillEvaluationSummary> {
  const { data } = await apiClient.get<SkillEvaluationSummary>(
    `/skills/${id}/evaluation`,
  );
  return data;
}

// ---------------------------------------------------------------------------
// SOP regeneration
// ---------------------------------------------------------------------------

export async function regenerateSop(
  id: string,
  feedback: string,
): Promise<Skill> {
  const { data } = await apiClient.post<Skill>(
    `/skills/${id}/regenerate-sop`,
    { feedback },
  );
  return data;
}

// ---------------------------------------------------------------------------
// Resources
// ---------------------------------------------------------------------------

export async function uploadResources(
  id: string,
  files: File[],
  resourceType: ResourceType,
): Promise<SkillResource[]> {
  const results: SkillResource[] = [];
  for (const file of files) {
    const formData = new FormData();
    formData.append("file", file);
    const { data } = await apiClient.post<SkillResource>(
      `/skills/${id}/resources`,
      formData,
      {
        headers: { "Content-Type": "multipart/form-data" },
        params: { resource_type: resourceType },
      },
    );
    results.push(data);
  }
  return results;
}

export async function deleteResource(
  skillId: string,
  resourceId: string,
): Promise<void> {
  await apiClient.delete(`/skills/${skillId}/resources/${resourceId}`);
}

export async function downloadResource(
  skillId: string,
  resourceId: string,
  filename: string,
): Promise<void> {
  const { data } = await apiClient.get<Blob>(
    `/skills/${skillId}/resources/${resourceId}/download`,
    { responseType: "blob" },
  );
  const url = URL.createObjectURL(data);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}

// ---------------------------------------------------------------------------
// Import / Export
// ---------------------------------------------------------------------------

export async function exportSkillZip(id: string): Promise<Blob> {
  const { data } = await apiClient.get<Blob>(`/skills/${id}/export`, {
    responseType: "blob",
  });
  return data;
}

export async function downloadSkillZip(
  id: string,
  skillName?: string,
): Promise<void> {
  const { data, headers } = await apiClient.get(`/skills/${id}/export`, {
    responseType: "blob",
  });
  const disposition = (headers["content-disposition"] as string) ?? "";
  const filenameMatch = disposition.match(/filename="?([^";\s]+)"?/);
  const filename = filenameMatch?.[1] ?? `${skillName ?? "skill"}.zip`;

  const url = URL.createObjectURL(data as Blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}

export async function importSkillZip(file: File): Promise<Skill> {
  const formData = new FormData();
  formData.append("file", file);
  const { data } = await apiClient.post<Skill>("/skills/import", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}
