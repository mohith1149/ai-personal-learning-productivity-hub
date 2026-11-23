import { useState, type FormEvent } from "react";
import { useCreateCourse, useUpdateCourse, type CourseDetail, type CourseInput } from "../../api/courses";
import { FormError, SelectInput, TextArea, TextInput } from "../../components/forms";
import { Modal } from "../../components/Modal";
import { Button } from "../../components/ui";
import { PRIORITIES } from "../tasks/constants";

export function CourseForm({
  course,
  onClose,
  onSaved,
}: {
  course: CourseDetail | null;
  onClose: () => void;
  onSaved?: (c: CourseDetail) => void;
}) {
  const create = useCreateCourse();
  const update = useUpdateCourse();
  const [f, setF] = useState({
    title: course?.title ?? "",
    provider: course?.provider ?? "",
    url: course?.url ?? "",
    description: course?.description ?? "",
    notes: course?.notes ?? "",
    kind: course?.kind ?? "course",
    priority: String(course?.priority ?? 2),
    target_date: course?.target_date ?? "",
  });
  const [localError, setLocalError] = useState<string | null>(null);
  const set = (k: keyof typeof f) => (v: string) => setF((p) => ({ ...p, [k]: v }));
  const pending = create.isPending || update.isPending;
  const serverError = (create.error ?? update.error)?.message ?? null;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setLocalError(null);
    if (!f.title.trim()) return setLocalError("Please give the course a title.");
    const body: CourseInput = {
      title: f.title.trim(),
      provider: f.provider.trim() || null,
      url: f.url.trim() || null,
      description: f.description.trim() || null,
      notes: f.notes.trim() || null,
      kind: f.kind as "course" | "video_series",
      priority: Number(f.priority),
      target_date: f.target_date || null,
    };
    const done = (c: CourseDetail) => {
      onSaved?.(c);
      onClose();
    };
    if (course) update.mutate({ id: course.id, body }, { onSuccess: done });
    else create.mutate(body, { onSuccess: done });
  };

  return (
    <Modal title={course ? "Edit course" : "New course"} onClose={onClose} size="lg">
      <form onSubmit={submit} className="space-y-4" noValidate>
        <TextInput label="Title" value={f.title} onChange={(e) => set("title")(e.target.value)} maxLength={200} required />
        <div className="grid gap-4 sm:grid-cols-2">
          <TextInput label="Provider" placeholder="e.g. DeepLearning.AI" value={f.provider} onChange={(e) => set("provider")(e.target.value)} maxLength={100} />
          <TextInput label="Link" type="url" placeholder="https://…" value={f.url} onChange={(e) => set("url")(e.target.value)} hint="Must start with http:// or https://" />
        </div>
        <TextArea label="Description" value={f.description} onChange={(e) => set("description")(e.target.value)} />
        <div className="grid gap-4 sm:grid-cols-3">
          <SelectInput label="Type" value={f.kind} onChange={(e) => set("kind")(e.target.value)}>
            <option value="course">Course</option>
            <option value="video_series">Video series</option>
          </SelectInput>
          <SelectInput label="Priority" value={f.priority} onChange={(e) => set("priority")(e.target.value)}>
            {PRIORITIES.map((p) => (
              <option key={p.value} value={p.value}>
                {p.label}
              </option>
            ))}
          </SelectInput>
          <TextInput label="Target finish date" type="date" value={f.target_date} onChange={(e) => set("target_date")(e.target.value)} />
        </div>
        <TextArea label="Notes" value={f.notes} onChange={(e) => set("notes")(e.target.value)} />
        <FormError message={localError ?? serverError} />
        <div className="flex justify-end gap-2 pt-1">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={pending}>
            {course ? "Save changes" : "Create course"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
