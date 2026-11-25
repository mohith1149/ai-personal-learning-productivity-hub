import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, Minus } from "lucide-react";
import { useState, type ReactNode } from "react";
import { useReport, type Report, type ReportKind, type Totals } from "../../api/reports";
import { Button, Card, cx, ErrorNotice, PageHeader, Spinner } from "../../components/ui";
import { addDays } from "../../lib/dates";
import { ChallengeStrip, DataTable, formatMinutes, MINUTE_STEPS, StackedBars, type Column, type Series } from "./charts";

const FINISHED: Series[] = [
  { key: "tasks_done", label: "Tasks", color: "var(--viz-tasks)" },
  { key: "lessons_done", label: "Lessons", color: "var(--viz-lessons)" },
  { key: "videos_done", label: "Videos", color: "var(--viz-videos)" },
  { key: "topics_done", label: "Roadmap topics", color: "var(--viz-topics)" },
];
const TIME: Series[] = [
  { key: "study_minutes", label: "Study", color: "var(--viz-study)" },
  { key: "project_minutes", label: "Projects", color: "var(--viz-project)" },
];
const PLAN: Series[] = [{ key: "percent", label: "Plan completed", color: "var(--viz-plan)" }];

const dayLong = (iso: string) => new Date(`${iso}T12:00:00`).toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" });
const dayShort = (iso: string, kind: ReportKind) => {
  const d = new Date(`${iso}T12:00:00`);
  return kind === "week" ? d.toLocaleDateString("en-GB", { weekday: "short" }) : String(d.getDate());
};

/** "2026-11-05" + n months -> "2026-12" */
function shiftMonth(iso: string, n: number): string {
  const y = Number(iso.slice(0, 4));
  const m = Number(iso.slice(5, 7)) - 1 + n;
  return `${y + Math.floor(m / 12)}-${String((((m % 12) + 12) % 12) + 1).padStart(2, "0")}`;
}

function columns(report: Report, values: (d: Report["days"][number]) => Record<string, number | null>, note?: (d: Report["days"][number]) => string | undefined): Column[] {
  return report.days.map((d) => ({ key: d.date, short: dayShort(d.date, report.period.kind), long: dayLong(d.date), values: values(d), note: note?.(d) }));
}

// ------------------------------------------------------------------ tiles

function Delta({ now, before, unit, label }: { now: number; before: number; unit?: (n: number) => string; label: string }) {
  const f = unit ?? String;
  if (now === 0 && before === 0) return <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">Nothing recorded in either</p>;
  const diff = now - before;
  const Icon = diff > 0 ? ArrowUp : diff < 0 ? ArrowDown : Minus;
  return (
    <p className={cx("mt-1 flex items-center gap-1 text-xs", diff > 0 ? "text-[var(--viz-up)]" : "text-slate-500 dark:text-slate-400")}>
      <Icon className="h-3 w-3" aria-hidden />
      {diff === 0 ? `No change vs ${label}` : `${diff > 0 ? "Up" : "Down"} ${f(Math.abs(diff))} vs ${label}`}
    </p>
  );
}

function Tile({ label, value, children }: { label: string; value: string; children?: ReactNode }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
      <p className="text-xs font-medium text-slate-500 dark:text-slate-400">{label}</p>
      <p className="mt-1 text-2xl font-semibold tracking-tight text-slate-900 dark:text-white">{value}</p>
      {children}
    </div>
  );
}

