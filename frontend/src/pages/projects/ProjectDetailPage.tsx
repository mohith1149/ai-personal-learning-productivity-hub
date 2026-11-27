import { ArrowLeft, Check, ExternalLink, Pencil, RotateCcw, Trash2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useAuthStatus } from "../../api/auth";
import { ApiError } from "../../api/client";
import {
  PRIORITY_LABEL,
  useAddMilestone,
  useAddProjectTask,
  useDeleteMilestone,
  useDeleteProject,
  useDeleteSession,
  useLogSession,
  useProject,
  useSetMilestoneStatus,
  useSetTaskStatus,
  useUpdateProject,
  type Milestone,
  type ProjectDetail,
} from "../../api/projects";
import { FormError, SelectInput, TextArea, TextInput } from "../../components/forms";
import { ConfirmDialog, Modal } from "../../components/Modal";
import { GoalPace } from "../../components/Goals";
import { StartTimerButton } from "../../components/Timer";
import { Badge, Button, Card, EmptyState, ErrorNotice, ProgressBar, Spinner, cx } from "../../components/ui";
import { formatDay, todayIn } from "../../lib/dates";
import { ProjectForm } from "./ProjectForm";
import { ProjectStatusBadge, formatHours } from "./ProjectsPage";

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <dt className="text-xs text-slate-500 dark:text-slate-400">{label}</dt>
      <dd className="text-lg font-semibold tabular-nums text-slate-900 dark:text-white">{value}</dd>
    </div>
  );
}

function DoneModal({ milestone, onClose }: { milestone: Milestone; onClose: () => void }) {
  const set = useSetMilestoneStatus();
  const [evidence, setEvidence] = useState(milestone.evidence ?? "");
  return (
    <Modal title={`Mark done: ${milestone.title}`} onClose={onClose}>
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          set.mutate({ id: milestone.id, status: "done", evidence: evidence.trim() || null }, { onSuccess: onClose });
        }}
      >
        <TextArea label="Evidence (optional)" rows={3} value={evidence} onChange={(e) => setEvidence(e.target.value)} hint="A commit, a link, or a note on how you know it's done." />
        <FormError message={set.error?.message} />
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={set.isPending}>
            Mark done
          </Button>
        </div>
      </form>
    </Modal>
  );
}

function MilestonesCard({ project, today }: { project: ProjectDetail; today: string }) {
  const add = useAddMilestone();
  const setStatus = useSetMilestoneStatus();
  const del = useDeleteMilestone();
  const [title, setTitle] = useState("");
  const [due, setDue] = useState("");
  const [done, setDone] = useState<Milestone | null>(null);
  const [confirm, setConfirm] = useState<Milestone | null>(null);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;
    add.mutate({ projectId: project.id, body: { title: title.trim(), due_date: due || null } }, { onSuccess: () => { setTitle(""); setDue(""); } });
  };

  return (
    <Card aria-label="Milestones">
      <h2 className="text-sm font-semibold text-slate-900 dark:text-white">Milestones</h2>
      {project.milestones.length === 0 ? (
        <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">No milestones yet. Break the project into steps you can check off.</p>
      ) : (
        <ul aria-label="Milestone list" className="mt-2 divide-y divide-slate-100 dark:divide-slate-800">
          {project.milestones.map((m) => (
            <li key={m.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2">
              <div className="min-w-0 flex-1">
                <p className={cx("text-sm font-medium", m.status === "done" ? "text-slate-500 line-through" : "text-slate-900 dark:text-white")}>{m.title}</p>
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  {m.due_date && <>Due {formatDay(m.due_date, today)}</>}
                  {m.overdue && <> · overdue</>}
                  {m.status === "done" && m.evidence && <> · {m.evidence}</>}
                </p>
              </div>
              {m.status === "done" ? (
                <Button variant="secondary" icon={RotateCcw} loading={setStatus.isPending && setStatus.variables?.id === m.id} onClick={() => setStatus.mutate({ id: m.id, status: "pending" })} aria-label={`Reopen milestone ${m.title}`}>
                  Reopen
                </Button>
              ) : (
                <Button variant="secondary" icon={Check} onClick={() => setDone(m)} aria-label={`Mark milestone ${m.title} done`}>
                  Mark done
                </Button>
              )}
              <button onClick={() => setConfirm(m)} aria-label={`Delete milestone ${m.title}`} className="rounded-lg p-1.5 text-slate-400 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950/40">
                <Trash2 className="h-4 w-4" aria-hidden />
              </button>
            </li>
          ))}
        </ul>
      )}
      <form onSubmit={submit} className="mt-3 flex flex-wrap items-end gap-2" noValidate>
        <div className="min-w-48 flex-1">
          <TextInput label="New milestone" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} />
        </div>
        <TextInput label="Due (optional)" type="date" value={due} onChange={(e) => setDue(e.target.value)} />
        <Button type="submit" loading={add.isPending} disabled={!title.trim()}>
          Add milestone
        </Button>
      </form>
      <FormError message={add.error?.message ?? setStatus.error?.message} />
      {done && <DoneModal milestone={done} onClose={() => setDone(null)} />}
      {confirm && (
        <ConfirmDialog
          title="Delete milestone?"
          message={<><strong>{confirm.title}</strong> will be deleted. Development sessions that mentioned it are kept.</>}
          busy={del.isPending}
          error={del.error?.message}
          onCancel={() => { setConfirm(null); del.reset(); }}
          onConfirm={() => del.mutate(confirm.id, { onSuccess: () => setConfirm(null) })}
        />
      )}
    </Card>
  );
}

