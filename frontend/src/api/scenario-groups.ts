import apiClient from "./client";
import type { CoachingSession } from "@/types/session";
import type {
  ScenarioGroup,
  ScenarioGroupCreate,
  ScenarioGroupItem,
  ScenarioGroupRun,
  ScenarioGroupRunItem,
  ScenarioGroupUpdate,
} from "@/types/scenario-group";

interface ScenarioGroupItemApi {
  id: string;
  group_id: string;
  scenario_id: string;
  weight: number;
  sort_order: number;
  scenario?: ScenarioGroupItem["scenario"];
}

interface ScenarioGroupApi {
  id: string;
  name: string;
  description: string;
  tags: string[];
  status: "draft" | "active" | "archived";
  pass_threshold: number;
  created_by: string;
  items: ScenarioGroupItemApi[];
  created_at: string;
  updated_at: string;
}

interface ScenarioGroupRunItemApi {
  id: string;
  run_id: string;
  group_item_id: string;
  scenario_id: string;
  session_id: string | null;
  status: "not_started" | "in_progress" | "completed" | "scored";
  weight: number;
  sort_order: number;
  score: number | null;
  passed: boolean | null;
  scenario?: ScenarioGroupRunItem["scenario"];
}

interface ScenarioGroupRunApi {
  id: string;
  user_id: string;
  group_id: string;
  group_name: string | null;
  status: "created" | "in_progress" | "completed" | "scored";
  started_at: string | null;
  completed_at: string | null;
  overall_score: number | null;
  passed: boolean | null;
  items: ScenarioGroupRunItemApi[];
  created_at: string;
  updated_at: string;
}

function toGroupItem(raw: ScenarioGroupItemApi): ScenarioGroupItem {
  return {
    id: raw.id,
    groupId: raw.group_id,
    scenarioId: raw.scenario_id,
    weight: raw.weight,
    sortOrder: raw.sort_order,
    scenario: raw.scenario,
  };
}

function toGroup(raw: ScenarioGroupApi): ScenarioGroup {
  return {
    id: raw.id,
    name: raw.name,
    description: raw.description,
    tags: raw.tags,
    status: raw.status,
    passThreshold: raw.pass_threshold,
    createdBy: raw.created_by,
    items: raw.items.map(toGroupItem),
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
  };
}

function toRunItem(raw: ScenarioGroupRunItemApi): ScenarioGroupRunItem {
  return {
    id: raw.id,
    runId: raw.run_id,
    groupItemId: raw.group_item_id,
    scenarioId: raw.scenario_id,
    sessionId: raw.session_id,
    status: raw.status,
    weight: raw.weight,
    sortOrder: raw.sort_order,
    score: raw.score,
    passed: raw.passed,
    scenario: raw.scenario,
  };
}

function toRun(raw: ScenarioGroupRunApi): ScenarioGroupRun {
  return {
    id: raw.id,
    userId: raw.user_id,
    groupId: raw.group_id,
    groupName: raw.group_name,
    status: raw.status,
    startedAt: raw.started_at,
    completedAt: raw.completed_at,
    overallScore: raw.overall_score,
    passed: raw.passed,
    items: raw.items.map(toRunItem),
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
  };
}

function toGroupPayload(data: ScenarioGroupCreate | ScenarioGroupUpdate) {
  return {
    name: data.name,
    description: data.description,
    tags: data.tags,
    pass_threshold: data.passThreshold,
    items: data.items?.map((item) => ({
      scenario_id: item.scenarioId,
      weight: item.weight,
      sort_order: item.sortOrder ?? 0,
    })),
  };
}

export async function getScenarioGroups(params?: {
  page?: number;
  page_size?: number;
  status?: string;
  search?: string;
}) {
  const { data } = await apiClient.get<{
    items: ScenarioGroupApi[];
    total: number;
    page: number;
    page_size: number;
    total_pages: number;
  }>("/scenario-groups", { params });
  return { ...data, items: data.items.map(toGroup) };
}

export async function getActiveScenarioGroups() {
  const { data } = await apiClient.get<ScenarioGroupApi[]>("/scenario-groups/active");
  return data.map(toGroup);
}

export async function createScenarioGroup(group: ScenarioGroupCreate) {
  const { data } = await apiClient.post<ScenarioGroupApi>(
    "/scenario-groups",
    toGroupPayload(group),
  );
  return toGroup(data);
}

export async function updateScenarioGroup(id: string, group: ScenarioGroupUpdate) {
  const { data } = await apiClient.put<ScenarioGroupApi>(
    `/scenario-groups/${id}`,
    toGroupPayload(group),
  );
  return toGroup(data);
}

export async function transitionScenarioGroupStatus(id: string, status: string) {
  const { data } = await apiClient.post<ScenarioGroupApi>(
    `/scenario-groups/${id}/transition`,
    { status },
  );
  return toGroup(data);
}

export async function deleteScenarioGroup(id: string) {
  await apiClient.delete(`/scenario-groups/${id}`);
}

export async function createScenarioGroupRun(groupId: string) {
  const { data } = await apiClient.post<ScenarioGroupRunApi>(
    "/scenario-groups/runs",
    null,
    { params: { group_id: groupId } },
  );
  return toRun(data);
}

export async function getScenarioGroupRun(runId: string) {
  const { data } = await apiClient.get<ScenarioGroupRunApi>(
    `/scenario-groups/runs/${runId}`,
  );
  return toRun(data);
}

export async function createScenarioGroupRunSession(
  runId: string,
  runItemId: string,
  mode: string,
  retrain = false,
) {
  const { data } = await apiClient.post<CoachingSession>(
    `/scenario-groups/runs/${runId}/items/${runItemId}/session`,
    { mode, retrain },
  );
  return data;
}

export async function refreshScenarioGroupRunScore(runId: string) {
  const { data } = await apiClient.post<ScenarioGroupRunApi>(
    `/scenario-groups/runs/${runId}/refresh-score`,
  );
  return toRun(data);
}
