import { Check, Minus, X } from "lucide-react";
import { cx } from "../../components/ui";
import type { ChallengeDay } from "../../api/reports";

/** Hand-built HTML charts (no chart library): thin bars with a rounded data end, a 2px surface gap between stacked segments, hairline
 *  recessive grid, one baseline, a legend for 2+ series, and a hover/focus tooltip per day. Every chart has a table twin (see DataTable). */

export type Series = { key: string; label: string; color: string; unit?: string };
export type Column = { key: string; short: string; long: string; values: Record<string, number | null>; note?: string };

const PLOT_HEIGHT = 168; // px, the plot area only; the x-axis labels sit below it so nothing is clipped

/** 0..max in about 4 whole-number steps of 1, 2 or 5 x 10^n (counts and minutes are never fractional). */
export function niceTicks(max: number, steps?: number[]): number[] {
  if (max <= 0) return [0, 1];
  const raw = max / 4;
  const mag = 10 ** Math.floor(Math.log10(raw));
  // `steps` lets an axis use steps that suit its unit (minutes step in 15, 30, 60 or 120, not 50)
  const step = steps ? (steps.find((s) => s >= raw) ?? Math.ceil(raw / 60) * 60) : Math.max(1, [1, 2, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? raw);
  const ticks: number[] = [];
  for (let v = 0; v < max + step; v += step) {
    ticks.push(v);
    if (v >= max) break;
  }
  return ticks;
}

export const MINUTE_STEPS = [5, 10, 15, 30, 60, 120, 180, 240];

export const formatMinutes = (m: number) => (m < 60 ? `${m}m` : `${Math.floor(m / 60)}h${m % 60 ? ` ${m % 60}m` : ""}`);

export function Legend({ series }: { series: Series[] }) {
  if (series.length < 2) return null; // one series: the title already says what is plotted
  return (
    <ul className="mb-2 flex flex-wrap gap-x-4 gap-y-1" aria-label="Legend">
      {series.map((s) => (
        <li key={s.key} className="flex items-center gap-1.5 text-xs text-slate-600 dark:text-slate-400">
          <span aria-hidden className="h-2.5 w-2.5 rounded-sm" style={{ background: s.color }} />
          {s.label}
        </li>
      ))}
    </ul>
  );
}

export function StackedBars({
  label,
  series,
  columns,
  format = (v) => String(v),
  fixedMax,
  steps,
}: {
  label: string; // the accessible name of the chart
  steps?: number[]; // axis steps that suit the unit (see MINUTE_STEPS)
  series: Series[];
  columns: Column[];
  format?: (v: number) => string;
  fixedMax?: number;
}) {
  const totals = columns.map((c) => series.reduce((sum, s) => sum + (c.values[s.key] ?? 0), 0));
  const ticks = fixedMax ? [0, fixedMax / 2, fixedMax] : niceTicks(Math.max(0, ...totals), steps);
  const max = ticks[ticks.length - 1];
  const dense = columns.length > 10;

  return (
    <div role="group" aria-label={label}>
      <Legend series={series} />
      <div className="flex pt-3">{/* headroom: the top axis label is centred on the top gridline and would otherwise touch the legend */}
        <div className="relative mr-2 w-12 shrink-0 text-right text-[11px] text-[var(--viz-muted)]" style={{ height: PLOT_HEIGHT }} aria-hidden>
          {ticks.map((t) => (
            <span key={t} className="absolute right-0 -translate-y-1/2 leading-none" style={{ bottom: `${(t / max) * 100}%` }}>
              {format(t)}
            </span>
          ))}
        </div>
        <div className="min-w-0 flex-1">
          <div className="relative" style={{ height: PLOT_HEIGHT }}>
            {ticks.map((t) => (
              <div key={t} aria-hidden className="absolute inset-x-0 border-t" style={{ bottom: `${(t / max) * 100}%`, borderColor: t === 0 ? "var(--viz-axis)" : "var(--viz-grid)" }} />
            ))}
            <div className="absolute inset-0 flex">
              {columns.map((c, i) => {
                const present = series.filter((s) => (c.values[s.key] ?? 0) > 0);
                const none = series.every((s) => c.values[s.key] === null);
                const name = none ? `${c.long}: ${c.note ?? "no data yet"}` : `${c.long}: ${series.map((s) => `${s.label} ${format(c.values[s.key] ?? 0)}`).join(", ")}`;
                const side = i < 2 ? "left-0" : i > columns.length - 3 ? "right-0" : "left-1/2 -translate-x-1/2";
                return (
                  <div
                    key={c.key}
                    tabIndex={0}
                    role="img"
                    aria-label={name}
                    className="group relative flex h-full min-w-0 flex-1 items-end justify-center rounded-sm outline-none hover:bg-slate-100/70 focus-visible:bg-slate-100/70 dark:hover:bg-slate-800/60 dark:focus-visible:bg-slate-800/60"
                  >
                    <div className={cx("flex w-full flex-col-reverse", dense ? "max-w-3" : "max-w-6")}>
                      {present.map((s, k) => {
                        const v = c.values[s.key] ?? 0;
                        return (
                          <div
                            key={s.key}
                            data-series={s.key}
                            className={cx(k === present.length - 1 && "rounded-t-[4px]")}
                            style={{ height: `${(v / max) * PLOT_HEIGHT}px`, minHeight: 2, background: s.color, marginBottom: k < present.length - 1 ? 2 : 0 }}
                          />
                        );
                      })}
                    </div>
                    <div
                      role="tooltip"
                      className={cx(
                        "pointer-events-none absolute bottom-full z-10 mb-1 hidden w-max min-w-36 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs shadow-md group-hover:block group-focus-visible:block dark:border-slate-700 dark:bg-slate-900",
                        side,
                      )}
                    >
                      <p className="font-medium text-slate-900 dark:text-white">{c.long}</p>
                      {none ? (
                        <p className="text-slate-500 dark:text-slate-400">{c.note ?? "Not happened yet"}</p>
                      ) : (
                        <>
                          {c.note && <p className="text-slate-500 dark:text-slate-400">{c.note}</p>}
                          {series.map((s) => (
                            <p key={s.key} className="mt-0.5 flex items-center gap-1.5 text-slate-700 dark:text-slate-300">
                              <span aria-hidden className="h-2 w-2 rounded-sm" style={{ background: s.color }} />
                              {s.label}: <b>{format(c.values[s.key] ?? 0)}</b>
                            </p>
                          ))}
                        </>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
          <div className="mt-1 flex" aria-hidden>
            {columns.map((c, i) => (
              <span key={c.key} className="min-w-0 flex-1 truncate text-center text-[11px] text-[var(--viz-muted)]">
                {dense ? (i % 5 === 0 ? c.short : "") : c.short}
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

/** The table twin of a chart: every value reachable without hover or colour. */
export function DataTable({ caption, series, columns, format = (v) => String(v) }: { caption: string; series: Series[]; columns: Column[]; format?: (v: number) => string }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr className="border-b border-slate-200 text-left text-xs text-slate-500 dark:border-slate-700 dark:text-slate-400">
            <th scope="col" className="py-1.5 pr-3 font-medium">
              Day
            </th>
            {series.map((s) => (
              <th key={s.key} scope="col" className="px-2 py-1.5 text-right font-medium">
                {s.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
          {columns.map((c) => (
            <tr key={c.key}>
              <th scope="row" className="whitespace-nowrap py-1.5 pr-3 text-left font-normal text-slate-700 dark:text-slate-300">
                {c.long}
              </th>
              {series.map((s) => (
                <td key={s.key} className="px-2 py-1.5 text-right tabular-nums text-slate-900 dark:text-slate-100">
                  {c.values[s.key] === null ? <span className="text-slate-400">{c.note ?? "–"}</span> : format(c.values[s.key] ?? 0)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ------------------------------------------------------------------ challenge strip

const CHALLENGE: Record<ChallengeDay, { label: string; box: string; icon?: typeof Check }> = {
  completed: { label: "Completed", box: "bg-[var(--viz-good)] text-white", icon: Check },
  missed: { label: "Missed", box: "bg-[var(--viz-critical)] text-white", icon: X },
  excused: { label: "Excused", box: "bg-slate-400 text-white dark:bg-slate-600", icon: Minus },
  planned: { label: "Planned", box: "border-2 border-slate-400 dark:border-slate-500" },
  in_progress: { label: "In progress", box: "border-2 border-slate-400 dark:border-slate-500" },
  none: { label: "Nothing planned", box: "bg-slate-100 dark:bg-slate-800" },
};

/** One square per day. Status colours always come with an icon and a name, never colour alone. */
export function ChallengeStrip({ days }: { days: { date: string; long: string; status: ChallengeDay }[] }) {
  return (
    <div>
      <ul className="flex flex-wrap gap-1.5" aria-label="Daily challenge by day">
        {days.map((d) => {
          const c = CHALLENGE[d.status];
          const Icon = c.icon;
          return (
            <li key={d.date} title={`${d.long}: ${c.label}`} aria-label={`${d.long}: ${c.label}`} className={cx("flex h-6 w-6 items-center justify-center rounded-md", c.box)}>
              {Icon && <Icon className="h-3.5 w-3.5" aria-hidden strokeWidth={3} />}
            </li>
          );
        })}
      </ul>
      <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-600 dark:text-slate-400" aria-label="Challenge key">
        {(["completed", "missed", "excused", "planned", "none"] as ChallengeDay[]).map((k) => {
          const Icon = CHALLENGE[k].icon;
          return (
            <li key={k} className="flex items-center gap-1.5">
              <span aria-hidden className={cx("flex h-3.5 w-3.5 items-center justify-center rounded", CHALLENGE[k].box)}>
                {Icon && <Icon className="h-2.5 w-2.5" strokeWidth={3} />}
              </span>
              {CHALLENGE[k].label}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