function TasksCard({ project, today }: { project: ProjectDetail; today: string }) {
  const add = useAddProjectTask();
  const setStatus = useSetTaskStatus();
  const [title, setTitle] = useState("");
  return (
    <Card aria-label="Project tasks">
      <h2 className="text-sm font-semibold text-slate-900 dark:text-white">Tasks</h2>
      <p className="text-xs text-slate-500 dark:text-slate-400">These are normal tasks, so they also show on the Tasks page.</p>
      {project.tasks.length === 0 ? (
        <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">No tasks yet.</p>
      ) : (
        <ul aria-label="Task list" className="mt-2 divide-y divide-slate-100 dark:divide-slate-800">
          {project.tasks.map((t) => {
            const done = t.status === "completed";
            return (
              <li key={t.id} className="flex items-center gap-3 py-2">
                <button
                  role="checkbox"
                  aria-checked={done}
                  disabled={t.status === "cancelled" || setStatus.isPending}
                  aria-label={done ? `Reopen task ${t.title}` : `Complete task ${t.title}`}
                  onClick={() => setStatus.mutate({ id: t.id, status: done ? "pending" : "completed" })}
                  className={cx("flex h-5 w-5 shrink-0 items-center justify-center rounded border disabled:opacity-40", done ? "border-emerald-500 bg-emerald-500 text-white" : "border-slate-300 hover:border-brand-500 dark:border-slate-600")}
                >
                  {done && <Check className="h-3.5 w-3.5" aria-hidden />}
                </button>
                <div className="min-w-0 flex-1">
                  <p className={cx("text-sm font-medium", done || t.status === "cancelled" ? "text-slate-500 line-through" : "text-slate-900 dark:text-white")}>{t.title}</p>
                  <p className="text-xs text-slate-500 dark:text-slate-400">
                    {PRIORITY_LABEL[t.priority]}
                    {t.due_date && <> · due {formatDay(t.due_date, today)}</>}
                    {t.estimated_minutes && <> · ~{formatHours(t.estimated_minutes)}</>}
                    {t.status === "cancelled" && <> · cancelled (not counted)</>}
                  </p>
                </div>
              </li>
            );
          })}
        </ul>
      )}
      <form
        className="mt-3 flex flex-wrap items-end gap-2"
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          if (title.trim()) add.mutate({ projectId: project.id, body: { title: title.trim() } }, { onSuccess: () => setTitle("") });
        }}
      >
        <div className="min-w-48 flex-1">
          <TextInput label="New task" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} />
        </div>
        <Button type="submit" loading={add.isPending} disabled={!title.trim()}>
          Add task
        </Button>
      </form>
      <FormError message={add.error?.message ?? setStatus.error?.message} />
    </Card>
  );
}

