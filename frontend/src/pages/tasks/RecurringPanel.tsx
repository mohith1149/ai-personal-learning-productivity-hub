import { Pause, Play, Plus, Repeat, Trash2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useAuthStatus } from "../../api/auth";
import {
  useCategories,
  useCreateRecurring,
  useDeleteRecurring,
  useRecurring,
  useUpdateRecurring,
  type Frequency,
  type Recurring,
} from "../../api/tasks";
import { FormError, SelectInput, TextArea, TextInput } from "../../components/forms";
import { ConfirmDialog, Modal } from "../../components/Modal";
import { Badge, Button, EmptyState, ErrorNotice, Spinner, cx } from "../../components/ui";
import { WEEKDAYS, formatDay, todayIn } from "../../lib/dates";
import { FREQUENCIES, PRIORITIES } from "./constants";

export function describeRecurrence(r: Pick<Recurring, "frequency" | "days_of_week" | "day_of_month">): string {
  switch (r.frequency) {
    case "daily":
      return "Every day";
    case "weekdays":
      return "Every weekday (Mon–Fri)";
    case "weekly":
      return `Weekly on ${(r.days_of_week ?? []).map((d) => WEEKDAYS[d]).join(", ")}`;
    case "monthly":
      return `Monthly on day ${r.day_of_month}`;
  }
}

function RecurringForm({ onClose }: { onClose: () => void }) {
  const user = useAuthStatus().data?.user;
  const today = todayIn(user?.timezone ?? "UTC");
  const categories = useCategories();
  const create = useCreateRecurring();
  const [f, setF] = useState({
    title: "",
    description: "",
    category_id: "",
    priority: "3",
    estimated_minutes: "",
    frequency: "daily" as Frequency,
    day_of_month: "1",
    start_date: today,
    end_date: "",
  });
  const [days, setDays] = useState<number[]>([]);
  const [localError, setLocalError] = useState<string | null>(null);
  const set = (k: keyof typeof f) => (v: string) => setF((p) => ({ ...p, [k]: v }));

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setLocalError(null);
    if (!f.title.trim()) return setLocalError("Please give the task a title.");
    if (f.frequency === "weekly" && days.length === 0) return setLocalError("Pick at least one day of the week.");
    if (f.end_date && f.end_date < f.start_date) return setLocalError("The end date can't be before the start date.");
    create.mutate(
      {
        title: f.title.trim(),
        description: f.description.trim() || null,
        category_id: f.category_id ? Number(f.category_id) : null,
        priority: Number(f.priority),
        estimated_minutes: f.estimated_minutes ? Number(f.estimated_minutes) : null,
        frequency: f.frequency,
        days_of_week: f.frequency === "weekly" ? days : null,
        day_of_month: f.frequency === "monthly" ? Number(f.day_of_month) : null,
        start_date: f.start_date || null,
        end_date: f.end_date || null,
      },
      { onSuccess: onClose },
    );
  };

  return (
    <Modal title="New recurring task" onClose={onClose} size="lg">
      <form onSubmit={submit} className="space-y-4" noValidate>
        <TextInput label="Title" value={f.title} onChange={(e) => set("title")(e.target.value)} maxLength={200} required />
        <TextArea label="Description" value={f.description} onChange={(e) => set("description")(e.target.value)} />
        <div className="grid gap-4 sm:grid-cols-2">
          <SelectInput label="Category" value={f.category_id} onChange={(e) => set("category_id")(e.target.value)}>
            <option value="">No category</option>
            {categories.data?.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </SelectInput>
          <SelectInput label="Priority" value={f.priority} onChange={(e) => set("priority")(e.target.value)}>
            {PRIORITIES.map((p) => (
              <option key={p.value} value={p.value}>
                {p.label}
              </option>
            ))}
          </SelectInput>
        </div>

        <SelectInput label="Repeats" value={f.frequency} onChange={(e) => set("frequency")(e.target.value)}>
          {FREQUENCIES.map((x) => (
            <option key={x.value} value={x.value}>
              {x.label}
            </option>
          ))}
        </SelectInput>

        {f.frequency === "weekly" && (
          <fieldset>
            <legend className="mb-1 text-sm font-medium text-slate-700 dark:text-slate-300">On these days</legend>
            <div className="flex flex-wrap gap-1.5">
              {WEEKDAYS.map((name, i) => {
                const on = days.includes(i);
                return (
                  <button
                    key={name}
                    type="button"
                    aria-pressed={on}
                    onClick={() => setDays((d) => (on ? d.filter((x) => x !== i) : [...d, i].sort()))}
                    className={cx(
                      "rounded-lg border px-3 py-1.5 text-sm font-medium transition",
                      on
                        ? "border-brand-600 bg-brand-600 text-white"
                        : "border-slate-300 text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800",
                    )}
                  >
                    {name}
                  </button>
                );
              })}
            </div>
          </fieldset>
        )}

        {f.frequency === "monthly" && (
          <TextInput
            label="Day of the month"
            type="number"
            min={1}
            max={31}
            value={f.day_of_month}
            onChange={(e) => set("day_of_month")(e.target.value)}
            hint="In shorter months it falls on the last day (e.g. day 31 → 30 April, 28 February)."
          />
        )}

        <div className="grid gap-4 sm:grid-cols-3">
          <TextInput label="Starts" type="date" min={today} value={f.start_date} onChange={(e) => set("start_date")(e.target.value)} />
          <TextInput label="Ends (optional)" type="date" value={f.end_date} onChange={(e) => set("end_date")(e.target.value)} />
          <TextInput
            label="Estimate (min)"
            type="number"
            min={1}
            max={1440}
            value={f.estimated_minutes}
            onChange={(e) => set("estimated_minutes")(e.target.value)}
          />
        </div>

        <FormError message={localError ?? create.error?.message} />
        <div className="flex justify-end gap-2 pt-1">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={create.isPending}>
            Create recurring task
          </Button>
        </div>
      </form>
    </Modal>
  );
}

