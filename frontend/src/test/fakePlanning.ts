/** Rest days and planning preferences for the fake API (installed by default, like notifications). Real rules are tested in pytest. */
import type { Goal } from "../api/goals";
import type { Preferences, RestMonth } from "../api/planner";
import type { Share } from "../api/share";
import type { Logged, RunningTimer } from "../api/timer";
import type { Handler } from "./fakeApi";

export type FakePlanning = {
  prefs: Preferences;
  restDays: { date: string; reason: string | null }[];
  today: () => string;
  goals: Goal[];
  timer: RunningTimer | null;
  /** What the fake logs when a timer is stopped (minutes come from the request). */
  stopped: Logged[];
  share: Share;
};

export const newFakePlanning = (today: () => string): FakePlanning => ({ prefs: { weekday_minutes: null, focus_windows: null, rest_days_per_month: 4 }, restDays: [], today, goals: [], timer: null, stopped: [], share: { enabled: false, token: null, path: null } });

export function restMonth(store: FakePlanning, month: string): RestMonth {
  const days = store.restDays.filter((d) => d.date.startsWith(month)).sort((a, b) => a.date.localeCompare(b.date));
  return { month, cap: store.prefs.rest_days_per_month, used: days.length, left: Math.max(0, store.prefs.rest_days_per_month - days.length), days };
}

export function planningHandler(store: FakePlanning): Handler {
  return ({ method, path, query, body }) => {
    if (path === "/api/rest-days" && method === "GET") return Response.json(restMonth(store, query.month ?? store.today().slice(0, 7)));
    if (path === "/api/rest-days" && method === "POST") {
      const b = body as { date: string; reason?: string };
      const month = b.date.slice(0, 7);
      if (store.restDays.some((d) => d.date === b.date)) return Response.json({ detail: "That day is already a rest day" }, { status: 409 });
      if (restMonth(store, month).left === 0) return Response.json({ detail: `You've used all ${store.prefs.rest_days_per_month} rest days for that month` }, { status: 422 });
      store.restDays.push({ date: b.date, reason: b.reason ?? null });
      return Response.json(restMonth(store, month), { status: 201 });
    }
    const m = path.match(/^\/api\/rest-days\/(\d{4}-\d{2}-\d{2})$/);
    if (m && method === "DELETE") {
      if (!store.restDays.some((d) => d.date === m[1])) return Response.json({ detail: "That day isn't a rest day" }, { status: 404 });
      store.restDays = store.restDays.filter((d) => d.date !== m[1]);
      return Response.json(restMonth(store, m[1].slice(0, 7)));
    }
    if (path === "/api/planner/preferences" && method === "GET") return Response.json(store.prefs);
    if (path === "/api/planner/preferences" && method === "PATCH") {
      Object.assign(store.prefs, body);
      return Response.json(store.prefs);
    }
    if (path === "/api/share" && method === "GET") return Response.json(store.share);
    if (path === "/api/share" && method === "POST") {
      const token = `tok${Math.random().toString(36).slice(2)}${"x".repeat(30)}`;
      store.share = { enabled: true, token, path: `/share/${token}` };
      return Response.json(store.share, { status: 201 });
    }
    if (path === "/api/share" && method === "DELETE") {
      store.share = { enabled: false, token: null, path: null };
      return new Response(null, { status: 204 });
    }
    if (path === "/api/goals" && method === "GET") return Response.json(store.goals);
    if (path === "/api/timer" && method === "GET") return Response.json(store.timer);
    if (path === "/api/timer" && method === "DELETE") {
      if (!store.timer) return Response.json({ detail: "No timer is running" }, { status: 404 });
      store.timer = null;
      return new Response(null, { status: 204 });
    }
    if (path === "/api/timer/start" && method === "POST") {
      if (store.timer) return Response.json({ detail: "A timer is already running. Stop it (to log the time) or discard it first" }, { status: 409 });
      const b = body as { kind: RunningTimer["kind"]; ref_id: number };
      store.timer = {
        kind: b.kind, label: `Timed ${b.kind} ${b.ref_id}`, started_at: new Date().toISOString(), elapsed_seconds: 0, logs_to: b.kind === "project" ? "Project: Timed" : null,
        task_id: b.kind === "task" ? b.ref_id : null, lesson_id: b.kind === "lesson" ? b.ref_id : null, topic_id: b.kind === "topic" ? b.ref_id : null,
        course_id: b.kind === "course" ? b.ref_id : null, project_id: b.kind === "project" ? b.ref_id : null,
      };
      return Response.json(store.timer, { status: 201 });
    }
    if (path === "/api/timer/stop" && method === "POST") {
      if (!store.timer) return Response.json({ detail: "No timer is running" }, { status: 404 });
      const b = body as { minutes?: number; summary?: string };
      const t = store.timer;
      const logged: Logged = {
        minutes: b.minutes ?? Math.max(1, Math.round(t.elapsed_seconds / 60)),
        logged_to: t.project_id ? "project" : t.course_id ? "course" : t.topic_id ? "topic" : "task",
        target_id: t.project_id ?? t.course_id ?? t.topic_id, label: t.label, date: store.today(),
      };
      store.stopped.push(logged);
      store.timer = null;
      return Response.json(logged);
    }
    return undefined;
  };
}
