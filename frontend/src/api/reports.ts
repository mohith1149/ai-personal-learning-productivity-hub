import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { api } from "./client";

export type ChallengeDay = "completed" | "excused" | "missed" | "planned" | "in_progress" | "none";

export type ReportDay = {
  date: string;
  tasks_done: number;
  lessons_done: number;
  videos_done: number;
  topics_done: number;
  items_done: number;
  study_minutes: number;
  project_minutes: number;
  habits_done: number;
  challenge: ChallengeDay;
  plan_total: number | null; // null = the day has not happened yet
  plan_completed: number | null;
};

export type Totals = {
  tasks_done: number;
  lessons_done: number;
  videos_done: number;
  topics_done: number;
  items_done: number;
  study_minutes: number;
  project_minutes: number;
  habits_done: number;
  challenge_days: number;
};

export type Report = {
  period: { kind: "week" | "month"; start: string; end: string; label: string; days: number; is_current: boolean; through: string };
  days: ReportDay[];
  totals: Totals;
  previous: Totals;
  plan: { total: number; completed: number; percent: number };
  challenge: { completed: number; verified: number; missed: number; excused: number; current_streak: number };
  projects: { project_id: number; title: string; minutes: number }[];
  habits: { habit_id: number; name: string; done_days: number }[];
};

export type ReportKind = Report["period"]["kind"];

/** `anchor`: a week = any day in it (YYYY-MM-DD); a month = YYYY-MM; null = the current one. The previous report stays on screen while the next one loads. */
export function useReport(kind: ReportKind, anchor: string | null) {
  return useQuery({
    queryKey: ["reports", kind, anchor],
    queryFn: () => api<Report>(kind === "week" ? `/reports/weekly${anchor ? `?week_start=${anchor}` : ""}` : `/reports/monthly${anchor ? `?month=${anchor}` : ""}`),
    placeholderData: keepPreviousData,
  });
}
