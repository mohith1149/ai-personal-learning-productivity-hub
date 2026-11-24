/** AI endpoints for the fake API. Proposals/memories are stored; approval just flips the status (what approval actually does is tested in pytest). */
import type { AiStatus, AiTool, Memory, Pending } from "../api/assistant";
import type { Fake, Handler } from "./fakeApi";

export type FakeAssistant = { status: AiStatus; tools: AiTool[]; memories: Memory[]; pending: Pending[] };

let nextId = 12000;

export function mkPending(o: Partial<Pending> = {}): Pending {
  const id = o.id ?? nextId++;
  return { id, conversation_id: 1, tool_name: "create_task", summary: `Create the task "Task ${id}"`, input: {}, status: "pending", result: null, created_at: "2026-11-24T10:00:00Z", resolved_at: null, ...o };
}

export function mkMemory(o: Partial<Memory> = {}): Memory {
  const id = o.id ?? nextId++;
  return { id, kind: "preference", content: `Note ${id}`, source: "user", created_at: "2026-11-24T10:00:00Z", ...o };
}

const schema = { type: "object", properties: {}, additionalProperties: false };
export const TOOLS: AiTool[] = [
  { name: "get_today_tasks", description: "Tasks scheduled or due today.", kind: "read", input_schema: schema },
  { name: "get_roadmap_progress", description: "Progress through the roadmap.", kind: "read", input_schema: schema },
  { name: "create_task", description: "Propose a new task.", kind: "write", input_schema: schema },
];

export function installFakeAssistant(fake: Fake, seed: Partial<FakeAssistant> = {}): FakeAssistant {
  const store: FakeAssistant = {
    status: seed.status ?? { provider: "none", connected: false, model: null, live_verified: false, message: "AI is off. Set AI_PROVIDER=anthropic and ANTHROPIC_API_KEY in backend/.env to turn it on." },
    tools: seed.tools ?? TOOLS, memories: seed.memories ?? [], pending: seed.pending ?? [],
  };
  const json = (d: unknown, status = 200) => Response.json(d, { status });
  const handler: Handler = ({ method, path, body }) => {
    if (path === "/api/ai/status") return json(store.status);
    if (path === "/api/ai/tools") return json(store.tools);
    if (path === "/api/ai/memories" && method === "GET") return json(store.memories);
    if (path === "/api/ai/memories" && method === "POST") {
      const b = body as { content: string; kind: Memory["kind"] };
      if (store.memories.some((m) => m.content.toLowerCase() === b.content.toLowerCase())) return json({ detail: "That is already remembered" }, 409);
      const m = mkMemory({ content: b.content, kind: b.kind });
      store.memories.unshift(m);
      return json(m, 201);
    }
    let m = path.match(/^\/api\/ai\/memories\/(\d+)$/);
    if (m && method === "DELETE") {
      store.memories = store.memories.filter((x) => x.id !== Number(m![1]));
      return new Response(null, { status: 204 });
    }
    if (path === "/api/ai/pending" && method === "GET") return json(store.pending.filter((p) => p.status === "pending"));
    m = path.match(/^\/api\/ai\/pending\/(\d+)\/(approve|reject)$/);
    if (m && method === "POST") {
      const p = store.pending.find((x) => x.id === Number(m![1]));
      if (!p) return json({ detail: "Proposal not found" }, 404);
      if (p.status !== "pending") return json({ detail: `This proposal was already ${p.status}` }, 409);
      p.status = m[2] === "approve" ? "executed" : "rejected";
      return json(p);
    }
    return undefined;
  };
  fake.handlers.push(handler);
  return store;
}
