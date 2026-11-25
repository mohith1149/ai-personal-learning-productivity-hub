import { useState, type FormEvent } from "react";
import { PRIORITY_LABEL, PROJECT_STATUS_LABEL, useCreateProject, useRepoPreview, useUpdateProject, type Origin, type ProjectDetail, type ProjectStatus, type ProjectSummary } from "../../api/projects";
import { FormError, SelectInput, TextArea, TextInput } from "../../components/forms";
import { Modal } from "../../components/Modal";
import { Button } from "../../components/ui";

const REPO = /^https:\/\/github\.com\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+?(\.git)?\/?$/;

/** Create a new project, bring in an existing one, or edit either. */
export function ProjectForm({ project, onClose, onSaved }: { project: ProjectSummary | null; onClose: () => void; onSaved?: (p: ProjectDetail) => void }) {
  const create = useCreateProject();
  const update = useUpdateProject();
  const preview = useRepoPreview();
  const [filled, setFilled] = useState<string | null>(null);
  const [f, setF] = useState({
    title: project?.title ?? "",
    origin: (project?.origin ?? "new") as Origin,
    description: project?.description ?? "",
    objective: project?.objective ?? "",
    stack: (project?.tech_stack ?? []).join(", "),
    repo_url: project?.repo_url ?? "",
    status: (project?.status ?? "active") as ProjectStatus,
    priority: String(project?.priority ?? 2),
    start_date: project?.start_date ?? "",
    target_date: project?.target_date ?? "",
  });
  const [localError, setLocalError] = useState<string | null>(null);
  const pending = create.isPending || update.isPending;

  /** Fill only EMPTY fields so anything already typed is never overwritten. */
  const fillFromGitHub = () => {
    setLocalError(null);
    setFilled(null);
    if (!REPO.test(f.repo_url.trim())) return setLocalError("Enter a GitHub link like https://github.com/owner/repository first.");
    preview.mutate(f.repo_url.trim(), {
      onSuccess: (r) => {
        setF((cur) => ({
          ...cur,
          title: cur.title.trim() ? cur.title : r.title,
          description: cur.description.trim() ? cur.description : (r.description ?? ""),
          stack: cur.stack.trim() ? cur.stack : r.tech_stack.join(", "),
          repo_url: r.repo_url,
          start_date: cur.start_date || (cur.origin === "existing" ? (r.start_date ?? "") : ""),
        }));
        setFilled("Filled the empty fields from GitHub. Check them, add the objective, and edit anything.");
      },
    });
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setLocalError(null);
    if (!f.title.trim()) return setLocalError("Please give the project a name.");
    if (f.repo_url.trim() && !REPO.test(f.repo_url.trim())) return setLocalError("Enter a GitHub link like https://github.com/owner/repository.");
    if (f.start_date && f.target_date && f.target_date < f.start_date) return setLocalError("The target date can't be before the start date.");
    const body = {
      title: f.title.trim(),
      origin: f.origin,
      description: f.description.trim() || null,
      objective: f.objective.trim() || null,
      tech_stack: f.stack.split(",").map((x) => x.trim()).filter(Boolean),
      repo_url: f.repo_url.trim() || null,
      status: f.status,
      priority: Number(f.priority),
      start_date: f.start_date || null,
      target_date: f.target_date || null,
    };
    const done = (p: ProjectDetail) => {
      onSaved?.(p);
      onClose();
    };
    if (project) update.mutate({ id: project.id, body }, { onSuccess: done });
    else create.mutate(body, { onSuccess: done });
  };

  return (
    <Modal title={project ? "Edit project" : "New project"} onClose={onClose} size="lg">
      <form onSubmit={submit} className="space-y-4" noValidate>
        <TextInput label="Project name" value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} maxLength={200} />
        <div className="grid gap-3 sm:grid-cols-3">
          <SelectInput label="Is it new?" value={f.origin} onChange={(e) => setF({ ...f, origin: e.target.value as Origin })}>
            <option value="new">A new project</option>
            <option value="existing">An existing project</option>
          </SelectInput>
          <SelectInput label="Status" value={f.status} onChange={(e) => setF({ ...f, status: e.target.value as ProjectStatus })}>
            {(Object.keys(PROJECT_STATUS_LABEL) as ProjectStatus[]).map((s) => (
              <option key={s} value={s}>
                {PROJECT_STATUS_LABEL[s]}
              </option>
            ))}
          </SelectInput>
          <SelectInput label="Priority" value={f.priority} onChange={(e) => setF({ ...f, priority: e.target.value })}>
            {[1, 2, 3, 4].map((p) => (
              <option key={p} value={p}>
                {PRIORITY_LABEL[p]}
              </option>
            ))}
          </SelectInput>
        </div>
        <TextArea label="Description" rows={2} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} />
        <TextArea label="Objective" rows={2} value={f.objective} onChange={(e) => setF({ ...f, objective: e.target.value })} hint="What do you want to achieve or learn?" />
        <TextInput label="Technology stack" value={f.stack} onChange={(e) => setF({ ...f, stack: e.target.value })} placeholder="Python, FastAPI, ChromaDB" hint="Separate with commas." />
        <TextInput label="GitHub repository" value={f.repo_url} onChange={(e) => setF({ ...f, repo_url: e.target.value })} placeholder="https://github.com/owner/repository" />
        {!project && (
          <div>
            <Button type="button" variant="secondary" loading={preview.isPending} onClick={fillFromGitHub}>
              Fill from GitHub
            </Button>
            {filled && <p className="mt-1 text-xs text-slate-600 dark:text-slate-400">{filled}</p>}
          </div>
        )}
        <div className="grid gap-3 sm:grid-cols-2">
          <TextInput label="Start date" type="date" value={f.start_date} onChange={(e) => setF({ ...f, start_date: e.target.value })} hint={f.origin === "new" ? "Leave empty to start today." : "Optional."} />
          <TextInput label="Target completion date" type="date" value={f.target_date} onChange={(e) => setF({ ...f, target_date: e.target.value })} />
        </div>
        <FormError message={localError ?? (create.error ?? update.error ?? preview.error)?.message} />
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={pending}>
            {project ? "Save changes" : "Create project"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
