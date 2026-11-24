import { ExternalLink, FolderGit2, Plus } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuthStatus } from "../../api/auth";
import { PRIORITY_LABEL, PROJECT_STATUS_LABEL, useProjects, type ProjectStatus, type ProjectSummary } from "../../api/projects";
import { Badge, Button, EmptyState, ErrorNotice, PageHeader, ProgressBar, Spinner, cx } from "../../components/ui";
import { formatDay, todayIn } from "../../lib/dates";
import { ProjectForm } from "./ProjectForm";

export const formatHours = (minutes: number) => (minutes >= 60 ? `${Math.floor(minutes / 60)}h ${minutes % 60}m` : `${minutes}m`);

export function ProjectStatusBadge({ status }: { status: ProjectStatus }) {
  const cls =
    status === "completed" ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300"
    : status === "active" ? "bg-brand-100 text-brand-700 dark:bg-brand-500/20 dark:text-brand-400"
    : "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400";
  return <span className={cx("inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium", cls)}>{PROJECT_STATUS_LABEL[status]}</span>;
}

function ProjectCard({ project, today }: { project: ProjectSummary; today: string }) {
  const p = project.progress;
  return (
    <li className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <h3 className="min-w-0 text-base font-semibold text-slate-900 dark:text-white">
          <Link to={`/projects/${project.id}`} className="hover:underline">
            {project.title}
          </Link>
        </h3>
        <div className="flex flex-wrap items-center gap-1.5">
          <ProjectStatusBadge status={project.status} />
          {project.origin === "existing" && <Badge>Existing</Badge>}
          {project.overdue && <Badge>Past target date</Badge>}
        </div>
      </div>
      {project.description && <p className="mt-1 line-clamp-2 text-sm text-slate-600 dark:text-slate-400">{project.description}</p>}
      {project.tech_stack.length > 0 && (
        <ul aria-label={`${project.title} technologies`} className="mt-2 flex flex-wrap gap-1">
          {project.tech_stack.map((t) => (
            <li key={t}>
              <Badge tone="brand">{t}</Badge>
            </li>
          ))}
        </ul>
      )}
      <div className="mt-3">
        <ProgressBar percent={p.percent} label={`${project.title} progress`} />
        <div className="mt-1.5 flex flex-wrap justify-between gap-2 text-xs text-slate-500 dark:text-slate-400">
          <span>
            {p.milestones_done}/{p.milestones_total} milestones · {p.tasks_done}/{p.tasks_total} tasks
          </span>
          <span className="tabular-nums">{p.percent}%</span>
        </div>
      </div>
      <p className="mt-2 flex flex-wrap items-center gap-x-3 text-xs text-slate-500 dark:text-slate-400">
        <span>{PRIORITY_LABEL[project.priority]} priority</span>
        <span>
          {formatHours(project.minutes_spent)} over {project.days_active} day{project.days_active === 1 ? "" : "s"}
        </span>
        {project.target_date && <span>Target {formatDay(project.target_date, today)}</span>}
        {project.repo_url && (
          <a href={project.repo_url} target="_blank" rel="noreferrer noopener" aria-label={`GitHub repository of ${project.title}`} className="inline-flex items-center gap-1 text-brand-600 hover:underline dark:text-brand-400">
            GitHub <ExternalLink className="h-3 w-3" aria-hidden />
          </a>
        )}
      </p>
    </li>
  );
}

const FILTERS: { key: ProjectStatus | ""; label: string }[] = [
  { key: "", label: "All" },
  { key: "active", label: "Active" },
  { key: "paused", label: "Paused" },
  { key: "completed", label: "Completed" },
  { key: "archived", label: "Archived" },
];

export function ProjectsPage() {
  const [filter, setFilter] = useState<ProjectStatus | "">("");
  const projects = useProjects(filter);
  const [creating, setCreating] = useState(false);
  const navigate = useNavigate();
  const tz = useAuthStatus().data?.user?.timezone ?? "UTC";
  const today = todayIn(tz);

  return (
    <>
      <PageHeader
        title="Projects"
        description="Track the AI projects you build, new or existing: milestones, tasks and the time you actually spend. Progress is worked out from what's done."
        actions={
          <Button icon={Plus} onClick={() => setCreating(true)}>
            New project
          </Button>
        }
      />
      <div role="tablist" aria-label="Project status" className="mb-4 flex flex-wrap gap-1">
        {FILTERS.map((f) => (
          <button
            key={f.label}
            role="tab"
            aria-selected={filter === f.key}
            onClick={() => setFilter(f.key)}
            className={cx("rounded-lg px-3 py-1.5 text-sm font-medium transition", filter === f.key ? "bg-brand-600 text-white" : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800")}
          >
            {f.label}
          </button>
        ))}
      </div>
      {projects.isPending ? (
        <Spinner label="Loading projects…" />
      ) : projects.isError ? (
        <ErrorNotice error={projects.error} onRetry={() => projects.refetch()} />
      ) : projects.data.length === 0 ? (
        <EmptyState icon={FolderGit2} title={filter ? "No projects with this status" : "No projects yet"} action={filter ? undefined : <Button icon={Plus} onClick={() => setCreating(true)}>New project</Button>}>
          {filter ? "Try another filter." : "Add a project you're starting, or one you already have. Nothing is added for you."}
        </EmptyState>
      ) : (
        <ul aria-label="Projects" className="grid gap-4 lg:grid-cols-2">
          {projects.data.map((p) => (
            <ProjectCard key={p.id} project={p} today={today} />
          ))}
        </ul>
      )}
      {creating && <ProjectForm project={null} onClose={() => setCreating(false)} onSaved={(p) => navigate(`/projects/${p.id}`)} />}
    </>
  );
}
