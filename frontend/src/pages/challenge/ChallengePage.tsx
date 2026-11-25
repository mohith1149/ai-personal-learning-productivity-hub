import { CheckCircle2, ExternalLink, EyeOff, Lightbulb, Play, Trash2 } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import {
  STATUS_LABEL,
  useCalendar,
  useCompleteChallenge,
  useDeleteChallenge,
  useExcuseDay,
  useHistory,
  usePlanChallenge,
  useStartChallenge,
  useToday,
  useVerifyChallenge,
  type CalendarDay,
  type CalendarStatus,
  type Challenge,
  type Mode,
  type Stats,
  type Suggestion,
} from "../../api/challenges";
import { useProjects } from "../../api/projects";
import { FormError, SelectInput, TextArea, TextInput } from "../../components/forms";
import { Modal } from "../../components/Modal";
import { Badge, Button, Card, EmptyState, ErrorNotice, PageHeader, Spinner, cx } from "../../components/ui";
import { formatDay } from "../../lib/dates";

const formatMinutes = (m: number) => (m >= 60 ? `${Math.floor(m / 60)}h ${m % 60}m` : `${m}m`);

const TONE: Record<CalendarStatus, string> = {
  completed: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
  excused: "bg-sky-100 text-sky-800 dark:bg-sky-950 dark:text-sky-300",
  missed: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300",
  in_progress: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
  planned: "bg-slate-200 text-slate-800 dark:bg-slate-800 dark:text-slate-200",
  none: "bg-slate-50 text-slate-400 dark:bg-slate-900 dark:text-slate-600",
};

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <dt className="text-xs text-slate-500 dark:text-slate-400">{label}</dt>
      <dd className="text-lg font-semibold tabular-nums text-slate-900 dark:text-white">{value}</dd>
    </div>
  );
}

function StatsCard({ stats }: { stats: Stats }) {
  return (
    <Card aria-label="Challenge statistics">
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <Stat label="Current streak" value={`${stats.current_streak} ${stats.current_streak === 1 ? "day" : "days"}`} />
        <Stat label="Longest streak" value={`${stats.longest_streak} ${stats.longest_streak === 1 ? "day" : "days"}`} />
        <Stat label="Completed" value={stats.completed} />
        <Stat label="Missed" value={stats.missed} />
        <Stat label="Excused" value={stats.excused} />
        <Stat label="Time" value={formatMinutes(stats.total_minutes)} />
      </dl>
      <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
        {stats.first_day ? `Since ${stats.first_day}: ${stats.completion_rate}% of days completed. Excused days don't break a streak.` : "Your streak starts with your first challenge."}
      </p>
    </Card>
  );
}

// ---------------------------------------------------------------- planning

