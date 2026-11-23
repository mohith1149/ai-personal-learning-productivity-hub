import { useState, type FormEvent } from "react";
import {
  useBulkLessons,
  useCreateLesson,
  useCreateModule,
  useRenameModule,
  useUpdateLesson,
  type Lesson,
  type Module,
} from "../../api/courses";
import { FormError, SelectInput, TextArea, TextInput } from "../../components/forms";
import { Modal } from "../../components/Modal";
import { Button } from "../../components/ui";
import { parseLessonLines } from "../../lib/lessons";

/** Add a module, or rename an existing one. */
export function ModuleModal({ courseId, module, onClose }: { courseId: number; module: Module | null; onClose: () => void }) {
  const create = useCreateModule();
  const rename = useRenameModule();
  const [title, setTitle] = useState(module?.title ?? "");
  const [localError, setLocalError] = useState<string | null>(null);
  const error = (create.error ?? rename.error)?.message ?? null;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return setLocalError("Please give the module a title.");
    setLocalError(null);
    if (module) rename.mutate({ id: module.id, title: title.trim() }, { onSuccess: onClose });
    else create.mutate({ courseId, title: title.trim() }, { onSuccess: onClose });
  };

  return (
    <Modal title={module ? "Rename module" : "Add module"} onClose={onClose}>
      <form onSubmit={submit} className="space-y-4" noValidate>
        <TextInput label="Title" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} required />
        <FormError message={localError ?? error} />
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={create.isPending || rename.isPending}>
            {module ? "Save" : "Add module"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

/** Add a lesson to a module, or edit one (including moving it to another module of the same course). */
export function LessonModal({
  moduleId,
  lesson,
  modules,
  onClose,
}: {
  moduleId: number;
  lesson: Lesson | null;
  modules: Module[];
  onClose: () => void;
}) {
  const create = useCreateLesson();
  const update = useUpdateLesson();
  const [f, setF] = useState({
    title: lesson?.title ?? "",
    url: lesson?.url ?? "",
    lesson_type: lesson?.lesson_type ?? "lesson",
    duration: lesson?.duration_minutes?.toString() ?? "",
    notes: lesson?.notes ?? "",
    module_id: String(lesson?.module_id ?? moduleId),
  });
  const [localError, setLocalError] = useState<string | null>(null);
  const set = (k: keyof typeof f) => (v: string) => setF((p) => ({ ...p, [k]: v }));
  const error = (create.error ?? update.error)?.message ?? null;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!f.title.trim()) return setLocalError("Please give the lesson a title.");
    setLocalError(null);
    const body = {
      title: f.title.trim(),
      url: f.url.trim() || null,
      lesson_type: f.lesson_type as "lesson" | "video",
      duration_minutes: f.duration.trim() ? Number(f.duration) : null,
      notes: f.notes.trim() || null,
    };
    if (lesson) update.mutate({ id: lesson.id, body: { ...body, module_id: Number(f.module_id) } }, { onSuccess: onClose });
    else create.mutate({ moduleId, body }, { onSuccess: onClose });
  };

  return (
    <Modal title={lesson ? "Edit lesson" : "Add lesson"} onClose={onClose}>
      <form onSubmit={submit} className="space-y-4" noValidate>
        <TextInput label="Title" value={f.title} onChange={(e) => set("title")(e.target.value)} maxLength={300} required />
        <TextInput label="Link" type="url" placeholder="https://…" value={f.url} onChange={(e) => set("url")(e.target.value)} hint="Must start with http:// or https://" />
        <div className="grid gap-4 sm:grid-cols-2">
          <SelectInput label="Type" value={f.lesson_type} onChange={(e) => set("lesson_type")(e.target.value)}>
            <option value="lesson">Lesson</option>
            <option value="video">Video</option>
          </SelectInput>
          <TextInput label="Duration (minutes)" type="number" min={1} max={1440} value={f.duration} onChange={(e) => set("duration")(e.target.value)} />
        </div>
        {lesson && modules.length > 1 && (
          <SelectInput label="Module" value={f.module_id} onChange={(e) => set("module_id")(e.target.value)}>
            {modules.map((m) => (
              <option key={m.id} value={m.id}>
                {m.title}
              </option>
            ))}
          </SelectInput>
        )}
        <TextArea label="Notes" value={f.notes} onChange={(e) => set("notes")(e.target.value)} />
        <FormError message={localError ?? error} />
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={create.isPending || update.isPending}>
            {lesson ? "Save changes" : "Add lesson"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

/** Paste a list of lesson titles (one per line) into a module. Nothing is marked complete. */
export function BulkLessonsModal({ courseId, module, onClose }: { courseId: number; module: Module; onClose: () => void }) {
  const bulk = useBulkLessons();
  const [text, setText] = useState("");
  const titles = parseLessonLines(text);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (titles.length === 0) return;
    bulk.mutate({ courseId, moduleId: module.id, titles }, { onSuccess: onClose });
  };

  return (
    <Modal title={`Paste lessons into "${module.title}"`} onClose={onClose}>
      <form onSubmit={submit} className="space-y-4" noValidate>
        <TextArea
          label="Lesson titles, one per line"
          rows={8}
          value={text}
          onChange={(e) => setText(e.target.value)}
          hint="Bullets and numbers like “1.” or “-” at the start of a line are removed. Lessons start as not started."
        />
        <p className="text-sm text-slate-600 dark:text-slate-300" aria-live="polite">
          {titles.length === 0 ? "Nothing to add yet." : `${titles.length} lesson${titles.length === 1 ? "" : "s"} will be added.`}
        </p>
        {titles.length > 200 && <FormError message="You can add at most 200 lessons at a time." />}
        <FormError message={bulk.error?.message} />
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={bulk.isPending} disabled={titles.length === 0 || titles.length > 200}>
            Add lessons
          </Button>
        </div>
      </form>
    </Modal>
  );
}
