/** 253 -> "4:13", 3723 -> "1:02:03". null when YouTube didn't report a length. */
export function formatDuration(seconds: number | null | undefined): string | null {
  if (seconds === null || seconds === undefined || seconds < 0) return null;
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  const ss = String(s).padStart(2, "0");
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${ss}` : `${m}:${ss}`;
}

/** "12 Oct 2026" in the user's time zone; null when there is no date. */
export function formatDate(iso: string | null | undefined, timeZone: string): string | null {
  if (!iso) return null;
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone });
}

/** "172" or "unavailable" - an unreported count is never turned into a number. */
export function countOrUnavailable(n: number | null | undefined): string {
  return n === null || n === undefined ? "unavailable" : String(n);
}
