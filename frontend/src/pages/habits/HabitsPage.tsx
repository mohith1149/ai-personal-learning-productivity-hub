import { Check, Flame, History as HistoryIcon, NotebookPen, Pencil, Plus, Repeat, RotateCcw, Trash2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useAuthStatus } from "../../api/auth";
import {
  useCreateHabit,
  useDeleteHabit,
  useDeleteLog,
  useHabits,
  useHistory,
  useSetLog,
  useUpdateHabit,
  type Frequency,
  type Habit,
  type RecentDay,
} from "../../api/habits";
import { FormError, SelectInput, TextArea, TextInput } from "../../components/forms";
import { ConfirmDialog, Modal } from "../../components/Modal";
import { Badge, Button, Card, EmptyState, ErrorNotice, PageHeader, ProgressBar, Spinner, cx } from "../../components/ui";
import { formatDay, todayIn } from "../../lib/dates";

const frequencyLabel = (h: Habit) => (h.frequency === "daily" ? "Every day" : `${h.target_per_period} day${h.target_per_period === 1 ? "" : "s"} a week`);
const unitLabel = (n: number, unit: string) => `${n} ${unit === "days" ? (n === 1 ? "day" : "days") : n === 1 ? "week" : "weeks"}`;

/* ---------------------------------- form ---------------------------------- */

function HabitForm({ habit, today, onClose }: { habit: Habit | null; today: string; onClose: () => void }) {
  const create = useCreateHabit();
  const update = useUpdateHabit();
  const [f, setF] = useState({
    name: habit?.name ?? "",
    description: habit?.description ?? "",
    notes: habit?.notes ?? "",
    start_date: habit?.start_date ?? today,
    frequency: (habit?.frequency ?? "daily") as Frequency,
    per: String(habit?.target_per_period ?? 3),
    target_value: habit?.target_value != null ? String(habit.target_value) : "",
    unit: habit?.unit ?? "",
    active: habit?.active ?? true,
  });
  const [localError, setLocalError] = useState<string | null>(null);
  const pending = create.isPending || update.isPending;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setLocalError(null);
    if (!f.name.trim()) return setLocalError("Please give the habit a name.");
    const per = f.frequency === "weekly" ? Number(f.per) : 1;
    if (!Number.isInteger(per) || per < 1 || per > 7) return setLocalError("Days per week must be a whole number from 1 to 7.");
    const tv = f.target_value.trim() === "" ? null : Number(f.target_value);
    if (tv !== null && !(tv > 0)) return setLocalError("The daily amount must be a number above 0, or left empty.");
    const body = {
      name: f.name.trim(),
      description: f.description.trim() || null,
      notes: f.notes.trim() || null,
      start_date: f.start_date || today,
      frequency: f.frequency,
      target_per_period: per,
      target_value: tv,
      unit: f.unit.trim() || null,
      active: f.active,
    };
    if (habit) update.mutate({ id: habit.id, body }, { onSuccess: onClose });
    else create.mutate(body, { onSuccess: onClose });
  };

  return (
    <Modal title={habit ? "Edit habit" : "New habit"} onClose={onClose}>
      <form onSubmit={submit} className="space-y-4" noValidate>
        <TextInput label="Name" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} maxLength={120} placeholder="e.g. Exercise" />
        <TextArea label="Description" rows={2} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} />
        <div className="grid grid-cols-2 gap-3">
          <SelectInput label="How often" value={f.frequency} onChange={(e) => setF({ ...f, frequency: e.target.value as Frequency })}>
            <option value="daily">Every day</option>
            <option value="weekly">Some days a week</option>
          </SelectInput>
          {f.frequency === "weekly" ? (
            <TextInput label="Days per week" type="number" min={1} max={7} value={f.per} onChange={(e) => setF({ ...f, per: e.target.value })} />
          ) : (
            <TextInput label="Start date" type="date" value={f.start_date} onChange={(e) => setF({ ...f, start_date: e.target.value })} />
          )}
        </div>
        {f.frequency === "weekly" && <TextInput label="Start date" type="date" value={f.start_date} onChange={(e) => setF({ ...f, start_date: e.target.value })} />}
        <div className="grid grid-cols-2 gap-3">
          <TextInput label="Daily amount (optional)" type="number" min={0} step="any" value={f.target_value} onChange={(e) => setF({ ...f, target_value: e.target.value })} placeholder="30" />
          <TextInput label="Unit (optional)" value={f.unit} onChange={(e) => setF({ ...f, unit: e.target.value })} maxLength={30} placeholder="minutes" />
        </div>
        <TextArea label="Notes" rows={2} value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} />
        <label className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300">
          <input type="checkbox" checked={f.active} onChange={(e) => setF({ ...f, active: e.target.checked })} />
          Active (inactive habits are left out of "due today")
        </label>
        <FormError message={localError ?? (create.error ?? update.error)?.message} />
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={pending}>
            {habit ? "Save changes" : "Create habit"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

/* ---------------------------------- record details + history ---------------------------------- */

function DetailsModal({ habit, today, onClose }: { habit: Habit; today: string; onClose: () => void }) {
  const set = useSetLog();
  const [date, setDate] = useState(today);
  const [value, setValue] = useState(habit.today?.value != null ? String(habit.today.value) : "");
  const [note, setNote] = useState(habit.today?.note ?? "");
  const [localError, setLocalError] = useState<string | null>(null);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setLocalError(null);
    const v = value.trim() === "" ? null : Number(value);
    if (v !== null && !(v >= 0)) return setLocalError("The amount must be 0 or more.");
    if (date > today) return setLocalError("You can't record a future day.");
    if (date < habit.start_date) return setLocalError(`This habit starts on ${habit.start_date}.`);
    set.mutate({ id: habit.id, date, body: { completed: true, value: v, note: note.trim() || null } }, { onSuccess: onClose });
  };

  return (
    <Modal title={`Record: ${habit.name}`} onClose={onClose}>
      <form onSubmit={submit} className="space-y-3" noValidate>
        <TextInput label="Day" type="date" min={habit.start_date} max={today} value={date} onChange={(e) => setDate(e.target.value)} />
        <TextInput label={habit.unit ? `Amount (${habit.unit})` : "Amount (optional)"} type="number" min={0} step="any" value={value} onChange={(e) => setValue(e.target.value)} />
        <TextArea label="Note" rows={3} value={note} onChange={(e) => setNote(e.target.value)} />
        <FormError message={localError ?? set.error?.message} />
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={set.isPending}>
            Save as done
          </Button>
        </div>
      </form>
    </Modal>
  );
}

