/** Dashboard endpoint for the fake API. The numbers are whatever the test provides; how the server computes them is tested in pytest. */
import type { Dashboard } from "../api/dashboard";
import { addDays, todayIn } from "../lib/dates";
import { USER, type Fake, type Handler } from "./fakeApi";

export function emptyDashboard(): Dashboard {
  const today = todayIn(USER.timezone);
  return {
    date: today,
    plan: { summary: { total: 0, completed: 0, pending: 0, overdue: 0, excused: 0, percent: 0, study_minutes: 0, dev_minutes: 0, by_kind: [], rest_day: false, planned_minutes: 0, available_minutes: null, unestimated: 0, overloaded: false }, next_items: [], open_count: 0 },
    videos: [], challenge: { today: null, stats: { completed: 0, excused: 0, rest_days: 0, missed: 0, completion_rate: 0, current_streak: 0, longest_streak: 0, total_minutes: 0, first_day: null } },
    habits: { active: 0, due_today: 0, best_streak: 0, best_streak_name: null, best_streak_unit: null }, tasks: { overdue: 0, today: 0, completed_today: 0 },
    projects: [], courses: [], roadmap: { total: 0, completed: 0, in_progress: 0, percent: 0, next_topic: null },
    week: Array.from({ length: 7 }, (_, i) => ({ date: addDays(today, i - 6), study_minutes: 0, dev_minutes: 0 })), is_empty: true,
  };
}

/** Serve `data` (merged over an empty dashboard) from GET /api/dashboard. Registered first, so it wins over the default empty one. */
export function installFakeDashboard(fake: Fake, data: Partial<Dashboard> = {}): Dashboard {
  const dash: Dashboard = { ...emptyDashboard(), ...data };
  const handler: Handler = ({ method, path }) => (path === "/api/dashboard" && method === "GET" ? Response.json(dash) : undefined);
  fake.handlers.unshift(handler);
  return dash;
}
