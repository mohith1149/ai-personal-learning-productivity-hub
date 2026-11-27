import { useQuery } from "@tanstack/react-query";
import { api } from "./client";

export type GoalStatus = "done" | "overdue" | "behind" | "stalled" | "not_started" | "on_track" | "unknown";

/** A course or project with a target date, and whether you are on pace for it. The wording in `message` comes from the server. */
export type Goal = {
  kind: "course" | "project";
  id: number;
  title: string;
  target_date: string;
  status: GoalStatus;
  warning: boolean;
  message: string;
  unit: string;
  total: number;
  done: number;
  remaining: number;
  days_left: number;
  needed_per_day: number;
  recent_per_day: number;
  projected_date: string | null;
};

export const useGoals = () => useQuery({ queryKey: ["goals"], queryFn: () => api<Goal[]>("/goals") });
