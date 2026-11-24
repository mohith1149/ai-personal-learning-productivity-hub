import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, qs } from "./client";

export type ProjectStatus = "active" | "paused" | "completed" | "archived";
export type Origin = "new" | "existing";
export const PROJECT_STATUS_LABEL: Record<ProjectStatus, string> = { active: "Active", paused: "Paused", completed: "Completed", archived: "Archived" };
export const PRIORITY_LABEL: Record<number, string> = { 1: "Urgent", 2: "High", 3: "Medium", 4: "Low" };

export type Progress = { milestones_done: number; milestones_total: number; tasks_done: number; tasks_total: number; percent: number };

export type ProjectSummary = {
  id: number;
  title: string;
  origin: Origin;
  status: ProjectStatus;
  priority: number;
  description: string | null;
  objective: string | null;
  tech_stack: string[];
  repo_url: string | null;
  start_date: string | null;
  target_date: string | null;
  completed_at: string | null;
  last_activity_at: string | null;
  created_at: string;
  progress: Progress;
  minutes_spent: number;
  session_count: number;
  days_active: number;
  overdue: boolean;
};

export type Milestone = {
  id: number;
  title: string;
  description: string | null;
  status: "pending" | "done";
  position: number;
  due_date: string | null;
  completed_at: string | null;
  evidence: string | null;
  overdue: boolean;
};

export type ProjectTask = {
  id: number;
  title: string;
  status: "pending" | "in_progress" | "completed" | "cancelled";
  priority: number;
  due_date: string | null;
  estimated_minutes: number | null;
  completed_at: string | null;
};

export type DevSession = {
  id: number;
  project_id: number;
  date: string;
  minutes: number;
  summary: string;
  milestone_id: number | null;
  task_id: number | null;
  notes: string | null;
  created_at: string;
};

export type ProjectDetail = ProjectSummary & { notes: string | null; milestones: Milestone[]; tasks: ProjectTask[]; sessions: DevSession[] };

export type ProjectInput = {
  title: string;
  origin?: Origin;
  description?: string | null;
  objective?: string | null;
  tech_stack?: string[];
  repo_url?: string | null;
  status?: ProjectStatus;
  priority?: number;
  start_date?: string | null;
  target_date?: string | null;
  notes?: string | null;
};

const ROOT = ["projects"] as const;

export const useProjects = (status: ProjectStatus | "") =>
  useQuery({ queryKey: [...ROOT, "list", status], queryFn: () => api<ProjectSummary[]>(`/projects${qs({ status })}`) });
export const useProject = (id: number) => useQuery({ queryKey: [...ROOT, "detail", id], queryFn: () => api<ProjectDetail>(`/projects/${id}`) });

/** Project numbers depend on tasks too, so task changes refresh the project queries and vice versa. */
function useInvalidating<TVars, TData>(fn: (v: TVars) => Promise<TData>) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => Promise.all([qc.invalidateQueries({ queryKey: ROOT }), qc.invalidateQueries({ queryKey: ["tasks"] })]),
  });
}

export const useCreateProject = () => useInvalidating((body: ProjectInput) => api<ProjectDetail>("/projects", { method: "POST", body }));
export const useUpdateProject = () =>
  useInvalidating(({ id, body }: { id: number; body: Partial<ProjectInput> }) => api<ProjectDetail>(`/projects/${id}`, { method: "PATCH", body }));
export const useDeleteProject = () => useInvalidating((id: number) => api<void>(`/projects/${id}`, { method: "DELETE" }));

export const useAddMilestone = () =>
  useInvalidating(({ projectId, body }: { projectId: number; body: { title: string; description?: string | null; due_date?: string | null } }) =>
    api<ProjectDetail>(`/projects/${projectId}/milestones`, { method: "POST", body }));
export const useUpdateMilestone = () =>
  useInvalidating(({ id, body }: { id: number; body: { title?: string; description?: string | null; due_date?: string | null } }) =>
    api<ProjectDetail>(`/project-milestones/${id}`, { method: "PATCH", body }));
export const useSetMilestoneStatus = () =>
  useInvalidating(({ id, status, evidence }: { id: number; status: "pending" | "done"; evidence?: string | null }) =>
    api<ProjectDetail>(`/project-milestones/${id}/status`, { method: "POST", body: { status, evidence: evidence ?? null } }));
export const useDeleteMilestone = () => useInvalidating((id: number) => api<ProjectDetail>(`/project-milestones/${id}`, { method: "DELETE" }));

export const useAddProjectTask = () =>
  useInvalidating(({ projectId, body }: { projectId: number; body: { title: string; priority?: number; due_date?: string | null; estimated_minutes?: number | null } }) =>
    api<ProjectDetail>(`/projects/${projectId}/tasks`, { method: "POST", body }));
/** Project tasks are normal tasks: their status is changed through the Tasks API. */
export const useSetTaskStatus = () =>
  useInvalidating(({ id, status }: { id: number; status: "pending" | "completed" }) => api<unknown>(`/tasks/${id}`, { method: "PATCH", body: { status } }));

export const useLogSession = () =>
  useInvalidating(({ projectId, body }: { projectId: number; body: { minutes: number; summary: string; date?: string; milestone_id?: number | null; task_id?: number | null; notes?: string | null } }) =>
    api<DevSession>(`/projects/${projectId}/sessions`, { method: "POST", body }));
export const useDeleteSession = () => useInvalidating((id: number) => api<void>(`/project-sessions/${id}`, { method: "DELETE" }));