function PlanForm({ suggestion, onClear }: { suggestion: Suggestion | null; onClear: () => void }) {
  const plan = usePlanChallenge();
  const projects = useProjects("active");
  const [mode, setMode] = useState<Mode>(suggestion?.mode ?? "existing_project");
  const [projectId, setProjectId] = useState(suggestion?.project_id ? String(suggestion.project_id) : "");
  const [title, setTitle] = useState("");
  const [repo, setRepo] = useState("");
  const [task, setTask] = useState(suggestion?.planned_task ?? "");
  const [minutes, setMinutes] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);
  const list = projects.data ?? [];

  return (
    <form
      className="space-y-4"
      noValidate
      onSubmit={(e) => {
        e.preventDefault();
        setLocalError(null);
        if (mode === "existing_project" && !projectId) return setLocalError("Choose the project you will continue.");
        if (mode === "new_project" && !title.trim()) return setLocalError("Name the new project.");
        if (task.trim().length < 3) return setLocalError("Say what you will build or do today.");
        const mins = minutes.trim() ? Number(minutes) : undefined;
        if (mins !== undefined && !(Number.isInteger(mins) && mins >= 1 && mins <= 1440)) return setLocalError("Estimated minutes must be a whole number from 1 to 1440.");
        plan.mutate(
          {
            mode,
            planned_task: task.trim(),
            ...(mode === "existing_project" ? { project_id: Number(projectId) } : { new_project: { title: title.trim(), ...(repo.trim() ? { repo_url: repo.trim() } : {}) } }),
            ...(mins !== undefined ? { estimated_minutes: mins } : {}),
          },
          { onSuccess: onClear },
        );
      }}
    >
      <fieldset className="space-y-2">
        <legend className="text-sm font-medium text-slate-700 dark:text-slate-300">Today's project</legend>
        <label className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300">
          <input type="radio" name="mode" checked={mode === "existing_project"} onChange={() => setMode("existing_project")} />
          Continue an existing project
        </label>
        <label className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300">
          <input type="radio" name="mode" checked={mode === "new_project"} onChange={() => setMode("new_project")} />
          Start a new project
        </label>
      </fieldset>
      {mode === "existing_project" ? (
        <SelectInput label="Project" value={projectId} onChange={(e) => setProjectId(e.target.value)} hint={list.length === 0 && !projects.isPending ? "You have no active projects. Start a new one instead." : undefined}>
          <option value="">Choose a project…</option>
          {list.map((p) => (
            <option key={p.id} value={p.id}>
              {p.title}
            </option>
          ))}
        </SelectInput>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          <TextInput label="New project name" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} />
          <TextInput label="GitHub repository (optional)" placeholder="https://github.com/you/project" value={repo} onChange={(e) => setRepo(e.target.value)} />
        </div>
      )}
      <TextArea label="What will you build or do today?" rows={2} value={task} onChange={(e) => setTask(e.target.value)} maxLength={500} />
      <TextInput label="Estimated minutes (optional)" inputMode="numeric" value={minutes} onChange={(e) => setMinutes(e.target.value)} className="w-40" />
      <FormError message={localError ?? plan.error?.message} />
      <Button type="submit" loading={plan.isPending}>
        Plan today's challenge
      </Button>
    </form>
  );
}

function Suggestions({ items, onPick }: { items: Suggestion[]; onPick: (s: Suggestion) => void }) {
  if (items.length === 0) return null;
  return (
    <div className="mt-5">
      <h3 className="flex items-center gap-1.5 text-sm font-semibold text-slate-900 dark:text-white">
        <Lightbulb className="h-4 w-4" aria-hidden /> Ideas from your own data
      </h3>
      <ul aria-label="Suggestions" className="mt-2 divide-y divide-slate-100 dark:divide-slate-800">
        {items.map((s, i) => (
          <li key={i} className="flex flex-wrap items-center gap-3 py-2">
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-slate-900 dark:text-white">{s.title}</p>
              <p className="text-xs text-slate-500 dark:text-slate-400">{s.detail}</p>
            </div>
            <Button variant="secondary" onClick={() => onPick(s)} aria-label={`Use idea: ${s.title}`} className="px-2.5 py-1.5">
              Use this
            </Button>
          </li>
        ))}
      </ul>
    </div>
  );
}

// ---------------------------------------------------------------- evidence

function EvidenceModal({ challenge, onClose }: { challenge: Challenge; onClose: () => void }) {
  const complete = useCompleteChallenge();
  const [summary, setSummary] = useState("");
  const [repo, setRepo] = useState(challenge.project?.repo_url ?? "");
  const [sha, setSha] = useState("");
  const [message, setMessage] = useState("");
  const [minutes, setMinutes] = useState(challenge.estimated_minutes ? String(challenge.estimated_minutes) : "");
  const [notes, setNotes] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);

  return (
    <Modal title="Record today's evidence" onClose={onClose} size="lg">
      <form
        className="space-y-4"
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          setLocalError(null);
          const mins = Number(minutes);
          if (!summary.trim()) return setLocalError("Describe what you implemented.");
          if (!repo.trim()) return setLocalError("Enter the GitHub repository the commit is in.");
          if (!sha.trim()) return setLocalError("Enter the commit hash.");
          if (!message.trim()) return setLocalError("Enter the commit message.");
          if (!Number.isInteger(mins) || mins < 1 || mins > 1440) return setLocalError("Time spent must be a whole number of minutes (1 to 1440).");
          complete.mutate(
            { id: challenge.id, summary: summary.trim(), repo_url: repo.trim(), commit_sha: sha.trim(), commit_message: message.trim(), minutes: mins, ...(notes.trim() ? { evidence_notes: notes.trim() } : {}) },
            { onSuccess: onClose },
          );
        }}
      >
        <p className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
          This is recorded as <strong>Unverified</strong>. The app can't check GitHub yet, so it relies on your honesty. Use a real commit that contains real work. Placeholder
          messages like "update" or "wip" are rejected.
        </p>
        <TextArea label="What did you implement?" rows={4} value={summary} onChange={(e) => setSummary(e.target.value)} hint="A few real sentences: what you built and what you learned (at least 30 characters)." />
        <div className="grid gap-3 sm:grid-cols-2">
          <TextInput label="GitHub repository" placeholder="https://github.com/you/project" value={repo} onChange={(e) => setRepo(e.target.value)} />
          <TextInput label="Commit hash" placeholder="a1b2c3d" value={sha} onChange={(e) => setSha(e.target.value)} hint="7 to 40 characters, from `git log`." />
        </div>
        <TextInput label="Commit message" value={message} onChange={(e) => setMessage(e.target.value)} maxLength={500} />
        <TextInput label="Time spent (minutes)" inputMode="numeric" value={minutes} onChange={(e) => setMinutes(e.target.value)} className="w-40" />
        <TextArea label="Notes (optional)" rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />
        <FormError message={localError ?? complete.error?.message} />
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={complete.isPending}>
            Complete the day
          </Button>
        </div>
      </form>
    </Modal>
  );
}

