/** In-memory stand-in for the backend, for UI tests. It mimics response SHAPES and basic filtering only;
 *  the real business rules (overdue, recurrence, validation) are tested against the real API in pytest. */
import { vi } from "vitest";
import type { Category, Recurring, Task } from "../api/tasks";
import { todayIn } from "../lib/dates";
import { emptyDashboard } from "./fakeDashboard";

export const USER = { id: 1, email: "me@example.com", display_name: "Ada Lovelace", timezone: "Asia/Kolkata" };
export const TODAY = todayIn(USER.timezone);

import { newFakeNotifications, notificationsHandler, type FakeNotifications } from "./fakeNotifications";

export type Call = { method: string; path: string; query: Record<string, string>; body?: Record<string, unknown> };

export type Req = { method: string; path: string; query: Record<string, string>; body?: Record<string, unknown> };
/** Extra route handlers (e.g. the courses fake) are consulted before an unknown request is treated as a test failure. */
export type Handler = (req: Req) => Response | undefined;

export type Fake = {
  handlers: Handler[];
  notifications: FakeNotifications;
  tasks: Task[];
  categories: Category[];
  recurring: Recurring[];
  calls: Call[];
  /** Make the next request whose "METHOD /path" matches fail once (or `times` times). */
  failNext: (match: RegExp, status: number, detail: string, times?: number) => void;
  callsTo: (method: string, pathRe: RegExp) => Call[];
};

let nextId = 100;

export function mkTask(o: Partial<Task> = {}): Task {
  const id = o.id ?? nextId++;
  return {
    id,
    title: `Task ${id}`,
    description: null,
    notes: null,
    category_id: null,
    category: null,
    task_type: "one_time",
    priority: 3,
    status: "pending",
    scheduled_date: null,
    due_date: null,
    due_time: null,
    estimated_minutes: null,
    actual_minutes: null,
    completed_at: null,
    recurring_task_id: null,
    is_overdue: false,
    created_at: "2026-11-23T00:00:00Z",
    updated_at: "2026-11-23T00:00:00Z",
    ...o,
  };
}

export function mkRecurring(o: Partial<Recurring> = {}): Recurring {
  const id = o.id ?? nextId++;
  return {
    id,
    title: `Routine ${id}`,
    description: null,
    category_id: null,
    category: null,
    priority: 3,
    estimated_minutes: null,
    frequency: "daily",
    days_of_week: null,
    day_of_month: null,
    start_date: TODAY,
    end_date: null,
    active: true,
    last_generated_date: TODAY,
    ...o,
  };
}

const OPEN = ["pending", "in_progress"];
const inView = (t: Task, view: string) =>
  view === "all" ||
  (view === "open" && OPEN.includes(t.status)) ||
  (view === "overdue" && t.is_overdue) ||
  (view === "today" && OPEN.includes(t.status) && (t.due_date === TODAY || t.scheduled_date === TODAY)) ||
  (view === "upcoming" && OPEN.includes(t.status) && !!t.due_date && t.due_date > TODAY) ||
  (view === "completed" && t.status === "completed");

