import { useState, type FormEvent } from "react";
import { useCategories, useCreateTask, useUpdateTask, type Task, type TaskInput, type TaskStatus } from "../../api/tasks";
import { FormError, SelectInput, TextArea, TextInput } from "../../components/forms";
import { Modal } from "../../components/Modal";
import { Button } from "../../components/ui";
import { PRIORITIES } from "./constants";

type Props = {
  /** Existing task to edit, or null to create. */
  task: Task | null;
  /** Pre-filled values for a new task (e.g. today's date when created from the Today tab). */
  defaults?: Partial<Pick<TaskInput, "due_date" | "scheduled_date">>;
  onClose: () => void;
};

const STATUSES: { value: TaskStatus; label: string }[] = [
  { value: "pending", label: "Pending" },
  { value: "in_progress", label: "In progress" },
  { value: "completed", label: "Completed" },
  { value: "cancelled", label: "Cancelled" },
];

const num = (s: string): number | null => (s.trim() === "" ? null : Number(s));

export function TaskForm({ task, defaults, onClose }: Props) {
  const editing = task !== null;
  const categories = useCategories();
  const create = useCreateTask();
  const update = useUpdateTask();

  const [f, setF] = useState({
    title: task?.title ?? "",
    description: task?.description ?? "",
    notes: task?.notes ?? "",
    category_id: task?.category_id?.toString() ?? "",
    priority: String(task?.priority ?? 3),
    status: task?.status ?? "pending",
    scheduled_date: task?.scheduled_date ?? defaults?.scheduled_date ?? "",
    due_date: task?.due_date ?? defaults?.due_date ?? "",
    due_time: task?.due_time ?? "",
    estimated_minutes: task?.estimated_minutes?.toString() ?? "",
    actual_minutes: task?.actual_minutes?.toString() ?? "",
  });
  const [localError, setLocalError] = useState<string | null>(null);
  const set = (k: keyof typeof f) => (v: string) => setF((p) => ({ ...p, [k]: v }));

  const pending = create.isPending || update.isPending;
  const serverError = (create.error ?? update.error)?.message ?? null;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setLocalError(null);
    if (!f.title.trim()) return setLocalError("Please give the task a title.");
    if (f.scheduled_date && f.due_date && f.due_date < f.scheduled_date)
      return setLocalError("The due date can't be before the scheduled date.");

    const body: TaskInput = {
      title: f.title.trim(),
      description: f.description.trim() || null,
      notes: f.notes.trim() || null,
      category_id: f.category_id ? Number(f.category_id) : null,
      priority: Number(f.priority),
      scheduled_date: f.scheduled_date || null,
      due_date: f.due_date || null,
      due_time: f.due_date && f.due_time ? f.due_time : null, // a time without a date is meaningless
      estimated_minutes: num(f.estimated_minutes),
    };
    if (task) {
      update.mutate(
        { id: task.id, body: { ...body, status: f.status, actual_minutes: num(f.actual_minutes) } },
        { onSuccess: onClose },
      );
    } else {
      create.mutate(body, { onSuccess: onClose });
    }
  };

  return (
    <Modal title={editing ? "Edit task" : "New task"} onClose={onClose} size="lg">
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

        <div className="grid gap-4 sm:grid-cols-3">
          <TextInput label="Scheduled for" type="date" value={f.scheduled_date} onChange={(e) => set("scheduled_date")(e.target.value)} />
          <TextInput label="Due date" type="date" value={f.due_date} onChange={(e) => set("due_date")(e.target.value)} />
          <TextInput
            label="Due time"
            type="time"
            value={f.due_time}
            disabled={!f.due_date}
            onChange={(e) => set("due_time")(e.target.value)}
            hint={f.due_date ? undefined : "Choose a due date first"}
          />
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <TextInput
            label="Estimate (minutes)"
            type="number"
            min={1}
            max={1440}
            value={f.estimated_minutes}
            onChange={(e) => set("estimated_minutes")(e.target.value)}
          />
          {editing && (
            <TextInput
              label="Actual time spent (minutes)"
              type="number"
              min={1}
              max={1440}
              value={f.actual_minutes}
              onChange={(e) => set("actual_minutes")(e.target.value)}
            />
          )}
        </div>

        {editing && (
          <SelectInput label="Status" value={f.status} onChange={(e) => set("status")(e.target.value)}>
            {STATUSES.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </SelectInput>
        )}

        <TextArea label="Notes" value={f.notes} onChange={(e) => set("notes")(e.target.value)} />

        <FormError message={localError ?? serverError} />
        <div className="flex justify-end gap-2 pt-1">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={pending}>
            {editing ? "Save changes" : "Create task"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
