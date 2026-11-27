/** Planner endpoints for the fake API. Days hold plan items; actions change an item's status and the summary is recomputed the way the
 *  server does (excused items are left out of the percentage). What belongs on a day, and the owning feature's rules, are tested in pytest. */
import type { DayPlan, ItemStatus, Kind, PlanItem } from "../api/planner";
import { addDays, todayIn } from "../lib/dates";
import { USER, type Fake, type Handler } from "./fakeApi";

export type FakePlanner = { days: Record<string, PlanItem[]> };

let nextId = 8000;

export function mkItem(o: Partial<PlanItem> & { kind: Kind }): PlanItem {
  const ref = o.ref_id ?? nextId++;
  const canAct = o.status !== "excused";
  return {
    key: `${o.kind}:${ref}`, ref_id: ref, title: `${o.kind} ${ref}`, subtitle: null, status: "pending", due_date: null, minutes: null, excuse_reason: null,
    can_complete: o.kind !== "project", can_reschedule: o.kind === "task", can_excuse: canAct, link: `/${o.kind}s`, url: null, carry_count: 0, slipping: (o.carry_count ?? 0) >= 3, ...o,
  };
}

const ORDER: Record<ItemStatus, number> = { overdue: 0, pending: 1, completed: 2, excused: 3 };

export function installFakePlanner(fake: Fake, seed: FakePlanner = { days: {} }): FakePlanner {
  const store = seed;
  const json = (d: unknown, status = 200) => Response.json(d, { status });
  const today = () => todayIn(USER.timezone);

  const plan = (day: string): DayPlan => {
    const restDay = fake.planning.restDays.some((d) => d.date === day);
    const items = [...(store.days[day] ?? [])]
      .map((i) => (restDay && (i.status === "pending" || i.status === "overdue") ? { ...i, status: "excused" as const, excuse_reason: "Rest day" } : i))
      .map((i) => ({ ...i, can_complete: i.can_complete && (day === today() || i.kind === "habit") && day <= today(), can_reschedule: i.can_reschedule && day <= today() && i.status !== "completed", can_excuse: !restDay && day <= today() && i.status !== "completed" }))
      .sort((a, b) => ORDER[a.status] - ORDER[b.status]);
    const counted = items.filter((i) => i.status !== "excused");
    const done = counted.filter((i) => i.status === "completed").length;
    const kinds = [...new Set(counted.map((i) => i.kind))];
    return {
      date: day, is_today: day === today(), items,
      summary: {
        total: counted.length, completed: done, pending: counted.filter((i) => i.status === "pending").length, overdue: counted.filter((i) => i.status === "overdue").length,
        excused: items.length - counted.length, percent: counted.length ? Math.floor((100 * done) / counted.length) : 0, study_minutes: 0, dev_minutes: 0,
        by_kind: kinds.map((k) => ({ kind: k, total: counted.filter((i) => i.kind === k).length, completed: counted.filter((i) => i.kind === k && i.status === "completed").length })),
        ...load(day, counted, restDay),
      },
    };
  };
  const load = (day: string, counted: PlanItem[], restDay: boolean) => {
    const week = fake.planning.prefs.weekday_minutes;
    const weekday = (new Date(`${day}T12:00:00`).getDay() + 6) % 7;
    const available = week ? week[weekday] : null;
    const planned = counted.reduce((n, i) => n + (i.minutes ?? 0), 0);
    return {
      rest_day: restDay, planned_minutes: planned, available_minutes: available,
      unestimated: counted.filter((i) => i.minutes === null && i.status !== "completed").length, overloaded: !restDay && available !== null && planned > available,
    };
  };
  const find = (day: string, kind: string, id: number) => (store.days[day] ?? []).find((i) => i.kind === kind && i.ref_id === id);

  const handler: Handler = ({ method, path, query, body }) => {
    if (path === "/api/planner" && method === "GET") return json(plan(query.day ?? today()));
    const b = body as { kind: Kind; ref_id: number; date: string; reason?: string; from_date?: string; move_due_date?: boolean } | undefined;
    if (path === "/api/planner/complete" || path === "/api/planner/reopen") {
      const it = find(b!.date, b!.kind, b!.ref_id);
      if (!it) return json({ detail: "Not found" }, 404);
      if (b!.date !== today() && b!.kind !== "habit") return json({ detail: "This can only be completed or reopened on today's plan" }, 422);
      it.status = path.endsWith("complete") ? "completed" : "pending";
      return json(plan(b!.date));
    }
    if (path === "/api/planner/excuse") {
      const it = find(b!.date, b!.kind, b!.ref_id);
      if (!it) return json({ detail: "That activity isn't on this day's plan" }, 422);
      if (it.status === "completed") return json({ detail: "A completed activity doesn't need an excuse" }, 422);
      it.status = "excused";
      it.excuse_reason = b!.reason ?? null;
      return json(plan(b!.date));
    }
    if (path === "/api/planner/unexcuse") {
      const it = find(b!.date, b!.kind, b!.ref_id);
      if (!it || it.status !== "excused") return json({ detail: "That activity isn't excused" }, 404);
      it.status = "pending";
      it.excuse_reason = null;
      return json(plan(b!.date));
    }
    const m = path.match(/^\/api\/planner\/tasks\/(\d+)\/reschedule$/);
    if (m && method === "POST") {
      const from = b!.from_date!;
      const it = find(from, "task", Number(m[1]));
      if (!it) return json({ detail: "Task not found" }, 404);
      if (b!.date < today()) return json({ detail: "A task can't be rescheduled into the past" }, 422);
      store.days[from] = store.days[from].filter((x) => x !== it);
      (store.days[b!.date] ??= []).push({ ...it, status: "pending" }); // moved, still not completed
      return json(plan(from));
    }
    if (path === "/api/planner/roll-over" && method === "POST") {
      const dry = (body as { dry_run?: boolean }).dry_run === true;
      const tomorrow = addDays(today(), 1);
      const open = (store.days[today()] ?? []).filter((i) => i.kind === "task" && (i.status === "pending" || i.status === "overdue"));
      const moved = open.map((i) => ({ task_id: i.ref_id, title: i.title, carry_count: i.carry_count + 1, minutes: i.minutes, slipping: i.carry_count + 1 >= 3 }));
      if (!dry) {
        store.days[today()] = (store.days[today()] ?? []).filter((i) => !open.includes(i));
        (store.days[tomorrow] ??= []).push(...open.map((i) => ({ ...i, status: "pending" as const, carry_count: i.carry_count + 1, slipping: i.carry_count + 1 >= 3 })));
      }
      const after = [...(store.days[tomorrow] ?? []), ...(dry ? open : [])];
      const l = load(tomorrow, after, fake.planning.restDays.some((d) => d.date === tomorrow));
      return json({ dry_run: dry, moved, tomorrow: { date: tomorrow, total: after.length, planned_minutes: l.planned_minutes, available_minutes: l.available_minutes, overloaded: l.overloaded, unestimated: l.unestimated, rest_day: l.rest_day } });
    }
    return undefined;
  };
  fake.handlers.push(handler);
  return store;
}