export function installFakeApi(seed: { tasks?: Task[]; categories?: Category[]; recurring?: Recurring[] } = {}): Fake {
  const f: Fake = {
    tasks: seed.tasks ?? [],
    categories: seed.categories ?? [],
    recurring: seed.recurring ?? [],
    calls: [],
    handlers: [],
    notifications: newFakeNotifications(),
    failNext: () => {},
    callsTo: (method, re) => f.calls.filter((c) => c.method === method && re.test(c.path)),
  };
  f.handlers.push(({ method, path }) => (path === "/api/dashboard" && method === "GET" ? Response.json(emptyDashboard()) : undefined)); // default: a new, empty account
  f.handlers.push(notificationsHandler(f.notifications));
  const failures: { match: RegExp; status: number; detail: string; left: number }[] = [];
  f.failNext = (match, status, detail, times = 1) => failures.push({ match, status, detail, left: times });

  const json = (data: unknown, status = 200) => Response.json(data, { status });
  const brief = (id: number | null) => {
    const c = f.categories.find((x) => x.id === id);
    return c ? { id: c.id, name: c.name, color: c.color } : null;
  };

  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string, init?: RequestInit) => {
      const url = new URL(input, "http://localhost");
      const method = init?.method ?? "GET";
      const body = init?.body ? (JSON.parse(init.body as string) as Record<string, unknown>) : undefined;
      const path = url.pathname;
      f.calls.push({ method, path, query: Object.fromEntries(url.searchParams), body });

      const key = `${method} ${path}`;
      const fail = failures.find((x) => x.left > 0 && x.match.test(key));
      if (fail) {
        fail.left--;
        return json({ detail: fail.detail }, fail.status);
      }

      if (path === "/api/auth/status") return json({ setup_required: false, authenticated: true, user: USER });

      // ---- tasks ----
      if (path === "/api/tasks/counts") {
        const c = (v: string) => f.tasks.filter((t) => inView(t, v)).length;
        return json({ open: c("open"), overdue: c("overdue"), today: c("today"), upcoming: c("upcoming"), completed: c("completed"), completed_today: 0, all: f.tasks.length });
      }
      if (path === "/api/tasks" && method === "GET") {
        const q = url.searchParams;
        let items = f.tasks.filter((t) => inView(t, q.get("view") ?? "all"));
        if (q.get("q")) items = items.filter((t) => t.title.toLowerCase().includes(q.get("q")!.toLowerCase()));
        if (q.get("category_id")) items = items.filter((t) => t.category_id === Number(q.get("category_id")));
        if (q.get("priority")) items = items.filter((t) => t.priority === Number(q.get("priority")));
        return json({ items, total: items.length });
      }
      if (path === "/api/tasks" && method === "POST") {
        const t = mkTask({ ...(body as Partial<Task>), category: brief((body?.category_id as number) ?? null) });
        f.tasks.push(t);
        return json(t, 201);
      }
      const taskId = path.match(/^\/api\/tasks\/(\d+)$/)?.[1];
      if (taskId) {
        const i = f.tasks.findIndex((t) => t.id === Number(taskId));
        if (i < 0) return json({ detail: "Task not found" }, 404);
        if (method === "PATCH") {
          const merged = { ...f.tasks[i], ...(body as Partial<Task>) };
          merged.completed_at = merged.status === "completed" ? (f.tasks[i].completed_at ?? "2026-11-23T10:00:00Z") : null;
          if (merged.status === "completed") merged.is_overdue = false;
          merged.category = brief(merged.category_id);
          f.tasks[i] = merged;
          return json(merged);
        }
        if (method === "DELETE") {
          f.tasks.splice(i, 1);
          return new Response(null, { status: 204 });
        }
        return json(f.tasks[i]);
      }

      // ---- categories ----
      if (path === "/api/task-categories" && method === "GET") return json(f.categories);
      if (path === "/api/task-categories" && method === "POST") {
        const c: Category = { id: nextId++, name: body!.name as string, color: body!.color as string, is_system: false };
        f.categories.push(c);
        return json(c, 201);
      }
      const catId = path.match(/^\/api\/task-categories\/(\d+)$/)?.[1];
      if (catId) {
        const i = f.categories.findIndex((c) => c.id === Number(catId));
        if (method === "PATCH") {
          f.categories[i] = { ...f.categories[i], ...(body as Partial<Category>) };
          return json(f.categories[i]);
        }
        if (method === "DELETE") {
          f.categories.splice(i, 1);
          f.tasks.forEach((t) => t.category_id === Number(catId) && ((t.category_id = null), (t.category = null)));
          return new Response(null, { status: 204 });
        }
      }

      // ---- recurring ----
      if (path === "/api/recurring-tasks" && method === "GET") return json(f.recurring);
      if (path === "/api/recurring-tasks" && method === "POST") {
        const r = mkRecurring({ ...(body as Partial<Recurring>), start_date: (body!.start_date as string) ?? TODAY });
        f.recurring.unshift(r);
        return json(r, 201);
      }
      const recId = path.match(/^\/api\/recurring-tasks\/(\d+)$/)?.[1];
      if (recId) {
        const i = f.recurring.findIndex((r) => r.id === Number(recId));
        if (method === "PATCH") {
          f.recurring[i] = { ...f.recurring[i], ...(body as Partial<Recurring>) };
          return json(f.recurring[i]);
        }
        if (method === "DELETE") {
          f.recurring.splice(i, 1);
          return new Response(null, { status: 204 });
        }
      }

      for (const h of f.handlers) {
        const res = h({ method, path, query: Object.fromEntries(url.searchParams), body });
        if (res) return res;
      }
      // Default for pages that only ask whether AI is on (e.g. the project form): AI is off. installFakeAssistant overrides this above.
      if (method === "GET" && path === "/api/ai/status") return Response.json({ provider: "none", connected: false, model: null, live_verified: false, message: "AI is off." });
      throw new Error(`Unexpected request in test: ${key}`);
    }),
  );
  return f;
}
