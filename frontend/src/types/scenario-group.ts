import type { Scenario } from "./scenario";

export interface ScenarioGroupItem {
  id: string;
  groupId: string;
  scenarioId: string;
  weight: number;
  sortOrder: number;
  scenario?: Scenario | null;
}

export interface ScenarioGroup {
  id: string;
  name: string;
  description: string;
  tags: string[];
  status: "draft" | "active" | "archived";
  passThreshold: number;
  createdBy: string;
  items: ScenarioGroupItem[];
  createdAt: string;
  updatedAt: string;
}

export interface ScenarioGroupItemCreate {
  scenarioId: string;
  weight: number;
  sortOrder?: number;
}

export interface ScenarioGroupCreate {
  name: string;
  description?: string;
  tags?: string[];
  passThreshold?: number;
  items: ScenarioGroupItemCreate[];
}

export interface ScenarioGroupUpdate {
  name?: string;
  description?: string;
  tags?: string[];
  passThreshold?: number;
  items?: ScenarioGroupItemCreate[];
}

export interface ScenarioGroupRunItem {
  id: string;
  runId: string;
  groupItemId: string;
  scenarioId: string;
  sessionId: string | null;
  status: "not_started" | "in_progress" | "completed" | "scored";
  weight: number;
  sortOrder: number;
  score: number | null;
  passed: boolean | null;
  scenario?: Scenario | null;
}

export interface ScenarioGroupRun {
  id: string;
  userId: string;
  groupId: string;
  groupName: string | null;
  status: "created" | "in_progress" | "completed" | "scored";
  startedAt: string | null;
  completedAt: string | null;
  overallScore: number | null;
  passed: boolean | null;
  items: ScenarioGroupRunItem[];
  createdAt: string;
  updatedAt: string;
}
