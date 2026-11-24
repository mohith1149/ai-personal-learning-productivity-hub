import { Compass } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { useAuthStatus } from "../../api/auth";
import { STATUS_LABEL } from "../../api/challenges";
import { useDashboard, type Dashboard } from "../../api/dashboard";
import { KIND_LABEL } from "../../api/planner";
import { Badge, Card, EmptyState, ErrorNotice, PageHeader, ProgressBar, Spinner } from "../../components/ui";
import { formatDay } from "../../lib/dates";

function greeting(timeZone: string): string {
  // "Good morning" is based on the user's configured timezone, not the browser's.
  let hour: number;
  try {
    hour = Number(new Intl.DateTimeFormat("en-GB", { hour: "numeric", hour12: false, timeZone }).format(new Date()));
  } catch {
    hour = new Date().getHours();
  }
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

const formatMinutes = (m: number) => (m >= 60 ? `${Math.floor(m / 60)}h ${m % 60}m` : `${m}m`);

function Panel({ title, to, linkLabel, children }: { title: string; to: string; linkLabel: string; children: ReactNode }) {
  return (
    <Card aria-label={title}>
      <div className="flex items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold text-slate-900 dark:text-white">{title}</h2>
        <Link to={to} className="text-xs text-brand-600 hover:underline dark:text-brand-400">
          {linkLabel}
        </Link>
      </div>
      <div className="mt-3">{children}</div>
    </Card>
  );
}

const Muted = ({ children }: { children: ReactNode }) => <p className="text-sm text-slate-500 dark:text-slate-400">{children}</p>;

function Fact({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <dt className="text-xs text-slate-500 dark:text-slate-400">{label}</dt>
      <dd className="text-lg font-semibold tabular-nums text-slate-900 dark:text-white">{value}</dd>
    </div>
  );
}

function TodayPanel({ d }: { d: Dashboard }) {
  const s = d.plan.summary;
  return (
    <Panel title="Today's plan" to="/planner" linkLabel="Open planner">
      {s.total === 0 && d.plan.next_items.length === 0 ? (
        <Muted>Nothing is planned for today.</Muted>
      ) : (
        <>
          <div className="flex items-end justify-between">
            <p className="text-sm text-slate-700 dark:text-slate-300">
              <span className="text-lg font-semibold tabular-nums text-slate-900 dark:text-white">
                {s.completed}/{s.total}
              </span>{" "}
              done{s.overdue > 0 && <span className="text-red-600 dark:text-red-400"> · {s.overdue} overdue</span>}
            </p>
            <span className="text-sm tabular-nums text-slate-600 dark:text-slate-300">{s.percent}%</span>
          </div>
          <div className="mt-2">
            <ProgressBar percent={s.percent} label="Today's progress" />
          </div>
          {d.plan.next_items.length > 0 && (
            <ul aria-label="Up next" className="mt-3 divide-y divide-slate-100 dark:divide-slate-800">
              {d.plan.next_items.map((i) => (
                <li key={i.key} className="flex items-center gap-2 py-1.5 text-sm">
                  <Badge tone={i.status === "overdue" ? "neutral" : "brand"}>{KIND_LABEL[i.kind]}</Badge>
                  <Link to={i.link} className="min-w-0 flex-1 truncate text-slate-900 hover:underline dark:text-slate-100">
                    {i.title}
                  </Link>
                  {i.status === "overdue" && <span className="text-xs text-red-600 dark:text-red-400">overdue</span>}
                </li>
              ))}
            </ul>
          )}
          {d.plan.open_count > d.plan.next_items.length && <Muted>and {d.plan.open_count - d.plan.next_items.length} more on the planner.</Muted>}
        </>
      )}
    </Panel>
  );
}

function VideosPanel({ d }: { d: Dashboard }) {
  return (
    <Panel title="Videos to watch today" to="/videos" linkLabel="Open videos">
      {d.videos.length === 0 ? (
        <Muted>No collection has a daily target. Set one on the Videos page.</Muted>
      ) : (
        <ul className="space-y-3">
          {d.videos.map((v) => (
            <li key={v.playlist_id}>
              <p className="text-sm font-medium text-slate-900 dark:text-white">
                {v.name}: watched {v.watched_today} of {v.daily_target}
                {v.target_met && <span className="ml-2 text-emerald-600 dark:text-emerald-400">target met</span>}
              </p>
              {v.up_next.length > 0 && (
                <ul className="mt-1 list-disc pl-5 text-sm text-slate-600 dark:text-slate-400">
                  {v.up_next.map((t, i) => (
                    <li key={i}>{t}</li>
                  ))}
                </ul>
              )}
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

function ChallengePanel({ d }: { d: Dashboard }) {
  const c = d.challenge.today;
  const st = d.challenge.stats;
  return (
    <Panel title="Daily challenge" to="/challenge" linkLabel="Open challenge">
      {c ? (
        <p className="text-sm text-slate-700 dark:text-slate-300">
          <Badge tone={c.status === "completed" ? "brand" : "neutral"}>{STATUS_LABEL[c.status]}</Badge> <span className="ml-1">{c.planned_task}</span>
          {c.project && <span className="text-slate-500 dark:text-slate-400"> · {c.project.title}</span>}
        </p>
      ) : (
        <Muted>Today's challenge isn't planned yet.</Muted>
      )}
      <dl className="mt-3 grid grid-cols-3 gap-3">
        <Fact label="Current streak" value={`${st.current_streak} ${st.current_streak === 1 ? "day" : "days"}`} />
        <Fact label="Longest streak" value={`${st.longest_streak} ${st.longest_streak === 1 ? "day" : "days"}`} />
        <Fact label="Missed days" value={st.missed} />
      </dl>
    </Panel>
  );
}

function HabitsPanel({ d }: { d: Dashboard }) {
  const h = d.habits;
  return (
    <Panel title="Habits" to="/habits" linkLabel="Open habits">
      {h.active === 0 ? (
        <Muted>No active habits.</Muted>
      ) : (
        <dl className="grid grid-cols-2 gap-3">
          <Fact label="Due today" value={h.due_today} />
          <Fact label="Best current streak" value={h.best_streak > 0 ? `${h.best_streak} ${h.best_streak_unit}` : "none yet"} />
        </dl>
      )}
      {h.best_streak_name && <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">{h.best_streak_name}</p>}
    </Panel>
  );
}

function TasksPanel({ d }: { d: Dashboard }) {
  const t = d.tasks;
  return (
    <Panel title="Tasks" to="/tasks" linkLabel="Open tasks">
      <dl className="grid grid-cols-3 gap-3">
        <Fact label="Overdue" value={t.overdue} />
        <Fact label="Due today" value={t.today} />
        <Fact label="Completed today" value={t.completed_today} />
      </dl>
    </Panel>
  );
}

function Bars({ title, rows, label }: { title: string; rows: { id: number; title: string; percent: number; detail?: string }[]; label: string }) {
  return (
    <ul aria-label={title} className="space-y-3">
      {rows.map((r) => (
        <li key={r.id}>
          <div className="flex items-baseline justify-between gap-2">
            <Link to={`/${label}/${r.id}`} className="min-w-0 truncate text-sm font-medium text-slate-900 hover:underline dark:text-white">
              {r.title}
            </Link>
            <span className="text-xs tabular-nums text-slate-600 dark:text-slate-300">{r.percent}%</span>
          </div>
          <ProgressBar percent={r.percent} label={`${r.title} progress`} />
          {r.detail && <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">{r.detail}</p>}
        </li>
      ))}
    </ul>
  );
}

function ProjectsPanel({ d }: { d: Dashboard }) {
  return (
    <Panel title="Active projects" to="/projects" linkLabel="Open projects">
      {d.projects.length === 0 ? (
        <Muted>No active projects.</Muted>
      ) : (
        <Bars title="Project progress" label="projects" rows={d.projects.map((p) => ({ id: p.id, title: p.title, percent: p.percent, detail: p.minutes_spent ? `${formatMinutes(p.minutes_spent)} spent` : "No time logged yet" }))} />
      )}
    </Panel>
  );
}

function CoursesPanel({ d }: { d: Dashboard }) {
  return (
    <Panel title="Active courses" to="/courses" linkLabel="Open courses">
      {d.courses.length === 0 ? (
        <Muted>No active courses.</Muted>
      ) : (
        <Bars title="Course progress" label="courses" rows={d.courses.map((c) => ({ id: c.id, title: c.title, percent: c.percent, detail: c.next_lesson ? `Next: ${c.next_lesson}` : "No lesson left" }))} />
      )}
    </Panel>
  );
}

function RoadmapPanel({ d }: { d: Dashboard }) {
  const r = d.roadmap;
  return (
    <Panel title="AI roadmap" to="/roadmap" linkLabel="Open roadmap">
      <div className="flex items-baseline justify-between">
        <p className="text-sm text-slate-700 dark:text-slate-300">
          {r.completed} of {r.total} topics completed{r.in_progress > 0 && `, ${r.in_progress} in progress`}
        </p>
        <span className="text-xs tabular-nums text-slate-600 dark:text-slate-300">{r.percent}%</span>
      </div>
      <div className="mt-2">
        <ProgressBar percent={r.percent} label="Roadmap progress" />
      </div>
      {r.next_topic && <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">Next topic: {r.next_topic}</p>}
    </Panel>
  );
}

function WeekPanel({ d }: { d: Dashboard }) {
  const max = Math.max(1, ...d.week.map((w) => w.study_minutes + w.dev_minutes));
  const total = d.week.reduce((n, w) => n + w.study_minutes + w.dev_minutes, 0);
  return (
    <Card aria-label="Last 7 days">
      <h2 className="text-sm font-semibold text-slate-900 dark:text-white">Last 7 days</h2>
      {total === 0 ? (
        <p className="mt-3 text-sm text-slate-500 dark:text-slate-400">No study or project time logged in the last 7 days.</p>
      ) : (
        <ul className="mt-3 space-y-1.5">
          {d.week.map((w) => (
            <li key={w.date} className="flex items-center gap-3 text-xs">
              <span className="w-20 shrink-0 text-slate-600 dark:text-slate-400">{formatDay(w.date, d.date)}</span>
              <span className="flex h-3 flex-1 overflow-hidden rounded bg-slate-100 dark:bg-slate-800" aria-hidden>
                <span className="bg-brand-500" style={{ width: `${(100 * w.study_minutes) / max}%` }} />
                <span className="bg-emerald-500" style={{ width: `${(100 * w.dev_minutes) / max}%` }} />
              </span>
              <span className="w-40 shrink-0 text-right tabular-nums text-slate-600 dark:text-slate-300">
                {formatMinutes(w.study_minutes)} study · {formatMinutes(w.dev_minutes)} projects
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

export function DashboardPage() {
  const user = useAuthStatus().data?.user;
  const dash = useDashboard();
  if (!user) return null;
  return (
    <>
      <PageHeader title={`${greeting(user.timezone)}, ${user.display_name}`} description="Today at a glance. Every figure is worked out from your own records." />
      {dash.isPending ? (
        <Spinner label="Loading your dashboard…" />
      ) : dash.isError ? (
        <ErrorNotice error={dash.error} onRetry={() => dash.refetch()} />
      ) : dash.data.is_empty ? (
        <EmptyState icon={Compass} title="Nothing to show yet">
          Add something and this page fills in from your real data: a <Link to="/tasks" className="underline">task</Link>, a <Link to="/courses" className="underline">course</Link>, a{" "}
          <Link to="/videos" className="underline">video collection</Link>, a <Link to="/habits" className="underline">habit</Link> or a <Link to="/projects" className="underline">project</Link>, or plan
          today's <Link to="/challenge" className="underline">challenge</Link>. Until then there is nothing to count.
        </EmptyState>
      ) : (
        <div className="space-y-4">
          <div className="grid gap-4 lg:grid-cols-2">
            <TodayPanel d={dash.data} />
            <VideosPanel d={dash.data} />
            <ChallengePanel d={dash.data} />
            <TasksPanel d={dash.data} />
            <HabitsPanel d={dash.data} />
            <RoadmapPanel d={dash.data} />
            <ProjectsPanel d={dash.data} />
            <CoursesPanel d={dash.data} />
          </div>
          <WeekPanel d={dash.data} />
        </div>
      )}
    </>
  );
}
