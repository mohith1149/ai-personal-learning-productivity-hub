import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, qs } from "./client";

export type TaskView = "open" | "today" | "overdue" | "upcoming" | "completed" | "all";
export type TaskStatus = "pending" | "in_progress" | "completed" | "cancelled";
export type CategoryBrief = { id: number; name: string; color: string };
export type Category = CategoryBrief & { is_system: boolean };

export type Task = {
  id: number;
  title: string;
  description: string | null;
  notes: string | null;
  category_id: number | null;
  category: CategoryBrief | null;
  task_type: string;
  priority: number;
  status: TaskStatus;
  scheduled_date: string | null;
  due_date: string | null;
  due_time: string | null;
  estimated_minutes: number | null;
  actual_minutes: number | null;
  completed_at: string | null;
  recurring_task_id: number | null;
  is_overdue: boolean;
  created_at: string;
  updated_at: string;
};

export type TaskCounts = {
  open: number;
  overdue: number;
  today: number;
  upcoming: number;
  completed: number;
  completed_today: number;
  all: number;
};

export type Frequency = "daily" | "weekdays" | "weekly" | "monthly";
export type Recurring = {
  id: number;
  title: string;
  description: string | null;
  category_id: number | null;
  category: CategoryBrief | null;
  priority: number;
  estimated_minutes: number | null;
  frequency: Frequency;
  days_of_week: number[] | null;
  day_of_month: number | null;
  start_date: string;
  end_date: string | null;
  active: boolean;
  last_generated_date: string | null;
};

export type TaskInput = {
  title: string;
  description?: string | null;
  notes?: string | null;
  category_id?: number | null;
  priority?: number;
  status?: TaskStatus;
  scheduled_date?: string | null;
  due_date?: string | null;
  due_time?: string | null;
  estimated_minutes?: number | null;
  actual_minutes?: number | null;
};

export type RecurringInput = {
  title: string;
  description?: string | null;
  category_id?: number | null;
  priority?: number;
  estimated_minutes?: number | null;
  frequency: Frequency;
  days_of_week?: number[] | null;
  day_of_month?: number | null;
  start_date?: string | null;
  end_date?: string | null;
};

export type TaskFilters = { view: TaskView; q?: string; category_id?: number; priority?: number };

/** Everything task-related shares the ["tasks", …] key prefix so one invalidation refreshes lists, counts and templates. */
const ROOT = ["tasks"] as const;

export function useTasks(f: TaskFilters) {
  return useQuery({
    queryKey: [...ROOT, "list", f],
    queryFn: () =>
      api<{ items: Task[]; total: number }>(
        `/tasks${qs({ view: f.view, q: f.q, category_id: f.category_id, priority: f.priority, limit: 500 })}`,
      ),
    placeholderData: keepPreviousData, // no flicker while filters change
  });
}

export const useTaskCounts = () =>
  useQuery({ queryKey: [...ROOT, "counts"], queryFn: () => api<TaskCounts>("/tasks/counts") });

export const useCategories = () =>
  useQuery({ queryKey: [...ROOT, "categories"], queryFn: () => api<Category[]>("/task-categories") });

export const useRecurring = () =>
  useQuery({ queryKey: [...ROOT, "recurring"], queryFn: () => api<Recurring[]>("/recurring-tasks") });

function useInvalidating<TVars, TData>(fn: (v: TVars) => Promise<TData>) {
  const qc = useQueryClient();
  return useMutation({ mutationFn: fn, onSuccess: () => qc.invalidateQueries({ queryKey: ROOT }) });
}

export const useCreateTask = () =>
  useInvalidating((body: TaskInput) => api<Task>("/tasks", { method: "POST", body }));

export const useUpdateTask = () =>
  useInvalidating(({ id, body }: { id: number; body: Partial<TaskInput> }) =>
    api<Task>(`/tasks/${id}`, { method: "PATCH", body }),
  );

export const useDeleteTask = () => useInvalidating((id: number) => api<void>(`/tasks/${id}`, { method: "DELETE" }));

export const useCreateCategory = () =>
  useInvalidating((body: { name: string; color: string }) => api<Category>("/task-categories", { method: "POST", body }));

export const useUpdateCategory = () =>
  useInvalidating(({ id, body }: { id: number; body: { name?: string; color?: string } }) =>
    api<Category>(`/task-categories/${id}`, { method: "PATCH", body }),
  );

export const useDeleteCategory = () =>
  useInvalidating((id: number) => api<void>(`/task-categories/${id}`, { method: "DELETE" }));

export const useCreateRecurring = () =>
  useInvalidating((body: RecurringInput) => api<Recurring>("/recurring-tasks", { method: "POST", body }));

export const useUpdateRecurring = () =>
  useInvalidating(({ id, body }: { id: number; body: { active?: boolean } }) =>
    api<Recurring>(`/recurring-tasks/${id}`, { method: "PATCH", body }),
  );

export const useDeleteRecurring = () =>
  useInvalidating((id: number) => api<void>(`/recurring-tasks/${id}`, { method: "DELETE" }));
