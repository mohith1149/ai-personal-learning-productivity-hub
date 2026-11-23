import { Clock, Trash2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useCreateSession, useDeleteSession, useSessions, type CourseDetail } from "../../api/courses";
import { FormError, SelectInput, TextArea, TextInput } from "../../components/forms";
import { Modal } from "../../components/Modal";
import { Button, Card, Spinner } from "../../components/ui";
import { formatDay } from "../../lib/dates";

export function SessionModal({ course, today, onClose }: { course: CourseDetail; today: string; onClose: () => void }) {
  const create = useCreateSession();
  const lessons = course.modules.flatMap((m) => m.lessons);
  const [f, setF] = useState({ minutes: "", date: today, lesson_id: "", notes: "" });
  const [localError, setLocalError] = useState<string | null>(null);
  const set = (k: keyof typeof f) => (v: string) => setF((p) => ({ ...p, [k]: v }));

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const minutes = Number(f.minutes);
    if (!Number.isInteger(minutes) || minutes < 1 || minutes > 1440) return setLocalError("Enter the minutes studied (1 to 1440).");
    if (f.date > today) return setLocalError("You can't log study time in the future.");
    setLocalError(null);
    create.mutate(
      { course_id: course.id, minutes, date: f.date || null, lesson_id: f.lesson_id ? Number(f.lesson_id) : null, notes: f.notes.trim() || null },
      { onSuccess: onClose },
    );
  };

  return (
    <Modal title="Log study time" onClose={onClose}>
      <form onSubmit={submit} className="space-y-4" noValidate>
        <div className="grid gap-4 sm:grid-cols-2">
          <TextInput label="Minutes studied" type="number" min={1} max={1440} value={f.minutes} onChange={(e) => set("minutes")(e.target.value)} required />
          <TextInput label="Date" type="date" max={today} value={f.date} onChange={(e) => set("date")(e.target.value)} />
        </div>
        {lessons.length > 0 && (
          <SelectInput label="Lesson (optional)" value={f.lesson_id} onChange={(e) => set("lesson_id")(e.target.value)}>
            <option value="">Not tied to a lesson</option>
            {lessons.map((l) => (
              <option key={l.id} value={l.id}>
                {l.title}
              </option>
            ))}
          </SelectInput>
        )}
        <TextArea label="What did you study?" value={f.notes} onChange={(e) => set("notes")(e.target.value)} />
        <FormError message={localError ?? create.error?.message} />
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={create.isPending}>
            Log time
          </Button>
        </div>
      </form>
    </Modal>
  );
}

export function StudyLog({ course, today, onLog }: { course: CourseDetail; today: string; onLog: () => void }) {
  const sessions = useSessions(course.id);
  const del = useDeleteSession();
  const lessonTitle = (id: number | null) => course.modules.flatMap((m) => m.lessons).find((l) => l.id === id)?.title;

  return (
    <Card>
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-900 dark:text-white">
          <Clock className="h-4 w-4 text-brand-500" aria-hidden />
          Study time
          {course.minutes_studied > 0 && (
            <span className="font-normal text-slate-500 dark:text-slate-400">· {course.minutes_studied} min total</span>
          )}
        </h2>
        <Button variant="secondary" onClick={onLog}>
          Log study time
        </Button>
      </div>
      {sessions.isPending ? (
        <Spinner label="Loading…" />
      ) : sessions.data && sessions.data.length > 0 ? (
        <ul className="divide-y divide-slate-100 dark:divide-slate-800" aria-label="Study sessions">
          {sessions.data.map((s) => (
            <li key={s.id} className="flex items-start justify-between gap-3 py-2 text-sm">
              <div className="min-w-0">
                <span className="font-medium">{s.minutes} min</span>
                <span className="text-slate-500 dark:text-slate-400"> · {formatDay(s.date, today)}</span>
                {lessonTitle(s.lesson_id) && <span className="text-slate-500 dark:text-slate-400"> · {lessonTitle(s.lesson_id)}</span>}
                {s.notes && <p className="mt-0.5 text-slate-600 dark:text-slate-300">{s.notes}</p>}
              </div>
              <button
                onClick={() => del.mutate(s.id)}
                aria-label={`Delete ${s.minutes} minute session`}
                className="rounded-lg p-1.5 text-slate-500 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950/40"
              >
                <Trash2 className="h-4 w-4" aria-hidden />
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-slate-500 dark:text-slate-400">No study time logged yet.</p>
      )}
    </Card>
  );
}