function SessionsCard({ project, today }: { project: ProjectDetail; today: string }) {
  const log = useLogSession();
  const del = useDeleteSession();
  const [minutes, setMinutes] = useState("60");
  const [date, setDate] = useState(today);
  const [summary, setSummary] = useState("");
  const [milestoneId, setMilestoneId] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setLocalError(null);
    const n = Number(minutes);
    if (!Number.isInteger(n) || n < 1 || n > 1440) return setLocalError("Minutes must be a whole number from 1 to 1440.");
    if (summary.trim().length < 3) return setLocalError("Say what you worked on (at least a few words).");
    if (date > today) return setLocalError("You can't log time in the future.");
    log.mutate(
      { projectId: project.id, body: { minutes: n, summary: summary.trim(), date, milestone_id: milestoneId ? Number(milestoneId) : null } },
      { onSuccess: () => { setSummary(""); setMilestoneId(""); } },
    );
  };

  return (
    <Card aria-label="Development sessions">
      <h2 className="text-sm font-semibold text-slate-900 dark:text-white">Development sessions</h2>
      <form onSubmit={submit} className="mt-2 space-y-3" noValidate>
        <div className="grid gap-3 sm:grid-cols-3">
          <TextInput label="Minutes" type="number" min={1} max={1440} value={minutes} onChange={(e) => setMinutes(e.target.value)} />
          <TextInput label="Day" type="date" max={today} value={date} onChange={(e) => setDate(e.target.value)} />
          <SelectInput label="Milestone (optional)" value={milestoneId} onChange={(e) => setMilestoneId(e.target.value)}>
            <option value="">None</option>
            {project.milestones.map((m) => (
              <option key={m.id} value={m.id}>
                {m.title}
              </option>
            ))}
          </SelectInput>
        </div>
        <TextArea label="What did you work on?" rows={2} value={summary} onChange={(e) => setSummary(e.target.value)} />
        <FormError message={localError ?? log.error?.message} />
        <div className="flex justify-end">
          <Button type="submit" loading={log.isPending}>
            Log session
          </Button>
        </div>
      </form>
      {project.sessions.length === 0 ? (
        <p className="mt-3 text-sm text-slate-500 dark:text-slate-400">No development time logged yet.</p>
      ) : (
        <ul aria-label="Session history" className="mt-3 divide-y divide-slate-100 dark:divide-slate-800">
          {project.sessions.map((s) => (
            <li key={s.id} className="flex items-start justify-between gap-2 py-2 text-sm">
              <span className="text-slate-700 dark:text-slate-300">
                <strong>{formatDay(s.date, today)}</strong> · {formatHours(s.minutes)} · {s.summary}
              </span>
              <button onClick={() => del.mutate(s.id)} aria-label={`Delete session of ${s.date}: ${s.summary}`} className="rounded p-1 text-slate-400 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950/40">
                <Trash2 className="h-4 w-4" aria-hidden />
              </button>
            </li>
          ))}
        </ul>
      )}
      <FormError message={del.error?.message} />
    </Card>
  );
}

function NotesCard({ project }: { project: ProjectDetail }) {
  const update = useUpdateProject();
  const [notes, setNotes] = useState(project.notes ?? "");
  return (
    <Card aria-label="Project notes">
      <h2 className="text-sm font-semibold text-slate-900 dark:text-white">Notes</h2>
      <div className="mt-2">
        <TextArea label="Notes" rows={4} value={notes} onChange={(e) => setNotes(e.target.value)} />
      </div>
      <FormError message={update.error?.message} />
      <div className="mt-2 flex justify-end">
        <Button variant="secondary" loading={update.isPending} disabled={notes === (project.notes ?? "")} onClick={() => update.mutate({ id: project.id, body: { notes: notes.trim() || null } })}>
          Save notes
        </Button>
      </div>
    </Card>
  );
}

