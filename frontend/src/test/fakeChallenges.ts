/** Challenge endpoints for the fake API. It stores challenges by date and mimics the response SHAPES; the evidence-quality, streak and
 *  missed-day rules are tested against the real API in pytest. Here we only check that the UI sends the right requests and shows the replies. */
import type { CalendarDay, Challenge, Stats, Suggestion } from "../api/challenges";
import { addDays, todayIn } from "../lib/dates";
import { USER, type Fake, type Handler } from "./fakeApi";

export type FakeChallenges = { challenges: Challenge[]; suggestions: Suggestion[]; stats: Partial<Stats>; verifyOk: boolean };

let nextId = 9000;

export function mkChallenge(o: Partial<Challenge> = {}): Challenge {
  const id = o.id ?? nextId++;
  return {
    id, date: todayIn(USER.timezone), mode: "existing_project", status: "planned", project: { id: 1, title: "RAG chatbot", repo_url: null },
    planned_task: "Add the retrieval step", estimated_minutes: null, actual_minutes: null, implemented_summary: null, repo_url: null, commit_sha: null,
    commit_message: null, evidence_notes: null, milestone: null, verification_status: "unverified", excuse_reason: null, completed_at: null,
    can_complete: true, can_edit: true, ...o,
  };
}

export function installFakeChallenges(fake: Fake, seed: Partial<FakeChallenges> = {}): FakeChallenges {
  const store: FakeChallenges = { challenges: seed.challenges ?? [], suggestions: seed.suggestions ?? [], stats: seed.stats ?? {}, verifyOk: seed.verifyOk ?? true };
  const json = (d: unknown, status = 200) => Response.json(d, { status });
  const today = () => todayIn(USER.timezone);

  const stats = (): Stats => {
    const done = store.challenges.filter((c) => c.status === "completed");
    return {
      completed: done.length, excused: store.challenges.filter((c) => c.status === "excused").length, rest_days: 0, missed: 0, completion_rate: done.length ? 100 : 0,
      current_streak: done.length, longest_streak: done.length, total_minutes: done.reduce((n, c) => n + (c.actual_minutes ?? 0), 0),
      first_day: store.challenges.map((c) => c.date).sort()[0] ?? null, ...store.stats,
    };
  };
  const onDay = (d: string) => store.challenges.find((c) => c.date === d);

  const handler: Handler = ({ method, path, body }) => {
    if (path === "/api/challenges/today" && method === "GET") {
      const c = onDay(today());
      return json({ date: today(), rest_day: fake.planning.restDays.some((r) => r.date === today()), challenge: c ?? null, stats: stats(), suggestions: c && (c.status === "completed" || c.status === "excused") ? [] : store.suggestions });
    }
    if (path === "/api/challenges/calendar" && method === "GET") {
      const days: CalendarDay[] = Array.from({ length: 30 }, (_, i) => {
        const date = addDays(today(), i - 29);
        const c = onDay(date);
        return { date, status: c?.status ?? (fake.planning.restDays.some((r) => r.date === date) ? ("rest" as const) : "none"), project_title: c?.project?.title ?? null, challenge_id: c?.id ?? null };
      });
      return json({ start: days[0].date, end: days[29].date, days, stats: stats() });
    }
    if (path === "/api/challenges/history" && method === "GET") return json([...store.challenges].sort((a, b) => b.date.localeCompare(a.date)));
    if (path === "/api/challenges" && method === "POST") {
      const b = body as { mode: Challenge["mode"]; project_id?: number; new_project?: { title: string }; planned_task: string; estimated_minutes?: number };
      if (onDay(today())) return json({ detail: "That day already has a challenge" }, 409);
      const c = mkChallenge({
        mode: b.mode, planned_task: b.planned_task, estimated_minutes: b.estimated_minutes ?? null,
        project: { id: b.project_id ?? 77, title: b.new_project?.title ?? "RAG chatbot", repo_url: null },
      });
      store.challenges.push(c);
      return json(c, 201);
    }
    if (path === "/api/challenges/excuse" && method === "POST") {
      const b = body as { date: string; reason: string };
      let c = onDay(b.date);
      if (!c) store.challenges.push((c = mkChallenge({ date: b.date, project: null, planned_task: "No challenge was planned" })));
      Object.assign(c, { status: "excused", excuse_reason: b.reason, can_complete: false, can_edit: false });
      return json(c);
    }
    const m = path.match(/^\/api\/challenges\/(\d+)(?:\/(start|complete|verify))?$/);
    if (m) {
      const c = store.challenges.find((x) => x.id === Number(m[1]));
      if (!c) return json({ detail: "Challenge not found" }, 404);
      if (m[2] === "start" && method === "POST") return json(Object.assign(c, { status: "in_progress" }));
      if (m[2] === "verify" && method === "POST") {
        if (store.verifyOk) c.verification_status = "verified";
        return json({
          verified: store.verifyOk,
          checks: [{ name: "Commit exists", ok: true, detail: "Found it" }, { name: "Message matches", ok: store.verifyOk, detail: 'GitHub says: "other"' }],
          challenge: c,
        });
      }
      if (m[2] === "complete" && method === "POST") {
        const b = body as Record<string, unknown>;
        Object.assign(c, {
          status: "completed", implemented_summary: b.summary, repo_url: b.repo_url, commit_sha: b.commit_sha, commit_message: b.commit_message,
          actual_minutes: b.minutes, evidence_notes: b.evidence_notes ?? null, can_complete: false, can_edit: false, completed_at: new Date().toISOString(),
        });
        return json(c);
      }
      if (!m[2] && method === "DELETE") {
        store.challenges = store.challenges.filter((x) => x !== c);
        return new Response(null, { status: 204 });
      }
    }
    return undefined;
  };
  fake.handlers.push(handler);
  return store;
}
