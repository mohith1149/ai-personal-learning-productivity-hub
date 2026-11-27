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
  carry_count: number; // times the task was moved to another day
  slipping: boolean; // moved 3 or more times and still open
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
  rest_day: boolean;
  planned_minutes: number; // time of the items that count; items with no time are in `unestimated`
  available_minutes: number | null; // the hours set for this weekday, null = not set
  unestimated: number;
  overloaded: boolean;
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

// ---------------------------------------------------------------- rest days, daily hours, rolling over

export type RestMonth = { month: string; cap: number; used: number; left: number; days: { date: string; reason: string | null }[] };
export type Preferences = { weekday_minutes: number[] | null; rest_days_per_month: number };
export type MovedTask = { task_id: number; title: string; carry_count: number; minutes: number | null; slipping: boolean };
export type RollOver = {
  dry_run: boolean;
  moved: MovedTask[];
  tomorrow: { date: string; total: number; planned_minutes: number; available_minutes: number | null; overloaded: boolean; unestimated: number; rest_day: boolean };
};

export const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"] as const;

export const useRestMonth = (month: string) => useQuery({ queryKey: ["rest-days", month], queryFn: () => api<RestMonth>(`/rest-days${qs({ month })}`) });

/** Rest days change the plan, the challenge streak and the reports, so all of those are refreshed. */
function useRestAction<TVars>(fn: (v: TVars) => Promise<RestMonth>) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => Promise.all(["rest-days", "planner", "challenges", "reports", "dashboard"].map((k) => qc.invalidateQueries({ queryKey: [k] }))),
  });
}
export const useAddRestDay = () => useRestAction((body: { date: string; reason?: string }) => api<RestMonth>("/rest-days", { method: "POST", body }));
export const useRemoveRestDay = () => useRestAction((date: string) => api<RestMonth>(`/rest-days/${date}`, { method: "DELETE" }));

export const usePreferences = () => useQuery({ queryKey: ["planner-preferences"], queryFn: () => api<Preferences>("/planner/preferences") });
export function useUpdatePreferences() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Partial<Preferences>) => api<Preferences>("/planner/preferences", { method: "PATCH", body }),
    onSuccess: () => Promise.all(["planner-preferences", "planner", "rest-days"].map((k) => qc.invalidateQueries({ queryKey: [k] }))),
  });
}

/** `dry_run: true` previews (nothing is saved). The real call changes tasks, so every list that shows them is refreshed. */
export function useRollOver() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { dry_run: boolean; task_ids?: number[] }) => api<RollOver>("/planner/roll-over", { method: "POST", body }),
    onSuccess: (r) => (r.dry_run ? undefined : Promise.all(["planner", "tasks", "dashboard"].map((k) => qc.invalidateQueries({ queryKey: [k] })))),
  });
}
