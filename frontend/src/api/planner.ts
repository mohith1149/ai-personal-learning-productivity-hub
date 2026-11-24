import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, qs } from "./client";

export type Kind = "task" | "lesson" | "video" | "topic" | "habit" | "project";
export type ItemStatus = "pending" | "overdue" | "completed" | "excused";

export type PlanItem = {
  key: string;
  kind: Kind;
  ref_id: number;
  title: string;
  subtitle: string | null;
  status: ItemStatus;
  due_date: string | null;
  minutes: number | null;
  excuse_reason: string | null;
  can_complete: boolean;
  can_reschedule: boolean;
  can_excuse: boolean;
  link: string;
  url: string | null;
};

export type DaySummary = {
  total: number;
  completed: number;
  pending: number;
  overdue: number;
  excused: number;
  percent: number;
  study_minutes: number;
  dev_minutes: number;
  by_kind: { kind: Kind; total: number; completed: number }[];
};

export type DayPlan = { date: string; is_today: boolean; items: PlanItem[]; summary: DaySummary };

export const KIND_LABEL: Record<Kind, string> = { task: "Task", lesson: "Lesson", video: "Video", topic: "Roadmap", habit: "Habit", project: "Project" };

const ROOT = ["planner"] as const;

export const usePlan = (day: string) => useQuery({ queryKey: [...ROOT, day], queryFn: () => api<DayPlan>(`/planner${qs({ day })}`) });

/** Acting on an item changes the owning feature's data too, so every feature's cached queries are refreshed. */
function useAction<TVars>(fn: (v: TVars) => Promise<DayPlan>) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => Promise.all(["planner", "tasks", "courses", "videos", "habits", "roadmap", "projects"].map((k) => qc.invalidateQueries({ queryKey: [k] }))),
  });
}

type Ref = { kind: Kind; ref_id: number; date: string };

export const useCompleteItem = () => useAction((body: Ref) => api<DayPlan>("/planner/complete", { method: "POST", body }));
export const useReopenItem = () => useAction((body: Ref) => api<DayPlan>("/planner/reopen", { method: "POST", body }));
export const useExcuse = () => useAction((body: Ref & { reason: string }) => api<DayPlan>("/planner/excuse", { method: "POST", body }));
export const useUnexcuse = () => useAction((body: Ref) => api<DayPlan>("/planner/unexcuse", { method: "POST", body }));
export const useReschedule = () =>
  useAction(({ taskId, ...body }: { taskId: number; date: string; from_date: string; move_due_date: boolean }) =>
    api<DayPlan>(`/planner/tasks/${taskId}/reschedule`, { method: "POST", body }));
