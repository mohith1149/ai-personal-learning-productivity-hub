/** AI endpoints for the fake API. Proposals are stored; approval just flips the status (what approval actually does is tested in pytest). */
import type { AiStatus, AiTool, Autofill, ChatMessage, ModelOptions, Pending } from "../api/assistant";
import type { Fake, Handler } from "./fakeApi";

export type FakeAssistant = {
  status: AiStatus; tools: AiTool[]; pending: Pending[]; models: ModelOptions;
  messages: ChatMessage[]; chatReply: string; chatProposals: number; autofill: Autofill; autofillError: string | null;
};

let nextId = 12000;

export function mkPending(o: Partial<Pending> = {}): Pending {
  const id = o.id ?? nextId++;
  return { id, conversation_id: 1, tool_name: "create_task", summary: `Create the task "Task ${id}"`, input: {}, status: "pending", result: null, created_at: "2026-11-24T10:00:00Z", resolved_at: null, ...o };
}

const schema = { type: "object", properties: {}, additionalProperties: false };
export const TOOLS: AiTool[] = [
  { name: "get_today_tasks", description: "Tasks scheduled or due today.", kind: "read", input_schema: schema },
  { name: "get_roadmap_progress", description: "Progress through the roadmap.", kind: "read", input_schema: schema },
  { name: "create_task", description: "Propose a new task.", kind: "write", input_schema: schema },
];

export function installFakeAssistant(fake: Fake, seed: Partial<FakeAssistant> = {}): FakeAssistant {
  const store: FakeAssistant = {
    status: seed.status ?? { provider: "none", connected: false, model: null, live_verified: false, message: "AI is off. Set AI_PROVIDER=groq and GROQ_API_KEY in backend/.env to turn it on (Groq has a free tier)." },
    tools: seed.tools ?? TOOLS, pending: seed.pending ?? [],
    models: seed.models ?? { default_provider: "groq", providers: [
      { provider: "groq", label: "Groq (free)", default_model: "llama-3.3-70b-versatile", models: ["llama-3.3-70b-versatile", "openai/gpt-oss-20b"] },
      { provider: "gemini", label: "Google Gemini (free tier)", default_model: "gemini-3.5-flash", models: ["gemini-3.5-flash"] },
    ] },
    messages: seed.messages ?? [], chatReply: seed.chatReply ?? "You have 2 open tasks today.", chatProposals: seed.chatProposals ?? 0,
    autofill: seed.autofill ?? { title: "RAG Bot", description: "A chatbot over my docs.", objective: "Learn retrieval.", tech_stack: ["Python", "FastAPI"], milestones: ["Load documents", "Build the index"],
                                 repo_url: "https://github.com/me/rag-bot", start_date: "2025-03-04", source: "repo", readme_used: true },
    autofillError: seed.autofillError ?? null,
  };
  const json = (d: unknown, status = 200) => Response.json(d, { status });
  const handler: Handler = ({ method, path, body }) => {
    if (path === "/api/ai/status") return json(store.status);
    if (path === "/api/ai/tools") return json(store.tools);
    if (path === "/api/ai/models") return json(store.models);
    if (path === "/api/ai/check" && method === "POST") return json({ ok: true, provider: "groq", model: (body as { model?: string } | undefined)?.model ?? "llama-3.3-70b-versatile", message: "The provider answered. The connection works." });
    if (path === "/api/ai/project-autofill" && method === "POST") return store.autofillError ? json({ detail: store.autofillError }, 422) : json(store.autofill);
    if (path === "/api/ai/chat" && method === "POST") {
      const b = body as { message: string };
      const base = store.messages.length;
      store.messages.push({ id: base + 1, role: "user", text: b.message, tool_calls: [], created_at: "2026-11-25T10:00:00Z" });
      store.messages.push({ id: base + 2, role: "assistant", text: store.chatReply, tool_calls: [{ name: "get_today_tasks", input: {} }], created_at: "2026-11-25T10:00:01Z" });
      const made = Array.from({ length: store.chatProposals }, () => mkPending());
      store.pending.push(...made);
      return json({ conversation_id: 1, reply: store.chatReply, pending: made });
    }
    if (path === "/api/ai/conversations/1" && method === "GET") return json({ id: 1, title: "chat", messages: store.messages, pending: [] });
    if (path === "/api/ai/pending" && method === "GET") return json(store.pending.filter((p) => p.status === "pending"));
    const m = path.match(/^\/api\/ai\/pending\/(\d+)\/(approve|reject)$/);
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
