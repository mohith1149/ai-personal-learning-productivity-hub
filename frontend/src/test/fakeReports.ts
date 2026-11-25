/** Report endpoints for the fake API. The numbers are generated deterministically from the requested period (the real arithmetic is tested in pytest). */
import type { ChallengeDay, Report, ReportDay, Totals } from "../api/reports";
import { addDays } from "../lib/dates";
import type { Fake, Handler } from "./fakeApi";
import { TODAY } from "./fakeApi";

export type FakeReports = { report: Report | null; error: string | null; empty: boolean; requests: string[] };

const CYCLE: ChallengeDay[] = ["completed", "completed", "missed", "excused", "completed", "planned", "none"];

function mondayOf(iso: string): string {
  const dow = (new Date(`${iso}T12:00:00`).getDay() + 6) % 7;
  return addDays(iso, -dow);
}

const totalsOf = (days: ReportDay[], challengeDays: number): Totals => {
  const sum = (k: keyof ReportDay) => days.reduce((n, d) => n + (typeof d[k] === "number" ? (d[k] as number) : 0), 0);
  const t = { tasks_done: sum("tasks_done"), lessons_done: sum("lessons_done"), videos_done: sum("videos_done"), topics_done: sum("topics_done"), study_minutes: sum("study_minutes"),
              project_minutes: sum("project_minutes"), habits_done: sum("habits_done") };
  return { ...t, items_done: t.tasks_done + t.lessons_done + t.videos_done + t.topics_done, challenge_days: challengeDays };
};

export function buildReport(kind: "week" | "month", anchor: string | null, empty = false): Report {
  const day = anchor ?? TODAY;
  let start: string, end: string, label: string;
  if (kind === "week") {
    start = mondayOf(day);
    end = addDays(start, 6);
    label = `${start} to ${end}`;
  } else {
    const ym = anchor ?? TODAY.slice(0, 7);
    start = `${ym}-01`;
    const next = new Date(Number(ym.slice(0, 4)), Number(ym.slice(5, 7)), 0).getDate();
    end = `${ym}-${String(next).padStart(2, "0")}`;
    label = new Date(`${start}T12:00:00`).toLocaleDateString("en-GB", { month: "long", year: "numeric" });
  }
  const length = (new Date(`${end}T12:00:00`).getTime() - new Date(`${start}T12:00:00`).getTime()) / 86400000 + 1;
  const days: ReportDay[] = Array.from({ length }, (_, i) => {
    const date = addDays(start, i);
    const happened = date <= TODAY;
    const v = (n: number) => (happened && !empty ? n : 0);
    const planned = happened ? (empty ? 0 : 4 + (i % 3)) : null;
    const done = planned === null ? null : Math.min(planned, i % 5);
    const d: ReportDay = {
      date, tasks_done: v(i % 3), lessons_done: v(i % 2), videos_done: v((i + 1) % 3 === 0 ? 2 : 0), topics_done: v(i % 7 === 3 ? 1 : 0),
      items_done: 0, study_minutes: v(20 * (i % 4)), project_minutes: v(i % 2 ? 45 : 0), habits_done: v(i % 3 === 0 ? 1 : 0),
      challenge: happened ? (empty ? "none" : CYCLE[i % CYCLE.length]) : "none", plan_total: planned, plan_completed: done,
    };
    d.items_done = d.tasks_done + d.lessons_done + d.videos_done + d.topics_done;
    return d;
  });
  const counted = days.filter((d) => d.date <= TODAY);
  const c = counted.filter((d) => d.challenge === "completed").length;
  const planTotal = counted.reduce((n, d) => n + (d.plan_total ?? 0), 0);
  const planDone = counted.reduce((n, d) => n + (d.plan_completed ?? 0), 0);
  const totals = totalsOf(counted, c);
  const previous: Totals = empty ? totalsOf([], 0) : { ...totals, items_done: totals.items_done + 2, study_minutes: Math.max(0, totals.study_minutes - 30), habits_done: totals.habits_done };
  return {
    period: { kind, start, end, label, days: length, is_current: start <= TODAY && TODAY <= end, through: end < TODAY ? end : TODAY },
    days, totals, previous,
    plan: { total: planTotal, completed: planDone, percent: planTotal ? Math.floor((100 * planDone) / planTotal) : 0 },
    challenge: { completed: c, verified: 0, missed: counted.filter((d) => d.challenge === "missed").length, excused: counted.filter((d) => d.challenge === "excused").length, current_streak: 2 },
    projects: empty ? [] : [{ project_id: 1, title: "RAG chatbot", minutes: 180 }, { project_id: 2, title: "Agent toolkit", minutes: 90 }],
    habits: empty ? [] : [{ habit_id: 1, name: "Reading", done_days: 4 }, { habit_id: 2, name: "Exercise", done_days: 1 }],
  };
}

export function installFakeReports(fake: Fake, seed: Partial<FakeReports> = {}): FakeReports {
  const store: FakeReports = { report: seed.report ?? null, error: seed.error ?? null, empty: seed.empty ?? false, requests: [] };
  const handler: Handler = ({ method, path, query }) => {
    if (method !== "GET" || !/^\/api\/reports\/(weekly|monthly)$/.test(path)) return undefined;
    store.requests.push(`${path}?${new URLSearchParams(query).toString()}`);
    if (store.error) return Response.json({ detail: store.error }, { status: 500 });
    if (store.report) return Response.json(store.report);
    const kind = path.endsWith("weekly") ? "week" : "month";
    return Response.json(buildReport(kind, query.week_start ?? query.month ?? null, store.empty));
  };
  fake.handlers.push(handler);
  return store;
}
