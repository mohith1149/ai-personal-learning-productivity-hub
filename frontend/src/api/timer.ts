import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";

export type TimerKind = "task" | "lesson" | "course" | "topic" | "project";

export type RunningTimer = {
  kind: TimerKind;
  label: string;
  started_at: string;
  elapsed_seconds: number; // at the time of the response; the clock on screen counts from started_at
  logs_to: string | null;
  task_id: number | null;
  lesson_id: number | null;
  topic_id: number | null;
  course_id: number | null;
  project_id: number | null;
};

export type Logged = { minutes: number; logged_to: "project" | "course" | "topic" | "task"; target_id: number | null; label: string; date: string };

export const useTimer = () => useQuery({ queryKey: ["timer"], queryFn: () => api<RunningTimer | null>("/timer") });

/** Logging time changes sessions, minutes and the plan, so those are refreshed too. */
const AFFECTED = ["timer", "projects", "courses", "tasks", "roadmap", "planner", "dashboard", "reports", "goals"];

function useTimerAction<TVars, TOut>(fn: (v: TVars) => Promise<TOut>) {
  const qc = useQueryClient();
  return useMutation({ mutationFn: fn, onSuccess: () => Promise.all(AFFECTED.map((k) => qc.invalidateQueries({ queryKey: [k] }))) });
}

export const useStartTimer = () => useTimerAction((body: { kind: TimerKind; ref_id: number }) => api<RunningTimer>("/timer/start", { method: "POST", body }));
export const useStopTimer = () => useTimerAction((body: { minutes?: number; summary?: string }) => api<Logged>("/timer/stop", { method: "POST", body }));
export const useDiscardTimer = () => useTimerAction(() => api<void>("/timer", { method: "DELETE" }));
