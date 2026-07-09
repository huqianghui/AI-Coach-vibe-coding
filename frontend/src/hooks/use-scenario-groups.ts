import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createScenarioGroup,
  createScenarioGroupRun,
  createScenarioGroupRunSession,
  deleteScenarioGroup,
  getActiveScenarioGroups,
  getScenarioGroupRun,
  getScenarioGroups,
  refreshScenarioGroupRunScore,
  transitionScenarioGroupStatus,
  updateScenarioGroup,
} from "@/api/scenario-groups";
import type { ScenarioGroupCreate, ScenarioGroupUpdate } from "@/types/scenario-group";

export function useScenarioGroups(params?: {
  page?: number;
  page_size?: number;
  status?: string;
  search?: string;
}) {
  return useQuery({
    queryKey: ["scenario-groups", params],
    queryFn: () => getScenarioGroups(params),
  });
}

export function useActiveScenarioGroups() {
  return useQuery({
    queryKey: ["scenario-groups", "active"],
    queryFn: getActiveScenarioGroups,
  });
}

export function useScenarioGroupRun(runId: string | undefined) {
  return useQuery({
    queryKey: ["scenario-group-runs", runId],
    queryFn: () => getScenarioGroupRun(runId!),
    enabled: !!runId,
    staleTime: 0,
    refetchOnMount: "always",
    refetchOnWindowFocus: true,
  });
}

export function useCreateScenarioGroup() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: ScenarioGroupCreate) => createScenarioGroup(data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["scenario-groups"] }),
  });
}

export function useUpdateScenarioGroup() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: ScenarioGroupUpdate }) =>
      updateScenarioGroup(id, data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["scenario-groups"] }),
  });
}

export function useTransitionScenarioGroupStatus() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      transitionScenarioGroupStatus(id, status),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["scenario-groups"] }),
  });
}

export function useDeleteScenarioGroup() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteScenarioGroup(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["scenario-groups"] }),
  });
}

export function useCreateScenarioGroupRun() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (groupId: string) => createScenarioGroupRun(groupId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["scenario-group-runs"] }),
  });
}

export function useCreateScenarioGroupRunSession() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      runId,
      runItemId,
      mode,
      retrain,
    }: {
      runId: string;
      runItemId: string;
      mode: string;
      retrain?: boolean;
    }) => createScenarioGroupRunSession(runId, runItemId, mode, retrain),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["scenario-group-runs"] }),
  });
}

export function useRefreshScenarioGroupRunScore() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (runId: string) => refreshScenarioGroupRunScore(runId),
    onSuccess: (run) => {
      queryClient.setQueryData(["scenario-group-runs", run.id], run);
      queryClient.invalidateQueries({ queryKey: ["scenario-group-runs"] });
    },
  });
}
