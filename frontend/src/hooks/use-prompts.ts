import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { promptsApi } from "@/api/prompts";
import type {
  AdoptRunRequest,
  OptimizeRequest,
  OptimizeTextRequest,
  PromptCreateRequest,
  PromptMetaUpdateRequest,
  PromptUpdateRequest,
} from "@/types/prompt";

const PROMPTS_KEY = "prompts";

export function usePrompts() {
  return useQuery({
    queryKey: [PROMPTS_KEY],
    queryFn: () => promptsApi.list(),
  });
}

export function usePrompt(key: string | undefined) {
  return useQuery({
    queryKey: [PROMPTS_KEY, key],
    queryFn: () => promptsApi.get(key!),
    enabled: !!key,
  });
}

export function useCreatePrompt() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: PromptCreateRequest) => promptsApi.create(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [PROMPTS_KEY] });
    },
  });
}

export function usePromptVersions(key: string | undefined) {
  return useQuery({
    queryKey: [PROMPTS_KEY, key, "versions"],
    queryFn: () => promptsApi.versions(key!),
    enabled: !!key,
  });
}

export function usePromptRuns(key: string | undefined) {
  return useQuery({
    queryKey: [PROMPTS_KEY, key, "runs"],
    queryFn: () => promptsApi.runs(key!),
    enabled: !!key,
  });
}

function useInvalidatePrompt(key: string | undefined) {
  const queryClient = useQueryClient();
  return () => {
    queryClient.invalidateQueries({ queryKey: [PROMPTS_KEY] });
    if (key) {
      queryClient.invalidateQueries({ queryKey: [PROMPTS_KEY, key] });
      queryClient.invalidateQueries({ queryKey: [PROMPTS_KEY, key, "versions"] });
      queryClient.invalidateQueries({ queryKey: [PROMPTS_KEY, key, "runs"] });
    }
  };
}

export function useSaveVersion(key: string | undefined) {
  const invalidate = useInvalidatePrompt(key);
  return useMutation({
    mutationFn: (payload: PromptUpdateRequest) => promptsApi.saveVersion(key!, payload),
    onSuccess: invalidate,
  });
}

export function useUpdatePromptMeta(key: string | undefined) {
  const invalidate = useInvalidatePrompt(key);
  return useMutation({
    mutationFn: (payload: PromptMetaUpdateRequest) => promptsApi.updateMeta(key!, payload),
    onSuccess: invalidate,
  });
}

export function useActivateVersion(key: string | undefined) {
  const invalidate = useInvalidatePrompt(key);
  return useMutation({
    mutationFn: (versionNo: number) => promptsApi.activateVersion(key!, versionNo),
    onSuccess: invalidate,
  });
}

export function useOptimizePrompt(key: string | undefined) {
  const invalidate = useInvalidatePrompt(key);
  return useMutation({
    mutationFn: (payload: OptimizeRequest) => promptsApi.optimize(key!, payload),
    onSuccess: invalidate,
  });
}

export function useAdoptRun(key: string | undefined) {
  const invalidate = useInvalidatePrompt(key);
  return useMutation({
    mutationFn: (payload: AdoptRunRequest) => promptsApi.adoptRun(key!, payload),
    onSuccess: invalidate,
  });
}

// Stateless optimization for per-entity prompts (rubric, conference audience).
// Optimizes the passed content without touching the prompt registry.
export function useOptimizeText() {
  return useMutation({
    mutationFn: (payload: OptimizeTextRequest) => promptsApi.optimizeText(payload),
  });
}