export function RecurringPanel() {
  const user = useAuthStatus().data?.user;
  const today = todayIn(user?.timezone ?? "UTC");
  const list = useRecurring();
  const update = useUpdateRecurring();
  const del = useDeleteRecurring();
  const [creating, setCreating] = useState(false);
  const [deleting, setDeleting] = useState<Recurring | null>(null);

  return (
    <div>
      <div className="mb-4 flex items-center justify-between gap-3">
        <p className="text-sm text-slate-500 dark:text-slate-400">
          Templates that create a task automatically. Days you miss show up as overdue; they never disappear.
        </p>
        <Button icon={Plus} onClick={() => setCreating(true)} className="shrink-0">
          New recurring task
        </Button>
      </div>

      {update.error && <div className="mb-3"><ErrorNotice error={update.error} /></div>}
      {list.isPending ? (
        <Spinner />
      ) : list.isError ? (
        <ErrorNotice error={list.error} onRetry={() => list.refetch()} />
      ) : list.data.length === 0 ? (
        <EmptyState icon={Repeat} title="No recurring tasks yet">
          Create one for anything you do on a schedule, like a daily review or a weekly planning session.
        </EmptyState>
      ) : (
        <ul className="space-y-2">
          {list.data.map((r) => (
            <li
              key={r.id}
              className="flex items-start gap-3 rounded-xl border border-slate-200 bg-white p-3.5 shadow-sm dark:border-slate-800 dark:bg-slate-900"
            >
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className={cx("truncate text-sm font-medium", !r.active && "text-slate-400 dark:text-slate-500")}>{r.title}</span>
                  {!r.active && <Badge>Paused</Badge>}
                </div>
                <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                  {describeRecurrence(r)} · from {formatDay(r.start_date, today)}
                  {r.end_date ? ` until ${formatDay(r.end_date, today)}` : ""}
                  {r.category ? ` · ${r.category.name}` : ""}
                </div>
              </div>
              <Button
                variant="secondary"
                icon={r.active ? Pause : Play}
                loading={update.isPending && update.variables?.id === r.id}
                onClick={() => update.mutate({ id: r.id, body: { active: !r.active } })}
                aria-label={r.active ? `Pause "${r.title}"` : `Resume "${r.title}"`}
              >
                {r.active ? "Pause" : "Resume"}
              </Button>
              <button
                onClick={() => setDeleting(r)}
                aria-label={`Delete recurring task "${r.title}"`}
                className="rounded-lg p-2 text-slate-500 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950/40"
              >
                <Trash2 className="h-4 w-4" aria-hidden />
              </button>
            </li>
          ))}
        </ul>
      )}

      {creating && <RecurringForm onClose={() => setCreating(false)} />}
      {deleting && (
        <ConfirmDialog
          title="Delete recurring task?"
          message={
            <>
              This stops <strong>{deleting.title}</strong> from repeating. Tasks it already created stay in your list.
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
    </div>
  );
}