function HistoryModal({ habit, today, onClose }: { habit: Habit; today: string; onClose: () => void }) {
  const history = useHistory(habit.id);
  const del = useDeleteLog();
  return (
    <Modal title={`History: ${habit.name}`} onClose={onClose}>
      {history.isPending ? (
        <Spinner label="Loading history…" />
      ) : history.isError ? (
        <ErrorNotice error={history.error} onRetry={() => history.refetch()} />
      ) : history.data.length === 0 ? (
        <p className="text-sm text-slate-500 dark:text-slate-400">Nothing recorded in the last 90 days.</p>
      ) : (
        <ul aria-label="Habit history" className="divide-y divide-slate-100 dark:divide-slate-800">
          {history.data.map((l) => (
            <li key={l.date} className="flex items-center justify-between gap-2 py-2 text-sm">
              <span className="text-slate-700 dark:text-slate-300">
                <strong>{formatDay(l.date, today)}</strong> · {l.completed ? "Done" : "Not done"}
                {l.value != null && <> · {l.value}{habit.unit ? ` ${habit.unit}` : ""}</>}
                {l.note && <span className="text-slate-500 dark:text-slate-400"> · {l.note}</span>}
              </span>
              <button
                onClick={() => del.mutate({ id: habit.id, date: l.date })}
                aria-label={`Delete record for ${l.date}`}
                className="rounded p-1 text-slate-400 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950/40"
              >
                <Trash2 className="h-4 w-4" aria-hidden />
              </button>
            </li>
          ))}
        </ul>
      )}
      <FormError message={del.error?.message} />
    </Modal>
  );
}

