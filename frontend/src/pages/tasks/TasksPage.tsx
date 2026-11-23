import { ListChecks, Plus, Search, Tags } from "lucide-react";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useAuthStatus } from "../../api/auth";
import {
  useCategories,
  useDeleteTask,
  useTaskCounts,
  useTasks,
  useUpdateTask,
  type Task,
  type TaskView,
} from "../../api/tasks";
import { controlClass } from "../../components/forms";
import { ConfirmDialog } from "../../components/Modal";
import { Button, EmptyState, ErrorNotice, PageHeader, Spinner, cx } from "../../components/ui";
import { todayIn } from "../../lib/dates";
import { CategoryManager } from "./CategoryManager";
import { PRIORITIES } from "./constants";
import { RecurringPanel } from "./RecurringPanel";
import { TaskForm } from "./TaskForm";
import { TaskRow } from "./TaskRow";

const TABS: { key: TaskView | "recurring"; label: string }[] = [
  { key: "open", label: "Open" },
  { key: "today", label: "Today" },
  { key: "overdue", label: "Overdue" },
  { key: "upcoming", label: "Upcoming" },
  { key: "completed", label: "Completed" },
  { key: "all", label: "All" },
  { key: "recurring", label: "Recurring" },
];

const EMPTY: Record<TaskView, { title: string; body: string }> = {
  open: { title: "No open tasks", body: "You're all caught up. Add a task to get started." },
  today: { title: "Nothing due or scheduled today", body: "Tasks due or scheduled for today appear here." },
  overdue: { title: "Nothing overdue", body: "Every task with a due date is on track." },
  upcoming: { title: "Nothing upcoming", body: "Tasks with a future due or scheduled date appear here." },
  completed: { title: "No completed tasks yet", body: "Tick a task off and it will show up here." },
  all: { title: "No tasks yet", body: "Create your first task to begin." },
};

function useDebounced<T>(value: T, ms = 250): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setV(value), ms);
    return () => clearTimeout(id);
  }, [value, ms]);
  return v;
}