function Tiles({ r }: { r: Report }) {
  const t: Totals = r.totals;
  const p: Totals = r.previous;
  const before = r.period.kind === "week" ? "the same days last week" : "the same days last month";
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-3 xl:grid-cols-6" role="list" aria-label="Totals">
      <div role="listitem">
        <Tile label="Items finished" value={String(t.items_done)}>
          <Delta now={t.items_done} before={p.items_done} label={before} />
        </Tile>
      </div>
      <div role="listitem">
        <Tile label="Study time" value={formatMinutes(t.study_minutes)}>
          <Delta now={t.study_minutes} before={p.study_minutes} unit={formatMinutes} label={before} />
        </Tile>
      </div>
      <div role="listitem">
        <Tile label="Project time" value={formatMinutes(t.project_minutes)}>
          <Delta now={t.project_minutes} before={p.project_minutes} unit={formatMinutes} label={before} />
        </Tile>
      </div>
      <div role="listitem">
        <Tile label="Habit check-ins" value={String(t.habits_done)}>
          <Delta now={t.habits_done} before={p.habits_done} label={before} />
        </Tile>
      </div>
      <div role="listitem">
        <Tile label="Plan completed" value={`${r.plan.percent}%`}>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{r.plan.total === 0 ? "Nothing was planned" : `${r.plan.completed} of ${r.plan.total} planned items`}</p>
        </Tile>
      </div>
      <div role="listitem">
        <Tile label="Challenge days" value={String(t.challenge_days)}>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            {r.challenge.missed} missed · streak {r.challenge.current_streak}
          </p>
        </Tile>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ cards

function ChartCard({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <Card aria-label={title}>
      <h2 className="text-sm font-semibold text-slate-900 dark:text-white">{title}</h2>
      {hint && <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">{hint}</p>}
      <div className="mt-3">{children}</div>
    </Card>
  );
}

function Charts({ r, tables }: { r: Report; tables: boolean }) {
  const finished = columns(r, (d) => ({ tasks_done: d.tasks_done, lessons_done: d.lessons_done, videos_done: d.videos_done, topics_done: d.topics_done }));
  const time = columns(r, (d) => ({ study_minutes: d.study_minutes, project_minutes: d.project_minutes }));
  const plan = columns(
    r,
    (d) => ({ percent: d.plan_total === null ? null : d.plan_total === 0 ? 0 : Math.floor((100 * (d.plan_completed ?? 0)) / d.plan_total) }),
    (d) => (d.plan_total === null ? "Not happened yet" : d.plan_total === 0 ? "Nothing was planned" : `${d.plan_completed} of ${d.plan_total} planned items`),
  );
  const pct = (v: number) => `${v}%`;
  return (
    <>
      <ChartCard title="Finished each day" hint="Tasks, lessons, videos and roadmap topics you completed.">
        {tables ? <DataTable caption="Finished each day" series={FINISHED} columns={finished} /> : <StackedBars label="Finished each day" series={FINISHED} columns={finished} />}
      </ChartCard>
      <ChartCard title="Time spent each day" hint="Minutes you logged on courses and topics (study) and on projects.">
        {tables ? <DataTable caption="Time spent each day" series={TIME} columns={time} format={formatMinutes} /> : <StackedBars label="Time spent each day" series={TIME} columns={time} format={formatMinutes} steps={MINUTE_STEPS} />}
      </ChartCard>
      <ChartCard title="Plan completed each day" hint="The share of that day's planned items you finished. Days that have not happened yet are blank.">
        {tables ? (
          <DataTable caption="Plan completed each day" series={PLAN} columns={plan} format={pct} />
        ) : (
          <StackedBars label="Plan completed each day" series={PLAN} columns={plan} format={pct} fixedMax={100} />
        )}
      </ChartCard>
      <ChartCard title="Daily challenge" hint={`${r.challenge.completed} completed${r.challenge.verified ? ` (${r.challenge.verified} checked on GitHub)` : ""}, ${r.challenge.missed} missed, ${r.challenge.excused} excused.`}>
        <ChallengeStrip days={r.days.map((d) => ({ date: d.date, long: dayLong(d.date), status: d.challenge }))} />
      </ChartCard>
    </>
  );
}

function Lists({ r }: { r: Report }) {
  const top = Math.max(1, ...r.projects.map((p) => p.minutes));
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Card aria-label="Time by project">
        <h2 className="text-sm font-semibold text-slate-900 dark:text-white">Time by project</h2>
        {r.projects.length === 0 ? (
          <p className="mt-3 text-sm text-slate-500 dark:text-slate-400">No project time was logged in this period.</p>
        ) : (
          <ul className="mt-3 space-y-3">
            {r.projects.map((p) => (
              <li key={p.project_id}>
                <div className="flex items-baseline justify-between gap-3 text-sm">
                  <span className="min-w-0 truncate text-slate-800 dark:text-slate-200">{p.title}</span>
                  <span className="shrink-0 text-slate-600 dark:text-slate-400">{formatMinutes(p.minutes)}</span>
                </div>
                <div className="mt-1 h-2 rounded-full bg-slate-100 dark:bg-slate-800" aria-hidden>
                  <div className="h-2 rounded-full" style={{ width: `${(p.minutes / top) * 100}%`, background: "var(--viz-project)" }} />
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Card aria-label="Habits">
        <h2 className="text-sm font-semibold text-slate-900 dark:text-white">Habits</h2>
        {r.habits.length === 0 ? (
          <p className="mt-3 text-sm text-slate-500 dark:text-slate-400">No habit was checked off in this period.</p>
        ) : (
          <ul className="mt-3 divide-y divide-slate-100 dark:divide-slate-800">
            {r.habits.map((h) => (
              <li key={h.habit_id} className="flex items-baseline justify-between gap-3 py-2 text-sm">
                <span className="min-w-0 truncate text-slate-800 dark:text-slate-200">{h.name}</span>
                <span className="shrink-0 text-slate-600 dark:text-slate-400">
                  {h.done_days} day{h.done_days === 1 ? "" : "s"}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

// ------------------------------------------------------------------ page

function Segmented<T extends string>({ value, options, onChange, label }: { value: T; options: { value: T; label: string }[]; onChange: (v: T) => void; label: string }) {
  return (
    <div role="group" aria-label={label} className="inline-flex rounded-lg border border-slate-200 bg-slate-100 p-0.5 dark:border-slate-700 dark:bg-slate-800">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          aria-pressed={o.value === value}
          onClick={() => onChange(o.value)}
          className={cx(
            "rounded-md px-3 py-1 text-sm font-medium transition",
            o.value === value ? "bg-white text-brand-700 shadow-sm dark:bg-slate-950 dark:text-brand-400" : "text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

function empty(r: Report) {
  const t = r.totals;
  return t.items_done + t.study_minutes + t.project_minutes + t.habits_done + t.challenge_days === 0;
}

export function ReportsPage() {
  const [kind, setKind] = useState<ReportKind>("week");
  const [anchor, setAnchor] = useState<string | null>(null);
  const [tables, setTables] = useState(false);
  const q = useReport(kind, anchor);
  const r = q.data;

  const go = (dir: -1 | 1) => {
    if (!r) return;
    setAnchor(kind === "week" ? addDays(r.period.start, 7 * dir) : shiftMonth(r.period.start, dir));
  };

  return (
    <>
      <PageHeader title="Reports" description="What you actually did, from your own records. Nothing here is estimated." />
      <div className="viz space-y-4">
        <div className="flex flex-wrap items-center gap-3" role="toolbar" aria-label="Report options">
          <Segmented
            label="Period"
            value={kind}
            options={[
              { value: "week", label: "Week" },
              { value: "month", label: "Month" },
            ]}
            onChange={(k) => {
              setKind(k);
              setAnchor(null);
            }}
          />
          <div className="flex items-center gap-1">
            <Button variant="secondary" icon={ChevronLeft} aria-label={`Previous ${kind}`} disabled={!r} onClick={() => go(-1)} className="px-2 py-1.5" />
            <p aria-live="polite" className="min-w-44 text-center text-sm font-medium text-slate-900 dark:text-white">
              {r ? r.period.label : "…"}
            </p>
            <Button variant="secondary" icon={ChevronRight} aria-label={`Next ${kind}`} disabled={!r || r.period.is_current} onClick={() => go(1)} className="px-2 py-1.5" />
            {r && !r.period.is_current && (
              <Button variant="ghost" onClick={() => setAnchor(null)} className="ml-1 px-2.5 py-1.5 text-xs">
                This {kind}
              </Button>
            )}
          </div>
          <div className="ml-auto">
            <Segmented
              label="View"
              value={tables ? "tables" : "charts"}
              options={[
                { value: "charts", label: "Charts" },
                { value: "tables", label: "Tables" },
              ]}
              onChange={(v) => setTables(v === "tables")}
            />
          </div>
        </div>

        {q.isPending ? (
          <Spinner label="Loading the report…" />
        ) : q.isError ? (
          <ErrorNotice error={q.error} onRetry={() => q.refetch()} />
        ) : (
          r && (
            <div className={cx("space-y-4 transition-opacity", q.isPlaceholderData && "opacity-60")} aria-busy={q.isPlaceholderData}>
              {empty(r) && (
                <p role="status" className="rounded-lg border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400">
                  Nothing was recorded in this {kind}. Finished tasks, lessons, videos, study and project time, habit check-ins and daily challenges will appear here.
                </p>
              )}
              <Tiles r={r} />
              <div className="grid gap-4 xl:grid-cols-2">
                <Charts r={r} tables={tables} />
              </div>
              <Lists r={r} />
            </div>
          )
        )}
      </div>
    </>
  );
}
