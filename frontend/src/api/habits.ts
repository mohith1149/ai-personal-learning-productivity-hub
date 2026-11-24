import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, qs } from "./client";

export type Frequency = "daily" | "weekly";

export type HabitLog = { date: string; completed: boolean; value: number | null; note: string | null };
export type Streak = { current: number; longest: number; unit: "days" | "weeks" };
export type Window = { start: string; end: string; completed: number; eligible_days: number; target: number | null; percent: number | null };
export type RecentDay = { date: string; completed: boolean; logged: boolean };

export type Habit = {
  id: number;
  name: string;
  description: string | null;
  notes: string | null;
  start_date: string;
  frequency: Frequency;
  target_per_period: number;
  target_value: number | null;
  unit: string | null;
  active: boolean;
  created_at: string;
  today: HabitLog | null;
  done_today: boolean;
  streak: Streak;
  week: Window;
  month: Window;
  total_completed: number;
  recent: RecentDay[]; // last 28 days, oldest first
};

export type HabitList = { items: Habit[]; due_today: number };

export type HabitInput = {
  name: string;
  description?: string | null;
  notes?: string | null;
  start_date?: string;
  frequency?: Frequency;
  target_per_period?: number;
  target_value?: number | null;
  unit?: string | null;
  active?: boolean;
};

const ROOT = ["habits"] as const;

export const useHabits = () => useQuery({ queryKey: ROOT, queryFn: () => api<HabitList>("/habits") });
export const useHistory = (habitId: number) =>
  useQuery({ queryKey: [...ROOT, "history", habitId], queryFn: () => api<HabitLog[]>(`/habits/${habitId}/logs${qs({ days: 90 })}`) });

function useInvalidating<TVars, TData>(fn: (v: TVars) => Promise<TData>) {
  const qc = useQueryClient();
  return useMutation({ mutationFn: fn, onSuccess: () => qc.invalidateQueries({ queryKey: ROOT }) });
}

export const useCreateHabit = () => useInvalidating((body: HabitInput) => api<Habit>("/habits", { method: "POST", body }));
export const useUpdateHabit = () => useInvalidating(({ id, body }: { id: number; body: Partial<HabitInput> }) => api<Habit>(`/habits/${id}`, { method: "PATCH", body }));
export const useDeleteHabit = () => useInvalidating((id: number) => api<void>(`/habits/${id}`, { method: "DELETE" }));
export const useSetLog = () =>
  useInvalidating(({ id, date, body }: { id: number; date: string; body: { completed: boolean; value?: number | null; note?: string | null } }) =>
    api<Habit>(`/habits/${id}/logs/${date}`, { method: "PUT", body }));
export const useDeleteLog = () => useInvalidating(({ id, date }: { id: number; date: string }) => api<Habit>(`/habits/${id}/logs/${date}`, { method: "DELETE" }));
