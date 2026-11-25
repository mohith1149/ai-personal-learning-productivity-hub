import { useState, type FormEvent } from "react";
import { useAiStatus, useAutofill } from "../../api/assistant";
import { PRIORITY_LABEL, PROJECT_STATUS_LABEL, useAddMilestone, useCreateProject, useRepoPreview, useUpdateProject, type Origin, type ProjectDetail, type ProjectStatus, type ProjectSummary } from "../../api/projects";
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
  const aiOn = useAiStatus().data?.connected === true;
  const autofill = useAutofill();
  const addMilestone = useAddMilestone();
  const [aiNote, setAiNote] = useState<string | null>(null);
  const [ideas, setIdeas] = useState<{ title: string; keep: boolean }[]>([]);
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

  /** Ask the AI to suggest the details from the repo link and/or what is already typed in the description. Only EMPTY fields are filled. */
  const suggestWithAi = () => {
    setLocalError(null);
    setAiNote(null);
    const repo = f.repo_url.trim();
    const desc = f.description.trim();
    if (!repo && !desc) return setLocalError("Enter a GitHub link or a short description first, then ask the AI to fill in the rest.");
    if (repo && !REPO.test(repo)) return setLocalError("Enter a GitHub link like https://github.com/owner/repository.");
    autofill.mutate(
      { ...(repo ? { repo_url: repo } : {}), ...(desc ? { description: desc } : {}) },
      {
        onSuccess: (r) => {
          setF((cur) => ({
            ...cur,
            title: cur.title.trim() ? cur.title : r.title,
            description: cur.description.trim() ? cur.description : (r.description ?? ""),
            objective: cur.objective.trim() ? cur.objective : (r.objective ?? ""),
            stack: cur.stack.trim() ? cur.stack : r.tech_stack.join(", "),
            repo_url: r.repo_url ?? cur.repo_url,
            start_date: cur.start_date || (cur.origin === "existing" ? (r.start_date ?? "") : ""),
          }));
          setIdeas(r.milestones.map((title) => ({ title, keep: true })));
          setAiNote("The AI filled the empty fields. It can be wrong, so read them and edit anything before you create the project.");
        },
      },
    );
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
    const done = async (p: ProjectDetail) => {
      let latest = p;
      if (!project) {
        for (const idea of ideas.filter((i) => i.keep && i.title.trim())) {
          try {
            latest = await addMilestone.mutateAsync({ projectId: p.id, body: { title: idea.title.trim() } });
          } catch {
            break; // the project exists; a milestone that failed can be added from its page
          }
        }
      }
      onSaved?.(latest);
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
            <div className="flex flex-wrap gap-2">
              <Button type="button" variant="secondary" loading={preview.isPending} onClick={fillFromGitHub}>
                Fill from GitHub
              </Button>
              {aiOn && (
                <Button type="button" variant="secondary" loading={autofill.isPending} onClick={suggestWithAi}>
                  Suggest with AI
                </Button>
              )}
            </div>
            {filled && <p className="mt-1 text-xs text-slate-600 dark:text-slate-400">{filled}</p>}
            {aiNote && <p className="mt-1 text-xs text-slate-600 dark:text-slate-400">{aiNote}</p>}
            {autofill.error && <FormError message={autofill.error.message} />}
          </div>
        )}
        {!project && ideas.length > 0 && (
          <fieldset className="rounded-lg border border-slate-200 p-3 dark:border-slate-700">
            <legend className="px-1 text-sm font-medium text-slate-700 dark:text-slate-300">Suggested milestones (added when you create the project)</legend>
            <ul className="space-y-1">
              {ideas.map((idea, i) => (
                <li key={i} className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    aria-label={`Keep milestone: ${idea.title}`}
                    checked={idea.keep}
                    onChange={(e) => setIdeas(ideas.map((x, j) => (j === i ? { ...x, keep: e.target.checked } : x)))}
                  />
                  <input
                    aria-label={`Milestone ${i + 1}`}
                    value={idea.title}
                    maxLength={200}
                    onChange={(e) => setIdeas(ideas.map((x, j) => (j === i ? { ...x, title: e.target.value } : x)))}
                    className="w-full rounded border border-slate-300 bg-white px-2 py-1 text-sm dark:border-slate-700 dark:bg-slate-950"
                  />
                </li>
              ))}
            </ul>
          </fieldset>
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
