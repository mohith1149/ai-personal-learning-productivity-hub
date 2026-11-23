/** Course endpoints for the fake API. Mirrors the SERVER'S RESPONSE SHAPES and the derived values the UI shows
 *  (progress, next lesson, status), kept deliberately simple: the real rules are tested in pytest and end to end. */
import type { CourseDetail, CourseTemplate, Lesson, Module, StudySession } from "../api/courses";
import { TODAY, type Fake, type Handler } from "./fakeApi";

let nextId = 5000;
const id = () => nextId++;

export function mkLesson(o: Partial<Lesson> & { module_id: number; course_id: number }): Lesson {
  const n = o.id ?? id();
  return {
    id: n, title: `Lesson ${n}`, url: null, lesson_type: "lesson", duration_minutes: null, position: n, status: "not_started",
    completed_at: null, notes: null, ...o,
  };
}

export function mkModule(o: Partial<Module> & { lessons?: Lesson[] } = {}): Module {
  const n = o.id ?? id();
  const lessons = o.lessons ?? [];
  return { id: n, title: `Module ${n}`, position: n, total_lessons: lessons.length, completed_lessons: 0, ...o, lessons };
}

export function mkCourse(o: Partial<CourseDetail> = {}): CourseDetail {
  const n = o.id ?? id();
  const c: CourseDetail = {
    id: n, title: `Course ${n}`, provider: null, url: null, description: null, notes: null, kind: "course", status: "active",
    priority: 2, target_date: null, started_at: null, completed_at: null, last_studied_at: null,
    progress: { total_lessons: 0, completed_lessons: 0, percent: 0, empty_modules: 0, total_minutes: 0, remaining_minutes: 0 },
    next_lesson: null, minutes_studied: 0, modules: [], ...o,
  };
  recompute(c);
  return c;
}

export function recompute(c: CourseDetail) {
  const lessons = c.modules.flatMap((m) => m.lessons);
  const done = lessons.filter((l) => l.status === "completed");
  c.progress = {
    total_lessons: lessons.length,
    completed_lessons: done.length,
    percent: lessons.length ? Math.floor((100 * done.length) / lessons.length) : 0,
    empty_modules: c.modules.filter((m) => m.lessons.length === 0).length,
    total_minutes: lessons.reduce((a, l) => a + (l.duration_minutes ?? 0), 0),
    remaining_minutes: lessons.filter((l) => l.status !== "completed").reduce((a, l) => a + (l.duration_minutes ?? 0), 0),
  };
  for (const m of c.modules) {
    m.total_lessons = m.lessons.length;
    m.completed_lessons = m.lessons.filter((l) => l.status === "completed").length;
  }
  const next = c.modules.flatMap((m) => m.lessons.filter((l) => l.status !== "completed").slice(0, 1).map((l) => ({ m, l })))[0];
  c.next_lesson = next ? { id: next.l.id, title: next.l.title, module_id: next.m.id, module_title: next.m.title, status: next.l.status, url: next.l.url } : null;
  const allDone = lessons.length > 0 && done.length === lessons.length && c.progress.empty_modules === 0;
  if (allDone && (c.status === "active" || c.status === "paused")) {
    c.status = "completed";
    c.completed_at = "2026-11-23T10:00:00Z";
  } else if (c.status === "completed" && lessons.length && !allDone) {
    c.status = "active";
    c.completed_at = null;
  }
}

export const AGENTIC_TEMPLATE: CourseTemplate = {
  key: "deeplearning-agentic-ai", title: "Agentic AI", provider: "DeepLearning.AI", url: "https://www.deeplearning.ai/courses/agentic-ai",
  description: "Taught by Andrew Ng. Lessons are not pre-filled.",
  modules: ["Module 1: Introduction to Agentic Workflows", "Module 2: Reflection", "Module 3: Tool Use", "Module 4: Practical Tips for Building Agentic AI", "Module 5: Patterns for Highly Autonomous Agents"],
  already_added: false,
};

export type FakeCourses = { courses: CourseDetail[]; sessions: StudySession[]; templates: CourseTemplate[] };