function ExcuseModal({ date, onClose }: { date: string; onClose: () => void }) {
  const excuse = useExcuseDay();
  const [reason, setReason] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);
  return (
    <Modal title={`Excuse ${date}`} onClose={onClose}>
      <form
        className="space-y-4"
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          setLocalError(null);
          if (reason.trim().length < 5) return setLocalError("Give a real reason (at least 5 characters).");
          excuse.mutate({ date, reason: reason.trim() }, { onSuccess: onClose });
        }}
      >
        <TextArea label="Why is this day being excused?" rows={3} value={reason} onChange={(e) => setReason(e.target.value)} hint="An excused day isn't counted as missed and doesn't break your streak. It also doesn't count as done." />
        <FormError message={localError ?? excuse.error?.message} />
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={excuse.isPending}>
            Excuse this day
          </Button>
        </div>
      </form>
    </Modal>
  );
}

// ---------------------------------------------------------------- today

function VerifyBox({ c }: { c: Challenge }) {
  const verify = useVerifyChallenge();
  if (c.verification_status === "verified")
    return <p className="mt-2 text-sm text-emerald-700 dark:text-emerald-400">Verified on GitHub: the commit exists, matches your message, was made that day and changes code.</p>;
  return (
    <div className="mt-3">
      <Button variant="secondary" loading={verify.isPending} onClick={() => verify.mutate(c.id)}>
        Verify on GitHub
      </Button>
      {verify.error && <ErrorNotice error={verify.error} />}
      {verify.data && !verify.data.verified && (
        <ul className="mt-2 space-y-1 text-sm" aria-label="Verification checks">
          {verify.data.checks.map((k) => (
            <li key={k.name} className={k.ok ? "text-slate-600 dark:text-slate-400" : "text-red-700 dark:text-red-400"}>
              {k.ok ? "Passed" : "Failed"}: {k.name}. {k.detail}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Evidence({ c }: { c: Challenge }) {
  return (
    <dl className="mt-3 space-y-2 text-sm">
      <div>
        <dt className="text-xs text-slate-500 dark:text-slate-400">What was implemented</dt>
        <dd className="whitespace-pre-wrap text-slate-900 dark:text-slate-100">{c.implemented_summary}</dd>
      </div>
      <div>
        <dt className="text-xs text-slate-500 dark:text-slate-400">Commit</dt>
        <dd className="text-slate-900 dark:text-slate-100">
          <code className="rounded bg-slate-100 px-1 dark:bg-slate-800">{c.commit_sha?.slice(0, 10)}</code> {c.commit_message}
          {c.repo_url && (
            <a href={`${c.repo_url}/commit/${c.commit_sha}`} target="_blank" rel="noreferrer noopener" className="ml-2 inline-flex items-center gap-1 text-brand-600 hover:underline dark:text-brand-400">
              View on GitHub <ExternalLink className="h-3.5 w-3.5" aria-hidden />
            </a>
          )}
        </dd>
      </div>
      <div className="flex flex-wrap gap-x-6 gap-y-1 text-slate-700 dark:text-slate-300">
        <span>Time: {formatMinutes(c.actual_minutes ?? 0)}</span>
        {c.milestone && <span>Milestone: {c.milestone.title}</span>}
      </div>
      {c.evidence_notes && <p className="text-slate-600 dark:text-slate-400">{c.evidence_notes}</p>}
      <VerifyBox c={c} />
    </dl>
  );
}

function TodayCard({ challenge, suggestions, date }: { challenge: Challenge | null; suggestions: Suggestion[]; date: string }) {
  const start = useStartChallenge();
  const remove = useDeleteChallenge();
  const [evidence, setEvidence] = useState(false);
  const [excusing, setExcusing] = useState(false);
  const [picked, setPicked] = useState<Suggestion | null>(null);

  if (!challenge) {
    return (
      <Card aria-label="Today's challenge">
        <h2 className="text-sm font-semibold text-slate-900 dark:text-white">Today's challenge</h2>
        <p className="mb-4 mt-1 text-sm text-slate-600 dark:text-slate-400">Pick one AI project to work on today. You'll need to show a real commit to finish the day.</p>
        <PlanForm key={picked ? `${picked.source}-${picked.title}` : "blank"} suggestion={picked} onClear={() => setPicked(null)} />
        <Suggestions items={suggestions} onPick={setPicked} />
        <div className="mt-4 border-t border-slate-100 pt-3 dark:border-slate-800">
          <Button variant="ghost" icon={EyeOff} onClick={() => setExcusing(true)}>
            Excuse today
          </Button>
        </div>
        {excusing && <ExcuseModal date={date} onClose={() => setExcusing(false)} />}
      </Card>
    );
  }

  const open = challenge.status === "planned" || challenge.status === "in_progress";
  return (
    <Card aria-label="Today's challenge">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-slate-900 dark:text-white">Today's challenge</h2>
        <div className="flex items-center gap-2">
          <Badge tone={challenge.status === "completed" ? "brand" : "neutral"}>{STATUS_LABEL[challenge.status]}</Badge>
          {challenge.status === "completed" && <Badge>{challenge.verification_status === "verified" ? "Verified" : "Unverified"}</Badge>}
        </div>
      </div>
      <p className="mt-2 text-base font-medium text-slate-900 dark:text-white">{challenge.planned_task}</p>
      <p className="text-sm text-slate-600 dark:text-slate-400">
        {challenge.project ? (
          <>
            {challenge.mode === "new_project" ? "New project: " : "Project: "}
            <Link to={`/projects/${challenge.project.id}`} className="text-brand-600 hover:underline dark:text-brand-400">
              {challenge.project.title}
            </Link>
          </>
        ) : (
          "No project"
        )}
        {challenge.estimated_minutes ? ` · about ${formatMinutes(challenge.estimated_minutes)}` : ""}
      </p>
      {challenge.status === "completed" && <Evidence c={challenge} />}
      {challenge.status === "excused" && <p className="mt-2 text-sm italic text-slate-600 dark:text-slate-400">Excused: {challenge.excuse_reason}</p>}
      {open && (
        <div className="mt-4 flex flex-wrap gap-2">
          {challenge.status === "planned" && (
            <Button variant="secondary" icon={Play} loading={start.isPending} onClick={() => start.mutate(challenge.id)}>
              Start
            </Button>
          )}
          <Button icon={CheckCircle2} onClick={() => setEvidence(true)}>
            Record evidence and complete
          </Button>
          <Button variant="ghost" icon={EyeOff} onClick={() => setExcusing(true)}>
            Excuse today
          </Button>
        </div>
      )}
      {(challenge.status === "excused" || open) && (
        <div className="mt-2">
          <Button variant="ghost" icon={Trash2} loading={remove.isPending} onClick={() => remove.mutate(challenge.id)} aria-label={challenge.status === "excused" ? "Remove excuse" : "Remove plan"}>
            {challenge.status === "excused" ? "Remove excuse" : "Remove plan"}
          </Button>
        </div>
      )}
      <FormError message={start.error?.message ?? remove.error?.message} />
      {evidence && <EvidenceModal challenge={challenge} onClose={() => setEvidence(false)} />}
      {excusing && <ExcuseModal date={date} onClose={() => setExcusing(false)} />}
    </Card>
  );
}

// ---------------------------------------------------------------- calendar + history

function CalendarCard({ days, today }: { days: CalendarDay[]; today: string }) {
  const [excusing, setExcusing] = useState<string | null>(null);
  return (
    <Card aria-label="Last 30 days">
      <h2 className="text-sm font-semibold text-slate-900 dark:text-white">Last 30 days</h2>
      <ul className="mt-3 grid grid-cols-5 gap-1.5 sm:grid-cols-10">
        {days.map((d) => {
          const label = `${d.date}: ${STATUS_LABEL[d.status]}${d.project_title ? ` (${d.project_title})` : ""}`;
          return (
            <li key={d.date}>
              {d.status === "missed" ? (
                <button type="button" onClick={() => setExcusing(d.date)} aria-label={`${label}. Excuse this day`} title="Missed. Click to excuse it with a reason" className={cx("w-full rounded px-1 py-1.5 text-center text-xs", TONE.missed, d.date === today && "ring-2 ring-brand-500")}>
                  {d.date.slice(5)}
                </button>
              ) : (
                <div aria-label={label} title={label} className={cx("rounded px-1 py-1.5 text-center text-xs", TONE[d.status], d.date === today && "ring-2 ring-brand-500")}>
                  {d.date.slice(5)}
                </div>
              )}
            </li>
          );
        })}
      </ul>
      <ul aria-label="Legend" className="mt-3 flex flex-wrap gap-2 text-xs">
        {(["completed", "excused", "missed", "in_progress", "planned"] as const).map((s) => (
          <li key={s} className={cx("rounded px-2 py-0.5", TONE[s])}>
            {STATUS_LABEL[s]}
          </li>
        ))}
      </ul>
      {excusing && <ExcuseModal date={excusing} onClose={() => setExcusing(null)} />}
    </Card>
  );
}

function HistoryCard({ items, today }: { items: Challenge[]; today: string }) {
  const done = items.filter((c) => c.status === "completed");
  return (
    <Card aria-label="Evidence history">
      <h2 className="text-sm font-semibold text-slate-900 dark:text-white">Evidence history</h2>
      {done.length === 0 ? (
        <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">No completed days yet.</p>
      ) : (
        <ul className="mt-1 divide-y divide-slate-100 dark:divide-slate-800">
          {done.map((c) => (
            <li key={c.id} className="py-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-medium text-slate-900 dark:text-white">{formatDay(c.date, today)}</span>
                <span className="text-xs text-slate-500 dark:text-slate-400">{c.date}</span>
                {c.project && <Badge>{c.project.title}</Badge>}
                <Badge>{c.verification_status === "verified" ? "Verified" : "Unverified"}</Badge>
              </div>
              <p className="mt-1 text-sm text-slate-700 dark:text-slate-300">{c.implemented_summary}</p>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                {c.commit_sha?.slice(0, 10)} · {c.commit_message} · {formatMinutes(c.actual_minutes ?? 0)}
              </p>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

export function ChallengePage() {
  const today = useToday();
  const calendar = useCalendar();
  const history = useHistory();

  return (
    <>
      <PageHeader title="Daily challenge" description="One AI project task every day, backed by a real commit, or an honest excuse. Nothing is completed for you." />
      {today.isPending ? (
        <Spinner label="Loading today's challenge…" />
      ) : today.isError ? (
        <ErrorNotice error={today.error} onRetry={() => today.refetch()} />
      ) : (
        <div className="space-y-4">
          <p className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400">
            Evidence is entered by you and is shown as <strong>Unverified</strong>. Checking commits against GitHub arrives in a later phase.
          </p>
          <StatsCard stats={today.data.stats} />
          <TodayCard challenge={today.data.challenge} suggestions={today.data.suggestions} date={today.data.date} />
          {calendar.isError ? <ErrorNotice error={calendar.error} onRetry={() => calendar.refetch()} /> : calendar.data ? <CalendarCard days={calendar.data.days} today={today.data.date} /> : null}
          {history.isError ? (
            <ErrorNotice error={history.error} onRetry={() => history.refetch()} />
          ) : history.data ? (
            history.data.length === 0 && !today.data.challenge ? (
              <EmptyState icon={CheckCircle2} title="No challenges yet">
                Plan today's challenge above. Each completed day appears here with its evidence.
              </EmptyState>
            ) : (
              <HistoryCard items={history.data} today={today.data.date} />
            )
          ) : null}
        </div>
      )}
    </>
  );
}