/* ---------------------------------- card ---------------------------------- */

function DayStrip({ habit, onToggle, disabled }: { habit: Habit; onToggle: (d: RecentDay) => void; disabled: boolean }) {
  return (
    <ol aria-label={`Last 28 days of ${habit.name}`} className="mt-3 flex flex-wrap gap-1">
      {habit.recent.map((d) => {
        const before = d.date < habit.start_date;
        return (
          <li key={d.date}>
            <button
              onClick={() => onToggle(d)}
              disabled={disabled || before}
              aria-label={`${d.completed ? "Undo" : "Mark"} ${habit.name} ${d.completed ? "on" : "done on"} ${d.date}`}
              title={d.date}
              className={cx(
                "h-4 w-4 rounded-sm border transition disabled:cursor-not-allowed",
                before && "opacity-30",
                d.completed ? "border-emerald-500 bg-emerald-500" : d.logged ? "border-amber-400 bg-amber-100 dark:bg-amber-900/40" : "border-slate-300 bg-white hover:border-brand-500 dark:border-slate-600 dark:bg-slate-900",
              )}
            />
          </li>
        );
      })}
    </ol>
  );
}

function HabitCard({ habit, today, onEdit }: { habit: Habit; today: string; onEdit: (h: Habit) => void }) {
  const set = useSetLog();
  const delLog = useDeleteLog();
  const del = useDeleteHabit();
  const [details, setDetails] = useState(false);
  const [history, setHistory] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const busy = set.isPending || delLog.isPending;
  const error = set.error ?? delLog.error;
  const weekly = habit.frequency === "weekly";

  const toggleDay = (d: RecentDay) => {
    if (d.completed) delLog.mutate({ id: habit.id, date: d.date });
    else set.mutate({ id: habit.id, date: d.date, body: { completed: true } });
  };

  return (
    <li className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="flex flex-wrap items-center gap-2 text-base font-semibold text-slate-900 dark:text-white">
            <span className="truncate">{habit.name}</span>
            {!habit.active && <Badge>Inactive</Badge>}
          </h3>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            {frequencyLabel(habit)}
            {habit.target_value != null && <> · goal {habit.target_value}{habit.unit ? ` ${habit.unit}` : ""} a day</>}
          </p>
          {habit.description && <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">{habit.description}</p>}
        </div>
        <div className="flex items-center gap-1 text-sm font-medium text-slate-900 dark:text-white" aria-label={`${habit.name} streak`}>
          <Flame className={cx("h-4 w-4", habit.streak.current > 0 ? "text-orange-500" : "text-slate-300")} aria-hidden />
          <span className="tabular-nums">{unitLabel(habit.streak.current, habit.streak.unit)}</span>{" "}
          <span className="text-xs font-normal text-slate-500 dark:text-slate-400">· best {unitLabel(habit.streak.longest, habit.streak.unit)}</span>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        {habit.done_today ? (
          <Button variant="secondary" icon={RotateCcw} loading={delLog.isPending} onClick={() => delLog.mutate({ id: habit.id, date: today })} aria-label={`Undo ${habit.name} for today`}>
            Done today · Undo
          </Button>
        ) : (
          <Button icon={Check} loading={set.isPending} onClick={() => set.mutate({ id: habit.id, date: today, body: { completed: true } })} aria-label={`Mark ${habit.name} done today`}>
            Mark done today
          </Button>
        )}
        <button onClick={() => setDetails(true)} aria-label={`Add details for ${habit.name}`} title="Amount and note" className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800">
          <NotebookPen className="h-4 w-4" aria-hidden />
        </button>
        <button onClick={() => setHistory(true)} aria-label={`History of ${habit.name}`} title="History" className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800">
          <HistoryIcon className="h-4 w-4" aria-hidden />
        </button>
        <button onClick={() => onEdit(habit)} aria-label={`Edit ${habit.name}`} title="Edit" className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800">
          <Pencil className="h-4 w-4" aria-hidden />
        </button>
        <button onClick={() => setConfirm(true)} aria-label={`Delete ${habit.name}`} title="Delete" className="ml-auto rounded-lg p-1.5 text-slate-500 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950/40">
          <Trash2 className="h-4 w-4" aria-hidden />
        </button>
      </div>
      {habit.today && (habit.today.value != null || habit.today.note) && (
        <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
          Today: {habit.today.value != null && <>{habit.today.value}{habit.unit ? ` ${habit.unit}` : ""}</>}
          {habit.today.note && <> · {habit.today.note}</>}
        </p>
      )}

      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <div>
          <ProgressBar percent={habit.week.percent ?? 0} label={`${habit.name} this week`} />
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            This week: {habit.week.completed} {weekly ? `of ${habit.week.target} days` : `of ${habit.week.eligible_days} day${habit.week.eligible_days === 1 ? "" : "s"} so far`}
          </p>
        </div>
        <div>
          <ProgressBar percent={habit.month.percent ?? 0} label={`${habit.name} this month`} />
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            This month: {habit.month.completed} {weekly ? "days done" : `of ${habit.month.eligible_days} days`}
            {habit.month.percent !== null && <> ({habit.month.percent}%)</>}
          </p>
        </div>
      </div>

      <DayStrip habit={habit} onToggle={toggleDay} disabled={busy} />
      {error && (
        <p role="alert" className="mt-2 text-sm text-red-600 dark:text-red-400">
          {error.message}
        </p>
      )}

      {details && <DetailsModal habit={habit} today={today} onClose={() => setDetails(false)} />}
      {history && <HistoryModal habit={habit} today={today} onClose={() => setHistory(false)} />}
      {confirm && (
        <ConfirmDialog
          title="Delete habit?"
          message={
            <>
              <strong>{habit.name}</strong> and all {habit.total_completed} completed-day record{habit.total_completed === 1 ? "" : "s"} will be permanently deleted. This can't be undone.
            </>
          }
          busy={del.isPending}
          error={del.error?.message}
          onCancel={() => {
            setConfirm(false);
            del.reset();
          }}
          onConfirm={() => del.mutate(habit.id, { onSuccess: () => setConfirm(false) })}
        />
      )}
    </li>
  );
}

/* ---------------------------------- page ---------------------------------- */

export function HabitsPage() {
  const habits = useHabits();
  const user = useAuthStatus().data?.user;
  const today = todayIn(user?.timezone ?? "UTC");
  const [form, setForm] = useState<{ habit: Habit | null } | null>(null);

  return (
    <>
      <PageHeader
        title="Habits"
        description="Habits you want to keep up. Streaks and progress are worked out from the days you record, never typed in."
        actions={
          <Button icon={Plus} onClick={() => setForm({ habit: null })}>
            New habit
          </Button>
        }
      />
      {habits.isPending ? (
        <Spinner label="Loading habits…" />
      ) : habits.isError ? (
        <ErrorNotice error={habits.error} onRetry={() => habits.refetch()} />
      ) : habits.data.items.length === 0 ? (
        <EmptyState icon={Repeat} title="No habits yet" action={<Button icon={Plus} onClick={() => setForm({ habit: null })}>New habit</Button>}>
          Add the habits you want to track, such as exercise, reading or coding. Nothing is added for you.
        </EmptyState>
      ) : (
        <>
          <Card className="mb-4" aria-label="Habits due today">
            <p className="text-sm text-slate-700 dark:text-slate-300" role="status">
              {habits.data.due_today === 0 ? "Nothing left to do today. Every active habit is done." : `${habits.data.due_today} habit${habits.data.due_today === 1 ? "" : "s"} still to do today.`}
            </p>
          </Card>
          <ul aria-label="Habits" className="grid gap-4 lg:grid-cols-2">
            {habits.data.items.map((h) => (
              <HabitCard key={h.id} habit={h} today={today} onEdit={(x) => setForm({ habit: x })} />
            ))}
          </ul>
        </>
      )}
      {form && <HabitForm habit={form.habit} today={today} onClose={() => setForm(null)} />}
    </>
  );
}
