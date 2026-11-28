/** Roadmap endpoints for the fake API. Mirrors the server's response shapes and the numbers the UI shows (progress,
 *  study totals). The real rules (exact seed, DB constraints, floor percentages) are tested in pytest. */
import type { Roadmap, Stage, StudySession, Topic } from "../api/roadmap";
import type { Fake, Handler } from "./fakeApi";

export type FakeRoadmap = { stages: Stage[]; sessions: (StudySession & { topic_id: number })[] };

let nextId = 7000;

export function mkTopic(o: Partial<Topic> & { stage_id: number }): Topic {
  const n = o.id ?? nextId++;
  return {
    id: n, title: `Topic ${n}`, description: null, position: n, status: "not_started", difficulty: "normal", notes: null, minutes_spent: 0, study_days: 0,
    last_studied_on: null, completed_at: null, ...o,
  };
}

export function mkStage(id: number, title: string, topics: string[]): Stage {
  return {
    id, title, description: null, position: id, total: 0, completed: 0, in_progress: 0, not_started: 0, percent: 0, minutes_spent: 0,
    topics: topics.map((t, i) => mkTopic({ id: id * 100 + i + 1, stage_id: id, title: t, position: i + 1 })),
  };
}

export function defaultRoadmap(): FakeRoadmap {
  return {
    stages: [mkStage(1, "Stage 1 – Programming and Foundations", ["Python", "Java fundamentals", "Git and GitHub"]),
             mkStage(2, "Stage 2 – Machine Learning and Deep Learning", ["PyTorch", "TensorFlow"])],
    sessions: [],
  };
}

export function installFakeRoadmap(fake: Fake, seed: FakeRoadmap = defaultRoadmap()): FakeRoadmap {
  const store = seed;
  const json = (d: unknown, status = 200) => Response.json(d, { status });
  const topics = () => store.stages.flatMap((s) => s.topics);
  const find = (id: number) => topics().find((t) => t.id === id);
  const pct = (a: number, b: number) => (b ? Math.floor((100 * a) / b) : 0);

  const refresh = () => {
    for (const t of topics()) {
      const ss = store.sessions.filter((s) => s.topic_id === t.id);
      t.minutes_spent = ss.reduce((a, s) => a + s.minutes, 0);
      t.study_days = new Set(ss.map((s) => s.date)).size;
      t.last_studied_on = ss.map((s) => s.date).sort().at(-1) ?? null;
    }
    for (const s of store.stages) {
      s.total = s.topics.length;
      s.completed = s.topics.filter((t) => t.status === "completed").length;
      s.in_progress = s.topics.filter((t) => t.status === "in_progress").length;
      s.not_started = s.total - s.completed - s.in_progress;
      s.percent = pct(s.completed, s.total);
      s.minutes_spent = s.topics.reduce((a, t) => a + t.minutes_spent, 0);
    }
  };

  const handler: Handler = ({ method, path, body }) => {
    let m: RegExpMatchArray | null;
    if (path === "/api/roadmap" && method === "GET") {
      refresh();
      const ts = topics();
      const c = ts.filter((t) => t.status === "completed").length;
      const ip = ts.filter((t) => t.status === "in_progress").length;
      const out: Roadmap = {
        stages: store.stages,
        overall: { total: ts.length, completed: c, in_progress: ip, not_started: ts.length - c - ip, percent: pct(c, ts.length), minutes_spent: ts.reduce((a, t) => a + t.minutes_spent, 0) },
        next_topic: ts.find((t) => t.status !== "completed") ?? null,
      };
      return json(out);
    }
    if (path === "/api/roadmap/topics" && method === "POST") {
      const b = body as { stage_id: number; title: string };
      const stage = store.stages.find((s) => s.id === b.stage_id);
      if (!stage) return json({ detail: "Stage not found" }, 404);
      if (stage.topics.some((t) => t.title.toLowerCase() === b.title.toLowerCase())) return json({ detail: "That stage already has a topic with that name" }, 409);
      const t = mkTopic({ stage_id: stage.id, title: b.title, position: stage.topics.length + 1 });
      stage.topics.push(t);
      return json(t, 201);
    }
    if ((m = path.match(/^\/api\/roadmap\/topics\/(\d+)(?:\/(status|study))?$/))) {
      const t = find(Number(m[1]));
      if (!t) return json({ detail: "Topic not found" }, 404);
      const sub = m[2];
      if (!sub && method === "PATCH") return json(Object.assign(t, body));
      if (!sub && method === "DELETE") {
        const stage = store.stages.find((s) => s.id === t.stage_id)!;
        stage.topics.splice(stage.topics.indexOf(t), 1);
        return new Response(null, { status: 204 });
      }
      if (sub === "status") {
        t.status = (body as { status: Topic["status"] }).status;
        t.completed_at = t.status === "completed" ? (t.completed_at ?? new Date().toISOString()) : null;
        return json(t);
      }
      if (sub === "study" && method === "GET") return json(store.sessions.filter((s) => s.topic_id === t.id).sort((a, b) => (a.date < b.date ? 1 : -1)));
      if (sub === "study" && method === "POST") {
        const b = body as { minutes: number; date?: string; notes: string | null };
        const s = { id: nextId++, topic_id: t.id, date: b.date ?? new Date().toISOString().slice(0, 10), minutes: b.minutes, notes: b.notes, created_at: new Date().toISOString() };
        store.sessions.push(s);
        if (t.status === "not_started") t.status = "in_progress"; // studying starts it, never completes it
        return json(s, 201);
      }
    }
    if ((m = path.match(/^\/api\/learning-sessions\/(\d+)$/)) && method === "DELETE") {
      const i = store.sessions.findIndex((s) => s.id === Number(m![1]));
      if (i < 0) return json({ detail: "Study session not found" }, 404);
      store.sessions.splice(i, 1);
      return new Response(null, { status: 204 });
    }
    return undefined;
  };
  fake.handlers.push(handler);
  return store;
}
