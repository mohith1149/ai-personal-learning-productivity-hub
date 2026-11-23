/** Date helpers. Dates travel as "YYYY-MM-DD" strings (no time zone), exactly like the API,
 *  so there is no off-by-one-day risk from Date objects drifting across time zones. */

const DAY_MS = 86_400_000;

function toUtcMs(iso: string): number {
  const [y, m, d] = iso.split("-").map(Number);
  return Date.UTC(y, m - 1, d);
}

/** Today's date in the given IANA time zone (the user's configured one, not necessarily the browser's). */
export function todayIn(timeZone: string, now: Date = new Date()): string {
  try {
    return new Intl.DateTimeFormat("en-CA", { timeZone, year: "numeric", month: "2-digit", day: "2-digit" }).format(now);
  } catch {
    return new Intl.DateTimeFormat("en-CA", { year: "numeric", month: "2-digit", day: "2-digit" }).format(now);
  }
}

export function addDays(iso: string, n: number): string {
  return new Date(toUtcMs(iso) + n * DAY_MS).toISOString().slice(0, 10);
}

/** Whole days from a to b (positive when b is later). */
export function daysBetween(a: string, b: string): number {
  return Math.round((toUtcMs(b) - toUtcMs(a)) / DAY_MS);
}

export function formatDay(iso: string, today: string): string {
  const diff = daysBetween(today, iso);
  if (diff === 0) return "Today";
  if (diff === 1) return "Tomorrow";
  if (diff === -1) return "Yesterday";
  const sameYear = iso.slice(0, 4) === today.slice(0, 4);
  return new Date(toUtcMs(iso)).toLocaleDateString("en-GB", {
    weekday: "short",
    day: "numeric",
    month: "short",
    year: sameYear ? undefined : "numeric",
    timeZone: "UTC",
  });
}

export const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"] as const;

/** "Due Tomorrow 09:30" / "3 days overdue" — the overdue decision itself always comes from the server. */
export function describeDue(
  t: { due_date: string | null; due_time: string | null; is_overdue: boolean },
  today: string,
): { text: string; overdue: boolean } | null {
  if (!t.due_date) return null;
  const time = t.due_time ? ` ${t.due_time}` : "";
  if (t.is_overdue) {
    const days = -daysBetween(today, t.due_date);
    return { text: days <= 0 ? `Overdue (was due${time})` : `${days} day${days === 1 ? "" : "s"} overdue`, overdue: true };
  }
  return { text: `${formatDay(t.due_date, today)}${time}`, overdue: false };
}
