/** Project endpoints for the fake API. Mirrors the server's response shapes and recomputes the derived numbers (progress, time)
 *  from the stored milestones/tasks/sessions. Project tasks live in the shared fake task list (like the real `tasks` table),
 *  so completing one through /api/tasks moves the project's progress. Real rules are tested in pytest. */
import type { DevSession, Milestone, ProjectDetail, ProjectInput, ProjectSummary } from "../api/projects";
import { USER, mkTask, type Fake, type Handler } from "./fakeApi";
import { todayIn } from "../lib/dates";

export type StoredProject = Omit<ProjectSummary, "progress" | "minutes_spent" | "session_count" | "days_active" | "overdue"> & { notes: string | null };
export type FakeProjects = { projects: StoredProject[]; milestones: (Milestone & { project_id: number })[]; taskIds: Record<number, number[]>; sessions: DevSession[] };

let nextId = 6000;

export function mkProject(o: Partial<StoredProject> = {}): StoredProject {
  const n = o.id ?? nextId++;
  return {
    id: n, title: `Project ${n}`, origin: "new", status: "active", priority: 2, description: null, objective: null, tech_stack: [], repo_url: null,
    start_date: null, target_date: null, completed_at: null, last_activity_at: null, created_at: "2026-11-01T00:00:00Z", notes: null, ...o,
  };
}

