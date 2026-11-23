/** Shared design-system primitives. Every feature page builds from these so the app looks consistent. */
import { Loader2, type LucideIcon } from "lucide-react";
import type { ButtonHTMLAttributes, ReactNode } from "react";

export function cx(...parts: (string | false | null | undefined)[]) {
  return parts.filter(Boolean).join(" ");
}

/* ---------- Buttons ---------- */

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";

const BUTTON_STYLES: Record<ButtonVariant, string> = {
  primary: "bg-brand-600 text-white shadow-sm hover:bg-brand-700 dark:bg-brand-500 dark:hover:bg-brand-600",
  secondary:
    "border border-slate-300 bg-white text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800",
  ghost: "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800",
  danger: "bg-red-600 text-white shadow-sm hover:bg-red-700",
};

export function Button({
  variant = "primary",
  loading = false,
  icon: Icon,
  className,
  children,
  disabled,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant; loading?: boolean; icon?: LucideIcon }) {
  return (
    <button
      {...rest}
      disabled={disabled || loading}
      className={cx(
        "inline-flex items-center justify-center gap-2 rounded-lg px-3.5 py-2 text-sm font-medium transition",
        "disabled:cursor-not-allowed disabled:opacity-60",
        BUTTON_STYLES[variant],
        className,
      )}
    >
      {loading ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : Icon && <Icon className="h-4 w-4" aria-hidden />}
      {children}
    </button>
  );
}

/* ---------- Layout blocks ---------- */

export function Card({ className, children }: { className?: string; children: ReactNode }) {
  return (
    <section
      className={cx(
        "rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900",
        className,
      )}
    >
      {children}
    </section>
  );
}

export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: ReactNode }) {
  return (
    <header className="mb-6 flex flex-wrap items-start justify-between gap-3">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-slate-900 dark:text-white">{title}</h1>
        {description && <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">{description}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </header>
  );
}

export function EmptyState({
  icon: Icon,
  title,
  children,
  action,
}: {
  icon?: LucideIcon;
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center rounded-xl border border-dashed border-slate-300 px-6 py-12 text-center dark:border-slate-700">
      {Icon && (
        <div className="mb-3 flex h-11 w-11 items-center justify-center rounded-full bg-brand-50 text-brand-600 dark:bg-slate-800 dark:text-brand-400">
          <Icon className="h-5 w-5" aria-hidden />
        </div>
      )}
      <h2 className="text-base font-semibold text-slate-900 dark:text-white">{title}</h2>
      {children && <div className="mt-1 max-w-md text-sm text-slate-500 dark:text-slate-400">{children}</div>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function Spinner({ label = "Loading…" }: { label?: string }) {
  return (
    <div role="status" className="flex items-center justify-center gap-2 py-12 text-sm text-slate-500 dark:text-slate-400">
      <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
      {label}
    </div>
  );
}

export function ErrorNotice({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const message = error instanceof Error ? error.message : "Something went wrong.";
  return (
    <div
      role="alert"
      className="flex items-center justify-between gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/50 dark:text-red-300"
    >
      <span>{message}</span>
      {onRetry && (
        <Button variant="secondary" onClick={onRetry} className="shrink-0">
          Retry
        </Button>
      )}
    </div>
  );
}

/* ---------- Status badges ----------
 * The brief requires completed / pending / overdue / excused to be visually distinct everywhere.
 * One mapping here keeps every page consistent. */

export type Status = "completed" | "pending" | "in_progress" | "overdue" | "excused" | "not_started" | "skipped" | "cancelled";

const STATUS_STYLES: Record<Status, { label: string; cls: string }> = {
  completed: { label: "Completed", cls: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300" },
  pending: { label: "Pending", cls: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300" },
  in_progress: { label: "In progress", cls: "bg-sky-100 text-sky-800 dark:bg-sky-950 dark:text-sky-300" },
  overdue: { label: "Overdue", cls: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300" },
  excused: { label: "Excused", cls: "bg-violet-100 text-violet-800 dark:bg-violet-950 dark:text-violet-300" },
  not_started: { label: "Not started", cls: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300" },
  skipped: { label: "Skipped", cls: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400" },
  cancelled: { label: "Cancelled", cls: "bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400" },
};

export function StatusBadge({ status }: { status: Status }) {
  const s = STATUS_STYLES[status];
  return <span className={cx("inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium", s.cls)}>{s.label}</span>;
}

export function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "brand" }) {
  return (
    <span
      className={cx(
        "inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium",
        tone === "brand"
          ? "bg-brand-100 text-brand-700 dark:bg-brand-500/20 dark:text-brand-400"
          : "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400",
      )}
    >
      {children}
    </span>
  );
}
