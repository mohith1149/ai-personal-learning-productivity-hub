import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";

export type Mode = "new_project" | "existing_project";
export type ChallengeStatus = "planned" | "in_progress" | "completed" | "missed" | "excused";
export type CalendarStatus = ChallengeStatus | "none";

export const STATUS_LABEL: Record<CalendarStatus, string> = {
  planned: "Planned", in_progress: "In progress", completed: "Completed", missed: "Missed", excused: "Excused", none: "Nothing planned",
};

export type Challenge = {
  id: number;
  date: string;
  mode: Mode;
  status: ChallengeStatus;
  project: { id: number; title: string; repo_url: string | null } | null;
  planned_task: string;
  estimated_minutes: number | null;
  actual_minutes: number | null;
  implemented_summary: string | null;
  repo_url: string | null;
  commit_sha: string | null;
  commit_message: string | null;
  evidence_notes: string | null;
  milestone: { id: number; title: string } | null;
  verification_status: "unverified" | "verified";
  excuse_reason: string | null;
  completed_at: string | null;
  can_complete: boolean;
  can_edit: boolean;
};

export type Suggestion = {
  source: "project" | "roadmap" | "course" | "previous";
  mode: Mode;
  project_id: number | null;
  title: string;
  detail: string | null;
  planned_task: string;
};

export type Stats = {
  completed: number;
  excused: number;
  missed: number;
  completion_rate: number;
  current_streak: number;
  longest_streak: number;
  total_minutes: number;
  first_day: string | null;
};

export type TodayView = { date: string; challenge: Challenge | null; stats: Stats; suggestions: Suggestion[] };
export type CalendarDay = { date: string; status: CalendarStatus; project_title: string | null; challenge_id: number | null };
export type CalendarView = { start: string; end: string; days: CalendarDay[]; stats: Stats };

export type PlanInput = {
  mode: Mode;
  project_id?: number;
  new_project?: { title: string; description?: string; repo_url?: string };
  planned_task: string;
  estimated_minutes?: number;
};

export type EvidenceInput = {
  summary: string;
  repo_url: string;
  commit_sha: string;
  commit_message: string;
  minutes: number;
  evidence_notes?: string;
};

const ROOT = ["challenges"] as const;

export const useToday = () => useQuery({ queryKey: [...ROOT, "today"], queryFn: () => api<TodayView>("/challenges/today") });
export const useCalendar = () => useQuery({ queryKey: [...ROOT, "calendar"], queryFn: () => api<CalendarView>("/challenges/calendar") });
export const useHistory = () => useQuery({ queryKey: [...ROOT, "history"], queryFn: () => api<Challenge[]>("/challenges/history") });

/** Challenges touch projects (new project, development time) and the planner (project minutes), so those are refreshed too. */
function useChanging<T, R = unknown>(fn: (v: T) => Promise<R>) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => Promise.all(["challenges", "projects", "planner"].map((k) => qc.invalidateQueries({ queryKey: [k] }))),
  });
}

export const usePlanChallenge = () => useChanging((body: PlanInput) => api<Challenge>("/challenges", { method: "POST", body }));
export const useStartChallenge = () => useChanging((id: number) => api<Challenge>(`/challenges/${id}/start`, { method: "POST" }));
export const useCompleteChallenge = () =>
  useChanging(({ id, ...body }: EvidenceInput & { id: number }) => api<Challenge>(`/challenges/${id}/complete`, { method: "POST", body }));
export const useDeleteChallenge = () => useChanging((id: number) => api<void>(`/challenges/${id}`, { method: "DELETE" }));
export const useExcuseDay = () => useChanging((body: { date: string; reason: string }) => api<Challenge>("/challenges/excuse", { method: "POST", body }));

export type VerifyResult = { verified: boolean; checks: { name: string; ok: boolean; detail: string }[]; challenge: Challenge };
export const useVerifyChallenge = () => useChanging((id: number) => api<VerifyResult>(`/challenges/${id}/verify`, { method: "POST" }));