export function installFakeProjects(fake: Fake, seed: Partial<FakeProjects> = {}): FakeProjects {
  const store: FakeProjects = { projects: seed.projects ?? [], milestones: seed.milestones ?? [], taskIds: seed.taskIds ?? {}, sessions: seed.sessions ?? [] };
  const json = (d: unknown, status = 200) => Response.json(d, { status });
  const today = () => todayIn(USER.timezone);

  const tasksOf = (pid: number) => (store.taskIds[pid] ?? []).map((id) => fake.tasks.find((t) => t.id === id)).filter((t) => !!t);

  const summary = (p: StoredProject): ProjectSummary => {
    const ms = store.milestones.filter((m) => m.project_id === p.id);
    const ts = tasksOf(p.id).filter((t) => t!.status !== "cancelled");
    const mDone = ms.filter((m) => m.status === "done").length;
    const tDone = ts.filter((t) => t!.status === "completed").length;
    const total = ms.length + ts.length;
    const ss = store.sessions.filter((s) => s.project_id === p.id);
    const { notes: _notes, ...rest } = p;
    void _notes;
    return {
      ...rest,
      progress: { milestones_done: mDone, milestones_total: ms.length, tasks_done: tDone, tasks_total: ts.length, percent: total ? Math.floor((100 * (mDone + tDone)) / total) : 0 },
      minutes_spent: ss.reduce((a, s) => a + s.minutes, 0), session_count: ss.length, days_active: new Set(ss.map((s) => s.date)).size,
      overdue: p.status === "active" && !!p.target_date && p.target_date < today(),
    };
  };

  const detail = (p: StoredProject): ProjectDetail => ({
    ...summary(p), notes: p.notes,
    milestones: store.milestones.filter((m) => m.project_id === p.id).map(({ project_id: _pid, ...m }) => { void _pid; return { ...m, overdue: m.status === "pending" && !!m.due_date && m.due_date < today() }; }),
    tasks: tasksOf(p.id).map((t) => ({ id: t!.id, title: t!.title, status: t!.status, priority: t!.priority, due_date: t!.due_date, estimated_minutes: t!.estimated_minutes, completed_at: t!.completed_at })),
    sessions: store.sessions.filter((s) => s.project_id === p.id).sort((a, b) => (a.date < b.date ? 1 : -1)),
  });

  const find = (id: number) => store.projects.find((p) => p.id === id);
  const NF = () => json({ detail: "Project not found" }, 404);

  const handler: Handler = ({ method, path, query, body }) => {
    if (method === "POST" && path === "/api/github/repo-preview") {
      const url = (body as { repo_url: string }).repo_url;
      if (url.endsWith("/missing")) return json({ detail: "GitHub has no repository in me/missing" }, 404);
      return json({ title: "rag-bot", description: "A RAG chatbot.", tech_stack: ["Python", "TypeScript"], repo_url: url, start_date: "2025-03-04", readme_found: true });
    }
    let m: RegExpMatchArray | null;
    if (path === "/api/projects" && method === "GET") return json(store.projects.filter((p) => !query.status || p.status === query.status).map(summary));
    if (path === "/api/projects" && method === "POST") {
      const b = body as ProjectInput;
      if (store.projects.some((p) => p.title.toLowerCase() === b.title.toLowerCase())) return json({ detail: "You already have a project with that name" }, 409);
      const p = mkProject({ ...b, tech_stack: b.tech_stack ?? [], start_date: b.start_date ?? (b.origin === "existing" ? null : today()) } as Partial<StoredProject>);
      store.projects.push(p);
      return json(detail(p), 201);
    }
    if ((m = path.match(/^\/api\/projects\/(\d+)$/))) {
      const p = find(Number(m[1]));
      if (!p) return NF();
      if (method === "GET") return json(detail(p));
      if (method === "PATCH") {
        const b = body as Partial<StoredProject>;
        Object.assign(p, b);
        if (b.status) p.completed_at = b.status === "completed" ? (p.completed_at ?? new Date().toISOString()) : null;
        return json(detail(p));
      }
      if (method === "DELETE") {
        store.projects.splice(store.projects.indexOf(p), 1);
        return new Response(null, { status: 204 });
      }
    }
    if ((m = path.match(/^\/api\/projects\/(\d+)\/(milestones|tasks|sessions)$/)) && method === "POST") {
      const p = find(Number(m[1]));
      if (!p) return NF();
      const b = body as Record<string, unknown>;
      if (m[2] === "milestones") {
        if (store.milestones.some((x) => x.project_id === p.id && x.title.toLowerCase() === String(b.title).toLowerCase())) return json({ detail: "This project already has a milestone with that name" }, 409);
        store.milestones.push({ id: nextId++, project_id: p.id, title: String(b.title), description: null, status: "pending", position: store.milestones.length + 1, due_date: (b.due_date as string) ?? null, completed_at: null, evidence: null, overdue: false });
        return json(detail(p), 201);
      }
      if (m[2] === "tasks") {
        const t = mkTask({ title: String(b.title), priority: (b.priority as number) ?? 2 });
        fake.tasks.push(t);
        (store.taskIds[p.id] ??= []).push(t.id);
        return json(detail(p), 201);
      }
      if (new Date(String(b.date ?? today())) > new Date(today())) return json({ detail: "You can't log development time in the future" }, 422);
      const s: DevSession = { id: nextId++, project_id: p.id, date: (b.date as string) ?? today(), minutes: b.minutes as number, summary: String(b.summary), milestone_id: (b.milestone_id as number) ?? null, task_id: null, notes: null, created_at: new Date().toISOString() };
      store.sessions.push(s);
      return json(s, 201);
    }
    if ((m = path.match(/^\/api\/project-milestones\/(\d+)(?:\/(status))?$/))) {
      const ms = store.milestones.find((x) => x.id === Number(m![1]));
      if (!ms) return json({ detail: "Milestone not found" }, 404);
      const p = find(ms.project_id)!;
      if (m[2] === "status") {
        const b = body as { status: "pending" | "done"; evidence: string | null };
        ms.status = b.status;
        ms.completed_at = b.status === "done" ? (ms.completed_at ?? new Date().toISOString()) : null;
        if (b.evidence) ms.evidence = b.evidence;
      } else if (method === "PATCH") Object.assign(ms, body);
      else if (method === "DELETE") store.milestones.splice(store.milestones.indexOf(ms), 1);
      return json(detail(p));
    }
    if ((m = path.match(/^\/api\/project-sessions\/(\d+)$/)) && method === "DELETE") {
      const i = store.sessions.findIndex((s) => s.id === Number(m![1]));
      if (i < 0) return json({ detail: "Development session not found" }, 404);
      store.sessions.splice(i, 1);
      return new Response(null, { status: 204 });
    }
    return undefined;
  };
  fake.handlers.push(handler);
  return store;
}