export function ProjectDetailPage() {
  const { projectId } = useParams();
  const id = Number(projectId);
  const navigate = useNavigate();
  const tz = useAuthStatus().data?.user?.timezone ?? "UTC";
  const today = todayIn(tz);
  const project = useProject(id);
  const update = useUpdateProject();
  const del = useDeleteProject();
  const [editing, setEditing] = useState(false);
  const [confirm, setConfirm] = useState(false);

  const back = (
    <Link to="/projects" className="mb-3 inline-flex items-center gap-1 text-sm text-brand-600 hover:underline dark:text-brand-400">
      <ArrowLeft className="h-4 w-4" aria-hidden /> Back to projects
    </Link>
  );

  if (project.isPending) return <Spinner label="Loading project…" />;
  if (project.isError) {
    const notFound = project.error instanceof ApiError && project.error.status === 404;
    return (
      <>
        {back}
        {notFound ? <EmptyState icon={ArrowLeft} title="Project not found">It may have been deleted.</EmptyState> : <ErrorNotice error={project.error} onRetry={() => project.refetch()} />}
      </>
    );
  }
  const p = project.data;
  const pr = p.progress;

  return (
    <>
      {back}
      <Card aria-label="Project overview">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-xl font-semibold text-slate-900 dark:text-white">{p.title}</h1>
              <ProjectStatusBadge status={p.status} />
              {p.origin === "existing" && <Badge>Existing</Badge>}
              {p.overdue && <Badge>Past target date</Badge>}
            </div>
            {p.objective && <p className="mt-1 text-sm text-slate-700 dark:text-slate-300">Objective: {p.objective}</p>}
            {p.description && <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">{p.description}</p>}
            <p className="mt-1 flex flex-wrap gap-x-3 text-xs text-slate-500 dark:text-slate-400">
              <span>{PRIORITY_LABEL[p.priority]} priority</span>
              {p.start_date && <span>Started {formatDay(p.start_date, today)}</span>}
              {p.target_date && <span>Target {formatDay(p.target_date, today)}</span>}
              {p.repo_url && (
                <a href={p.repo_url} target="_blank" rel="noreferrer noopener" aria-label="GitHub repository" className="inline-flex items-center gap-1 text-brand-600 hover:underline dark:text-brand-400">
                  {p.repo_url.replace("https://github.com/", "")} <ExternalLink className="h-3 w-3" aria-hidden />
                </a>
              )}
            </p>
            {p.target_date && p.status === "active" && <GoalPace kind="project" id={p.id} />}
            {p.tech_stack.length > 0 && (
              <ul aria-label="Technologies" className="mt-2 flex flex-wrap gap-1">
                {p.tech_stack.map((t) => (
                  <li key={t}>
                    <Badge tone="brand">{t}</Badge>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-1">
            {p.status === "active" && <StartTimerButton kind="project" id={p.id} label={p.title} className="border border-slate-300 dark:border-slate-700" />}
            {p.status !== "completed" ? (
              <Button icon={Check} loading={update.isPending} onClick={() => update.mutate({ id: p.id, body: { status: "completed" } })}>
                Mark project completed
              </Button>
            ) : (
              <Button variant="secondary" icon={RotateCcw} loading={update.isPending} onClick={() => update.mutate({ id: p.id, body: { status: "active" } })}>
                Reopen project
              </Button>
            )}
            <Button variant="secondary" icon={Pencil} onClick={() => setEditing(true)}>
              Edit
            </Button>
            <Button variant="ghost" icon={Trash2} onClick={() => setConfirm(true)} aria-label={`Delete project ${p.title}`}>
              Delete
            </Button>
          </div>
        </div>
        <FormError message={update.error?.message} />
        <div className="mt-4">
          <ProgressBar percent={pr.percent} label={`${p.title} progress`} />
          <p className="mt-1.5 text-xs text-slate-500 dark:text-slate-400">
            {pr.percent}% · {pr.milestones_done + pr.tasks_done} of {pr.milestones_total + pr.tasks_total} milestones and tasks done
          </p>
        </div>
        <dl className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Stat label="Milestones" value={`${pr.milestones_done}/${pr.milestones_total}`} />
          <Stat label="Tasks" value={`${pr.tasks_done}/${pr.tasks_total}`} />
          <Stat label="Time spent" value={formatHours(p.minutes_spent)} />
          <Stat label="Days worked" value={p.days_active} />
        </dl>
      </Card>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <MilestonesCard project={p} today={today} />
        <TasksCard project={p} today={today} />
      </div>
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <SessionsCard project={p} today={today} />
        <NotesCard key={p.notes ?? ""} project={p} />
      </div>

      {editing && <ProjectForm project={p} onClose={() => setEditing(false)} />}
      {confirm && (
        <ConfirmDialog
          title="Delete project?"
          message={
            <>
              <strong>{p.title}</strong>, its {pr.milestones_total} milestone{pr.milestones_total === 1 ? "" : "s"} and {p.session_count} development session{p.session_count === 1 ? "" : "s"} will be permanently deleted. Its tasks stay in your task list.
            </>
          }
          busy={del.isPending}
          error={del.error?.message}
          onCancel={() => { setConfirm(false); del.reset(); }}
          onConfirm={() => del.mutate(p.id, { onSuccess: () => navigate("/projects") })}
        />
      )}
    </>
  );
}
