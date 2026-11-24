import { useQuery } from "@tanstack/react-query";
import type { Stats, Challenge } from "./challenges";
import type { DaySummary, PlanItem } from "./planner";
import { api } from "./client";

export type VideoToday = { playlist_id: number; name: string; daily_target: number; watched_today: number; remaining_today: number; target_met: boolean; up_next: string[] };

export type Dashboard = {
  date: string;
  plan: { summary: DaySummary; next_items: PlanItem[]; open_count: number };
  videos: VideoToday[];
  challenge: { today: Challenge | null; stats: Stats };
  habits: { active: number; due_today: number; best_streak: number; best_streak_name: string | null; best_streak_unit: string | null };
  tasks: { overdue: number; today: number; completed_today: number };
  projects: { id: number; title: string; percent: number; minutes_spent: number; last_activity_at: string | null }[];
  courses: { id: number; title: string; percent: number; next_lesson: string | null }[];
  roadmap: { total: number; completed: number; in_progress: number; percent: number; next_topic: string | null };
  week: { date: string; study_minutes: number; dev_minutes: number }[];
  is_empty: boolean;
};

/** Everything on the dashboard is computed by the server from your records on each request; nothing is cached or stored for it. */
export const useDashboard = () => useQuery({ queryKey: ["dashboard"], queryFn: () => api<Dashboard>("/dashboard") });
