import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  archiveSkill,
  batchFoundrySync,
  checkStructure,
  createNewVersion,
  createSkill,
  createSkillFromMaterials,
  deleteSkill,
  evaluateQuality,
  exportSkillZip,
  getConversionStatus,
  getEvaluation,
  getPublishedSkills,
  getSkill,
  getSkills,
  importSkillZip,
  publishSkill,
  regenerateSop,
  restoreSkill,
  retryConversion,
  retryFoundrySync,
  startConversion,
  updateSkill,
  uploadAndConvert,
  uploadResources,
  deleteResource,
} from "@/api/skills";
import type {
  ResourceType,
  SkillCreate,
  SkillUpdate,
} from "@/types/skill";

// ---------------------------------------------------------------------------
// Query-key factory (disciplined cache invalidation for 15+ hooks)
// ---------------------------------------------------------------------------

export const skillKeys = {
  all: ["skills"] as const,
  lists: () => [...skillKeys.all, "list"] as const,
  list: (params: Record<string, unknown>) =>
    [...skillKeys.lists(), params] as const,
  published: (params?: Record<string, unknown>) =>
    [...skillKeys.all, "published", params] as const,
  details: () => [...skillKeys.all, "detail"] as const,
  detail: (id: string) => [...skillKeys.details(), id] as const,
  conversion: (id: string) =>
    [...skillKeys.detail(id), "conversion"] as const,
  evaluation: (id: string) =>
    [...skillKeys.detail(id), "evaluation"] as const,
};

// ---------------------------------------------------------------------------
// Queries
// ---------------------------------------------------------------------------

export function useSkills(params?: {
  page?: number;
  page_size?: number;
  status?: string;
  product?: string;
  search?: string;
}) {
  return useQuery({
    queryKey: skillKeys.list(params ?? {}),
    queryFn: () => getSkills(params),
  });
}

export function usePublishedSkills(params?: {
  page?: number;
  page_size?: number;
  search?: string;
}) {
  return useQuery({
    queryKey: skillKeys.published(params),
    queryFn: () => getPublishedSkills(params),
  });
}

export function useSkill(id: string | undefined) {
  return useQuery({
    queryKey: skillKeys.detail(id ?? ""),
    queryFn: () => getSkill(id!),
    enabled: !!id,
  });
}

export function useConversionStatus(id: string, enabled: boolean) {
  return useQuery({
    queryKey: skillKeys.conversion(id),
    queryFn: () => getConversionStatus(id),
    enabled,
    refetchInterval: enabled ? 3000 : false,
  });
}

export function useSkillEvaluation(id: string | undefined) {
  return useQuery({
    queryKey: skillKeys.evaluation(id ?? ""),
    queryFn: () => getEvaluation(id!),
    enabled: !!id,
  });
}

// ---------------------------------------------------------------------------
// Mutations — CRUD
// ---------------------------------------------------------------------------

export function useCreateSkill() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: SkillCreate) => createSkill(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: skillKeys.all });
    },
  });
}

export function useCreateSkillFromMaterials() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (args: { materialIds: string[]; name?: string; product?: string }) =>
      createSkillFromMaterials(args.materialIds, args.name, args.product),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: skillKeys.all });
    },
  });
}

export function useUpdateSkill() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (args: { id: string; data: SkillUpdate }) =>
      updateSkill(args.id, args.data),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: skillKeys.detail(variables.id),
      });
      queryClient.invalidateQueries({ queryKey: skillKeys.lists() });
    },
  });
}

export function useDeleteSkill() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteSkill(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: skillKeys.all });
    },
  });
}

// ---------------------------------------------------------------------------
// Mutations — Lifecycle
// ---------------------------------------------------------------------------

export function usePublishSkill() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      // Backend handles draft → review → published automatically.
      return publishSkill(id);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: skillKeys.all });
    },
  });
}

export function useArchiveSkill() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => archiveSkill(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: skillKeys.all });
    },
  });
}

export function useRestoreSkill() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => restoreSkill(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: skillKeys.all });
    },
  });
}

export function useCreateNewVersion() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => createNewVersion(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: skillKeys.all });
    },
  });
}

export function useRetryFoundrySync() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => retryFoundrySync(id),
    onSuccess: (_data, id) => {
      queryClient.invalidateQueries({ queryKey: skillKeys.detail(id) });
      queryClient.invalidateQueries({ queryKey: skillKeys.lists() });
    },
  });
}

export function useBatchFoundrySync() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => batchFoundrySync(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: skillKeys.all });
    },
  });
}

// ---------------------------------------------------------------------------
// Mutations — Conversion
// ---------------------------------------------------------------------------

export function useStartConversion() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => startConversion(id),
    onSuccess: (_data, id) => {
      queryClient.invalidateQueries({ queryKey: skillKeys.detail(id) });
      queryClient.invalidateQueries({ queryKey: skillKeys.conversion(id) });
    },
  });
}

export function useRetryConversion() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => retryConversion(id),
    onSuccess: (_data, id) => {
      queryClient.invalidateQueries({ queryKey: skillKeys.detail(id) });
      queryClient.invalidateQueries({ queryKey: skillKeys.conversion(id) });
    },
  });
}

export function useUploadAndConvert() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (args: { id: string; files: File[] }) =>
      uploadAndConvert(args.id, args.files),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: skillKeys.detail(variables.id),
      });
      queryClient.invalidateQueries({
        queryKey: skillKeys.conversion(variables.id),
      });
    },
  });
}

// ---------------------------------------------------------------------------
// Mutations — Quality
// ---------------------------------------------------------------------------

export function useCheckStructure() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => checkStructure(id),
    onSuccess: (_data, id) => {
      queryClient.invalidateQueries({ queryKey: skillKeys.detail(id) });
      queryClient.invalidateQueries({ queryKey: skillKeys.evaluation(id) });
    },
  });
}

export function useEvaluateQuality() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => evaluateQuality(id),
    onSuccess: (_data, id) => {
      queryClient.invalidateQueries({ queryKey: skillKeys.detail(id) });
      queryClient.invalidateQueries({ queryKey: skillKeys.evaluation(id) });
    },
  });
}

// ---------------------------------------------------------------------------
// Mutations — SOP regeneration
// ---------------------------------------------------------------------------

export function useRegenerateSop() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (args: { id: string; feedback: string }) =>
      regenerateSop(args.id, args.feedback),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: skillKeys.detail(variables.id),
      });
    },
  });
}

// ---------------------------------------------------------------------------
// Mutations — Resources
// ---------------------------------------------------------------------------

export function useUploadResources() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (args: {
      id: string;
      files: File[];
      resourceType: ResourceType;
    }) => uploadResources(args.id, args.files, args.resourceType),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: skillKeys.detail(variables.id),
      });
    },
  });
}

export function useDeleteResource() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (args: { skillId: string; resourceId: string }) =>
      deleteResource(args.skillId, args.resourceId),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: skillKeys.detail(variables.skillId),
      });
    },
  });
}

// ---------------------------------------------------------------------------
// Mutations — Import / Export
// ---------------------------------------------------------------------------

export function useExportSkillZip() {
  return useMutation({
    mutationFn: (id: string) => exportSkillZip(id),
  });
}

export function useImportSkillZip() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => importSkillZip(file),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: skillKeys.all });
    },
  });
}
