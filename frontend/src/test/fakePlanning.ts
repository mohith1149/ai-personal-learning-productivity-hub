/** Rest days and planning preferences for the fake API (installed by default, like notifications). Real rules are tested in pytest. */
import type { Preferences, RestMonth } from "../api/planner";
import type { Handler } from "./fakeApi";

export type FakePlanning = { prefs: Preferences; restDays: { date: string; reason: string | null }[]; today: () => string };

export const newFakePlanning = (today: () => string): FakePlanning => ({ prefs: { weekday_minutes: null, rest_days_per_month: 4 }, restDays: [], today });

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
    return undefined;
  };
}
