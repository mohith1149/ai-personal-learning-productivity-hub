import { Check, Clock, Pencil, Repeat, Trash2 } from "lucide-react";
import type { Task } from "../../api/tasks";
import { Badge, StatusBadge, cx } from "../../components/ui";
import { describeDue } from "../../lib/dates";
import { priorityLabel } from "./constants";

export function TaskRow({
  task,
  today,
  busy,
  onToggle,
  onEdit,
  onDelete,
}: {
  task: Task;
  today: string;
  busy: boolean;
  onToggle: (t: Task) => void;
  onEdit: (t: Task) => void;
  onDelete: (t: Task) => void;
}) {
  const done = task.status === "completed";
  const closed = done || task.status === "cancelled";
  const due = describeDue(task, today);

  return (
    <li
      className={cx(
        "group flex items-start gap-3 rounded-xl border bg-white p-3.5 shadow-sm dark:bg-slate-900",
        task.is_overdue ? "border-red-300 dark:border-red-900" : "border-slate-200 dark:border-slate-800",
      )}
    >
      <button
        role="checkbox"
        aria-checked={done}
        aria-label={done ? `Mark "${task.title}" as not done` : `Mark "${task.title}" as done`}
        disabled={busy || task.status === "cancelled"}
        onClick={() => onToggle(task)}
        className={cx(
          "mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-md border transition disabled:opacity-50",
          done
            ? "border-emerald-600 bg-emerald-600 text-white"
            : "border-slate-300 hover:border-brand-500 dark:border-slate-600",
        )}
      >
        {done && <Check className="h-3.5 w-3.5" aria-hidden />}
      </button>

      <div className="min-w-0 flex-1">
        <button
          onClick={() => onEdit(task)}
          className={cx(
            "block w-full truncate text-left text-sm font-medium hover:underline",
            closed ? "text-slate-400 line-through dark:text-slate-500" : "text-slate-900 dark:text-slate-100",
          )}
        >
          {task.title}
        </button>

        <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-500 dark:text-slate-400">
          {task.is_overdue && <StatusBadge status="overdue" />}
          {task.status === "in_progress" && <StatusBadge status="in_progress" />}
          {task.status === "cancelled" && <StatusBadge status="cancelled" />}
          {done && <StatusBadge status="completed" />}
          {due && !done && (
            <span className={cx("inline-flex items-center gap-1", due.overdue && "font-medium text-red-600 dark:text-red-400")}>
              <Clock className="h-3.5 w-3.5" aria-hidden />
              {due.text}
            </span>
          )}
          {task.priority !== 3 && (
            <span className={cx(task.priority === 1 && "font-medium text-red-600 dark:text-red-400", task.priority === 2 && "font-medium text-orange-600 dark:text-orange-400")}>
              {priorityLabel(task.priority)} priority
            </span>
          )}
          {task.category && (
            <span className="inline-flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full" style={{ backgroundColor: task.category.color }} aria-hidden />
              {task.category.name}
            </span>
          )}
          {task.estimated_minutes && <span>{task.estimated_minutes} min</span>}
          {task.recurring_task_id && (
            <Badge>
              <Repeat className="mr-1 h-3 w-3" aria-hidden />
              Recurring
            </Badge>
          )}
        </div>
      </div>

      <div className="flex shrink-0 gap-0.5 opacity-100 sm:opacity-0 sm:transition sm:group-focus-within:opacity-100 sm:group-hover:opacity-100">
        <button
          onClick={() => onEdit(task)}
          aria-label={`Edit "${task.title}"`}
          className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 hover:text-slate-800 dark:hover:bg-slate-800 dark:hover:text-slate-200"
        >
          <Pencil className="h-4 w-4" aria-hidden />
        </button>
        <button
          onClick={() => onDelete(task)}
          aria-label={`Delete "${task.title}"`}
          className="rounded-lg p-1.5 text-slate-500 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950/40"
        >
          <Trash2 className="h-4 w-4" aria-hidden />
        </button>
      </div>
    </li>
  );
}