export function TasksPage() {
  const user = useAuthStatus().data?.user;
  const today = todayIn(user?.timezone ?? "UTC");
  const [params, setParams] = useSearchParams();
  const rawTab = params.get("view");
  const tab = (TABS.some((t) => t.key === rawTab) ? rawTab : "open") as TaskView | "recurring";
  const view: TaskView = tab === "recurring" ? "open" : tab;

  const [search, setSearch] = useState("");
  const q = useDebounced(search.trim());
  const [categoryId, setCategoryId] = useState("");
  const [priority, setPriority] = useState("");

  const [editing, setEditing] = useState<Task | "new" | null>(null);
  const [deleting, setDeleting] = useState<Task | null>(null);
  const [managingCategories, setManagingCategories] = useState(false);

  const categories = useCategories();
  const counts = useTaskCounts();
  const tasks = useTasks({
    view,
    q: q || undefined,
    category_id: categoryId ? Number(categoryId) : undefined,
    priority: priority ? Number(priority) : undefined,
  });
  const update = useUpdateTask();
  const del = useDeleteTask();

  const filtersActive = Boolean(q || categoryId || priority);
  const selectTab = (key: string) => setParams(key === "open" ? {} : { view: key }, { replace: true });
  const toggle = (t: Task) => update.mutate({ id: t.id, body: { status: t.status === "completed" ? "pending" : "completed" } });

  return (
    <>
      <PageHeader
        title="Tasks"
        description="Everything you need to do, with due dates, priorities and recurring routines."
        actions={
          <>
            <Button variant="secondary" icon={Tags} onClick={() => setManagingCategories(true)}>
              Categories
            </Button>
            {tab !== "recurring" && (
              <Button icon={Plus} onClick={() => setEditing("new")}>
                New task
              </Button>
            )}
          </>
        }
      />

      <div role="tablist" aria-label="Task views" className="-mx-1 mb-4 flex gap-1 overflow-x-auto px-1 pb-1">
        {TABS.map(({ key, label }) => {
          const count = key === "recurring" ? undefined : counts.data?.[key];
          const active = tab === key;
          return (
            <button
              key={key}
              role="tab"
              aria-selected={active}
              onClick={() => selectTab(key)}
              className={cx(
                "flex shrink-0 items-center gap-2 rounded-lg px-3 py-1.5 text-sm font-medium transition",
                active
                  ? "bg-brand-600 text-white"
                  : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800",
              )}
            >
              {label}
              {count !== undefined && (
                <span
                  aria-label={`${count} tasks`}
                  className={cx(
                    "rounded-full px-1.5 text-xs tabular-nums",
                    active
                      ? "bg-white/25"
                      : key === "overdue" && count > 0
                        ? "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300"
                        : "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400",
                  )}
                >
                  {count}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {tab === "recurring" ? (
        <RecurringPanel />
      ) : (
        <>
          <div className="mb-4 flex flex-wrap gap-2">
            <div className="relative min-w-[12rem] flex-1">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" aria-hidden />
              <input
                type="search"
                aria-label="Search tasks"
                placeholder="Search tasks"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className={cx(controlClass, "w-full pl-9")}
              />
            </div>
            <select
              aria-label="Filter by category"
              value={categoryId}
              onChange={(e) => setCategoryId(e.target.value)}
              className={controlClass}
            >
              <option value="">All categories</option>
              {categories.data?.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
            <select
              aria-label="Filter by priority"
              value={priority}
              onChange={(e) => setPriority(e.target.value)}
              className={controlClass}
            >
              <option value="">All priorities</option>
              {PRIORITIES.map((p) => (
                <option key={p.value} value={p.value}>
                  {p.label}
                </option>
              ))}
            </select>
          </div>

          {update.error && (
            <div className="mb-3">
              <ErrorNotice error={update.error} />
            </div>
          )}

          {tasks.isPending ? (
            <Spinner label="Loading tasks…" />
          ) : tasks.isError ? (
            <ErrorNotice error={tasks.error} onRetry={() => tasks.refetch()} />
          ) : tasks.data.items.length === 0 ? (
            filtersActive ? (
              <EmptyState icon={Search} title="No tasks match these filters">
                Try a different search or clear the filters.
              </EmptyState>
            ) : (
              <EmptyState
                icon={ListChecks}
                title={EMPTY[view].title}
                action={
                  view !== "completed" && view !== "overdue" ? (
                    <Button icon={Plus} onClick={() => setEditing("new")}>
                      New task
                    </Button>
                  ) : undefined
                }
              >
                {EMPTY[view].body}
              </EmptyState>
            )
          ) : (
            <ul className="space-y-2" aria-label="Tasks">
              {tasks.data.items.map((t) => (
                <TaskRow
                  key={t.id}
                  task={t}
                  today={today}
                  busy={update.isPending && update.variables?.id === t.id}
                  onToggle={toggle}
                  onEdit={setEditing}
                  onDelete={setDeleting}
                />
              ))}
            </ul>
          )}
        </>
      )}

      {editing && (
        <TaskForm
          task={editing === "new" ? null : editing}
          defaults={view === "today" ? { due_date: today } : undefined}
          onClose={() => setEditing(null)}
        />
      )}
      {managingCategories && <CategoryManager onClose={() => setManagingCategories(false)} />}
      {deleting && (
        <ConfirmDialog
          title="Delete task?"
          message={
            <>
              <strong>{deleting.title}</strong> will be permanently deleted. This can't be undone.
            </>
          }
          busy={del.isPending}
          error={del.error?.message}
          onCancel={() => {
            del.reset();
            setDeleting(null);
          }}
          onConfirm={() => del.mutate(deleting.id, { onSuccess: () => setDeleting(null) })}
        />
      )}
    </>
  );
}