export function installFakeCourses(fake: Fake, seed: Partial<FakeCourses> = {}): FakeCourses {
  const store: FakeCourses = { courses: seed.courses ?? [], sessions: seed.sessions ?? [], templates: seed.templates ?? [] };
  const json = (data: unknown, status = 200) => Response.json(data, { status });
  const empty = () => new Response(null, { status: 204 });
  const findLesson = (lid: number) => {
    for (const c of store.courses) for (const m of c.modules) for (const l of m.lessons) if (l.id === lid) return { c, m, l };
  };
  const findModule = (mid: number) => {
    for (const c of store.courses) for (const m of c.modules) if (m.id === mid) return { c, m };
  };
  const out = (c: CourseDetail) => (recompute(c), json(c));
  const swap = <T extends { position: number }>(list: T[], i: number, dir: unknown) => {
    const j = dir === "up" ? i - 1 : i + 1;
    if (j < 0 || j >= list.length) return;
    [list[i], list[j]] = [list[j], list[i]];
  };

  const handler: Handler = ({ method, path, query, body }) => {
    let m: RegExpMatchArray | null;
    if (path === "/api/courses" && method === "GET") {
      const list = store.courses.filter((c) => !query.status || c.status === query.status);
      return json(list.map((c) => ({ ...c, modules: undefined, notes: undefined })));
    }
    if (path === "/api/courses" && method === "POST") {
      const c = mkCourse({ ...(body as Partial<CourseDetail>) });
      store.courses.push(c);
      return json(c, 201);
    }
    if ((m = path.match(/^\/api\/courses\/(\d+)$/))) {
      const c = store.courses.find((x) => x.id === Number(m![1]));
      if (!c) return json({ detail: "Course not found" }, 404);
      if (method === "GET") return json(c);
      if (method === "PATCH") {
        const b = body as Partial<CourseDetail>;
        Object.assign(c, b);
        if (b.status === "active" || b.status === "paused" || b.status === "archived") c.completed_at = null;
        return out(c);
      }
      if (method === "DELETE") {
        store.courses.splice(store.courses.indexOf(c), 1);
        return empty();
      }
    }
    if ((m = path.match(/^\/api\/courses\/(\d+)\/modules$/)) && method === "POST") {
      const c = store.courses.find((x) => x.id === Number(m![1]));
      if (!c) return json({ detail: "Course not found" }, 404);
      c.modules.push(mkModule({ title: body!.title as string }));
      recompute(c);
      return json(c, 201);
    }
    if ((m = path.match(/^\/api\/courses\/(\d+)\/bulk-lessons$/)) && method === "POST") {
      const found = findModule(body!.module_id as number);
      if (!found) return json({ detail: "Module not found" }, 404);
      for (const t of body!.titles as string[]) found.m.lessons.push(mkLesson({ title: t, module_id: found.m.id, course_id: found.c.id }));
      recompute(found.c);
      return json(found.c, 201);
    }
    if ((m = path.match(/^\/api\/modules\/(\d+)(\/move|\/lessons)?$/))) {
      const found = findModule(Number(m[1]));
      if (!found) return json({ detail: "Module not found" }, 404);
      const { c, m: mod } = found;
      if (!m[2] && method === "PATCH") mod.title = body!.title as string;
      else if (!m[2] && method === "DELETE") c.modules.splice(c.modules.indexOf(mod), 1);
      else if (m[2] === "/move") swap(c.modules, c.modules.indexOf(mod), body!.direction);
      else if (m[2] === "/lessons") {
        mod.lessons.push(mkLesson({ ...(body as Partial<Lesson>), module_id: mod.id, course_id: c.id } as Lesson));
        recompute(c);
        return json(c, 201);
      }
      return out(c);
    }
    if ((m = path.match(/^\/api\/lessons\/(\d+)(?:\/(start|complete|uncomplete|move))?$/))) {
      const found = findLesson(Number(m[1]));
      if (!found) return json({ detail: "Lesson not found" }, 404);
      const { c, m: mod, l } = found;
      const action = m[2];
      if (!action && method === "PATCH") {
        const { module_id, ...rest } = body as Partial<Lesson>;
        Object.assign(l, rest);
        if (module_id && module_id !== l.module_id) {
          const dest = c.modules.find((x) => x.id === module_id)!;
          mod.lessons.splice(mod.lessons.indexOf(l), 1);
          l.module_id = dest.id;
          dest.lessons.push(l);
        }
      } else if (!action && method === "DELETE") mod.lessons.splice(mod.lessons.indexOf(l), 1);
      else if (action === "move") swap(mod.lessons, mod.lessons.indexOf(l), body!.direction);
      else if (action === "start") {
        if (l.status === "completed") return json({ detail: "This lesson is already completed. Un-complete it first to study it again" }, 422);
        l.status = "in_progress";
        c.started_at = c.started_at ?? "2026-11-23T10:00:00Z";
      } else if (action === "complete") {
        l.status = "completed";
        l.completed_at = l.completed_at ?? "2026-11-23T10:00:00Z";
        c.started_at = c.started_at ?? "2026-11-23T10:00:00Z";
        c.last_studied_at = "2026-11-23T10:00:00Z";
      } else if (action === "uncomplete") {
        l.status = "not_started";
        l.completed_at = null;
      }
      return out(c);
    }
    if (path === "/api/learning-sessions" && method === "GET")
      return json(store.sessions.filter((s) => !query.course_id || s.course_id === Number(query.course_id)));
    if (path === "/api/learning-sessions" && method === "POST") {
      const b = body as { course_id: number; lesson_id: number | null; minutes: number; date: string | null; notes: string | null };
      const s: StudySession = { id: id(), date: b.date ?? TODAY, minutes: b.minutes, course_id: b.course_id, lesson_id: b.lesson_id, notes: b.notes, created_at: "2026-11-23T10:00:00Z" };
      store.sessions.unshift(s);
      const c = store.courses.find((x) => x.id === b.course_id);
      if (c) c.minutes_studied += b.minutes;
      return json(s, 201);
    }
    if ((m = path.match(/^\/api\/learning-sessions\/(\d+)$/)) && method === "DELETE") {
      const i = store.sessions.findIndex((s) => s.id === Number(m![1]));
      if (i < 0) return json({ detail: "Study session not found" }, 404);
      const [s] = store.sessions.splice(i, 1);
      const c = store.courses.find((x) => x.id === s.course_id);
      if (c) c.minutes_studied -= s.minutes;
      return empty();
    }
    if (path === "/api/course-templates" && method === "GET") return json(store.templates);
    if ((m = path.match(/^\/api\/course-templates\/([\w-]+)$/)) && method === "POST") {
      const t = store.templates.find((x) => x.key === m![1]);
      if (!t) return json({ detail: "Template not found" }, 404);
      if (t.already_added) return json({ detail: "You have already added this course" }, 409);
      t.already_added = true;
      const c = mkCourse({ title: t.title, provider: t.provider, url: t.url, description: t.description, modules: t.modules.map((title) => mkModule({ title })) });
      store.courses.push(c);
      return json(c, 201);
    }
    return undefined;
  };
  fake.handlers.push(handler);
  return store;
}
