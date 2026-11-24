/** Habit endpoints for the fake API. It recomputes streak/week/month from the stored day records, mirroring the server's
 *  response shape. The exact maths (weekly weeks, timezones, boundaries) is tested in pytest against the real code. */
import type { Habit, HabitLog } from "../api/habits";
import { addDays, todayIn } from "../lib/dates";
import { USER, type Fake, type Handler } from "./fakeApi";

export type StoredHabit = Omit<Habit, "today" | "done_today" | "streak" | "week" | "month" | "total_completed" | "recent">;
export type FakeHabits = { habits: StoredHabit[]; logs: Record<number, HabitLog[]> };

let nextId = 4000;

export function mkHabit(o: Partial<StoredHabit> = {}): StoredHabit {
  const n = o.id ?? nextId++;
  return {
    id: n, name: `Habit ${n}`, description: null, notes: null, start_date: addDays(todayIn(USER.timezone), -60), frequency: "daily",
    target_per_period: 1, target_value: null, unit: null, active: true, created_at: "2026-11-01T00:00:00Z", ...o,
  };
}

export const isoDaysAgo = (n: number) => addDays(todayIn(USER.timezone), -n);

export function installFakeHabits(fake: Fake, seed: Partial<FakeHabits> = {}): FakeHabits {
  const store: FakeHabits = { habits: seed.habits ?? [], logs: seed.logs ?? {} };
  const json = (d: unknown, status = 200) => Response.json(d, { status });
  const today = () => todayIn(USER.timezone);

  const summary = (h: StoredHabit): Habit => {
    const t = today();
    const logs = store.logs[h.id] ?? [];
    const done = new Set(logs.filter((l) => l.completed && l.date >= h.start_date).map((l) => l.date));
    let cur = 0;
    let cursor = done.has(t) ? t : addDays(t, -1);
    while (done.has(cursor)) {
      cur++;
      cursor = addDays(cursor, -1);
    }
    let best = 0, run = 0, prev = "";
    for (const d of [...done].sort()) {
      run = prev && addDays(prev, 1) === d ? run + 1 : 1;
      best = Math.max(best, run);
      prev = d;
    }
    const weekStart = addDays(t, -((new Date(t + "T00:00:00Z").getUTCDay() + 6) % 7));
    const inRange = (a: string, b: string) => [...done].filter((d) => d >= a && d <= b && d <= t).length;
    const eligible = (a: string) => Math.max((new Date(t).getTime() - new Date(a < h.start_date ? h.start_date : a).getTime()) / 86400000 + 1, 0);
    const weekly = h.frequency === "weekly";
    const monthStart = t.slice(0, 8) + "01";
    const wDone = inRange(weekStart, addDays(weekStart, 6));
    const mDone = inRange(monthStart, t);
    const mEligible = eligible(monthStart);
    const wEligible = eligible(weekStart);
    return {
      ...h, today: logs.find((l) => l.date === t) ?? null, done_today: done.has(t),
      // weekly streaks (consecutive weeks meeting the goal) are computed and tested by the real server code; the fake reports none
      streak: { current: weekly ? 0 : cur, longest: weekly ? 0 : best, unit: weekly ? "weeks" : "days" },
      week: { start: weekStart, end: addDays(weekStart, 6), completed: wDone, eligible_days: wEligible, target: weekly ? h.target_per_period : null,
              percent: Math.min(100, Math.floor((100 * wDone) / (weekly ? h.target_per_period : wEligible || 1))) },
      month: { start: monthStart, end: monthStart, completed: mDone, eligible_days: mEligible, target: null, percent: weekly ? null : Math.floor((100 * mDone) / (mEligible || 1)) },
      total_completed: done.size,
      recent: Array.from({ length: 28 }, (_, i) => {
        const d = addDays(t, i - 27);
        const l = logs.find((x) => x.date === d);
        return { date: d, completed: done.has(d), logged: !!l };
      }),
    };
  };

  const find = (id: number) => store.habits.find((h) => h.id === id);
  const handler: Handler = ({ method, path, body, query }) => {
    let m: RegExpMatchArray | null;
    if (path === "/api/habits" && method === "GET") {
      const items = store.habits.map(summary);
      const due = items.filter((h) => h.active && !h.done_today && (h.frequency === "daily" || h.week.completed < h.week.target!)).length;
      return json({ items, due_today: due });
    }
    if (path === "/api/habits" && method === "POST") {
      const b = body as Partial<StoredHabit>;
      if (store.habits.some((h) => h.name.toLowerCase() === String(b.name).toLowerCase())) return json({ detail: "You already have a habit with that name" }, 409);
      const h = mkHabit({ ...b, start_date: b.start_date ?? today() });
      store.habits.push(h);
      return json(summary(h), 201);
    }
    if ((m = path.match(/^\/api\/habits\/(\d+)(?:\/logs(?:\/(\d{4}-\d{2}-\d{2}))?)?$/))) {
      const h = find(Number(m[1]));
      if (!h) return json({ detail: "Habit not found" }, 404);
      const day = m[2];
      const isLogs = path.includes("/logs");
      if (!isLogs && method === "GET") return json(summary(h));
      if (!isLogs && method === "PATCH") return json(summary(Object.assign(h, body)));
      if (!isLogs && method === "DELETE") {
        store.habits.splice(store.habits.indexOf(h), 1);
        return new Response(null, { status: 204 });
      }
      const logs = (store.logs[h.id] ??= []);
      if (isLogs && !day && method === "GET") return json([...logs].sort((a, b) => (a.date < b.date ? 1 : -1)).filter((l) => l.date >= addDays(today(), -(Number(query.days) - 1))));
      if (day && method === "PUT") {
        if (day > today()) return json({ detail: "You can't record a habit for a future day" }, 422);
        if (day < h.start_date) return json({ detail: `This habit starts on ${h.start_date}; earlier days can't be recorded` }, 422);
        const b = body as { completed: boolean; value: number | null; note: string | null };
        const i = logs.findIndex((l) => l.date === day);
        const rec = { date: day, completed: b.completed, value: b.value ?? null, note: b.note ?? null };
        if (i >= 0) logs[i] = rec;
        else logs.push(rec);
        return json(summary(h));
      }
      if (day && method === "DELETE") {
        const i = logs.findIndex((l) => l.date === day);
        if (i < 0) return json({ detail: "No record for that day" }, 404);
        logs.splice(i, 1);
        return json(summary(h));
      }
    }
    return undefined;
  };
  fake.handlers.push(handler);
  return store;
}
