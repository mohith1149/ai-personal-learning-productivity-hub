import { AlertTriangle, CheckCircle2, Target } from "lucide-react";
import { Link } from "react-router-dom";
import { useGoals, type Goal, type GoalStatus } from "../api/goals";
import { Badge, Card, cx } from "./ui";

const LABEL: Record<GoalStatus, string> = {
  done: "Done",
  overdue: "Past the date",
  behind: "Behind pace",
  stalled: "Stalled",
  not_started: "Not started",
  on_track: "On track",
  unknown: "Nothing to count yet",
};

const href = (g: Goal) => (g.kind === "course" ? `/courses/${g.id}` : `/projects/${g.id}`);

/** One goal's pace in a sentence. Used on the course and project pages. Renders nothing for an item without a target date. */
export function GoalPace({ kind, id }: { kind: Goal["kind"]; id: number }) {
  const goals = useGoals();
  const g = goals.data?.find((x) => x.kind === kind && x.id === id);
  if (!g) return null;
  return (
    <p
      role={g.warning ? "alert" : "status"}
      aria-label="Pace"
      className={cx(
        "mt-2 flex items-start gap-2 rounded-lg px-3 py-2 text-sm",
        g.warning ? "bg-amber-50 text-amber-900 dark:bg-amber-950/40 dark:text-amber-200" : "bg-slate-50 text-slate-700 dark:bg-slate-800/60 dark:text-slate-300",
      )}
    >
      {g.warning ? <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden /> : <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />}
      <span>{g.message}</span>
    </p>
  );
}

/** Courses and projects with a target date, worst first, with the pace needed against the pace you have. Hidden when there are none. */
export function GoalsCard() {
  const goals = useGoals();
  const list = (goals.data ?? []).filter((g) => g.status !== "done");
  if (list.length === 0) return null;
  const behind = list.filter((g) => g.warning).length;
  return (
    <Card aria-label="Goals and pace">
      <div className="flex items-center gap-2">
        <Target className="h-4 w-4 text-slate-500 dark:text-slate-400" aria-hidden />
        <h2 className="text-sm font-semibold text-slate-900 dark:text-white">Goals and pace</h2>
        {behind > 0 && <Badge tone="warn">{behind} need attention</Badge>}
      </div>
      <ul aria-label="Goals" className="mt-2 divide-y divide-slate-100 dark:divide-slate-800">
        {list.map((g) => (
          <li key={`${g.kind}:${g.id}`} className="py-2">
            <div className="flex flex-wrap items-center gap-2">
              <Link to={href(g)} className="text-sm font-medium text-slate-900 hover:underline dark:text-white">
                {g.title}
              </Link>
              <Badge tone={g.warning ? "warn" : g.status === "on_track" ? "brand" : "neutral"}>{LABEL[g.status]}</Badge>
              <span className="text-xs text-slate-500 dark:text-slate-400">
                {g.kind === "course" ? "Course" : "Project"} · {g.days_left} {g.days_left === 1 ? "day" : "days"} left · {g.remaining} {g.unit} to go
              </span>
            </div>
            <p className={cx("mt-0.5 text-xs", g.warning ? "text-amber-800 dark:text-amber-300" : "text-slate-600 dark:text-slate-400")}>{g.message}</p>
          </li>
        ))}
      </ul>
    </Card>
  );
}
