import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSyncExternalStore } from "react";
import { api } from "./client";

export type AiStatus = { provider: string; connected: boolean; model: string | null; live_verified: boolean; message: string };
export type AiTool = { name: string; description: string; kind: "read" | "write"; input_schema: Record<string, unknown> };
export type Pending = {
  id: number;
  conversation_id: number;
  tool_name: string;
  summary: string;
  input: Record<string, unknown>;
  status: "pending" | "approved" | "rejected" | "executed" | "failed";
  result: unknown;
  created_at: string;
  resolved_at: string | null;
};

const ROOT = ["ai"] as const;

export const useAiStatus = () => useQuery({ queryKey: [...ROOT, "status"], queryFn: () => api<AiStatus>("/ai/status") });
export const useAiTools = () => useQuery({ queryKey: [...ROOT, "tools"], queryFn: () => api<AiTool[]>("/ai/tools") });
export const usePending = () => useQuery({ queryKey: [...ROOT, "pending"], queryFn: () => api<Pending[]>("/ai/pending") });

function useChanging<T, R = unknown>(fn: (v: T) => Promise<R>, extra: string[] = []) {
  const qc = useQueryClient();
  return useMutation({ mutationFn: fn, onSuccess: () => Promise.all(["ai", ...extra].map((k) => qc.invalidateQueries({ queryKey: [k] }))) });
}

/** An approved proposal changes real data (tasks, projects, challenges...), so those pages' cached data is refreshed too. */
export const useApprove = () => useChanging((id: number) => api<Pending>(`/ai/pending/${id}/approve`, { method: "POST" }), ["tasks", "projects", "challenges", "planner", "dashboard"]);
export const useReject = () => useChanging((id: number) => api<Pending>(`/ai/pending/${id}/reject`, { method: "POST" }));

export type ChatMessage = { id: number; role: "user" | "assistant"; text: string; tool_calls: { name: string; input: Record<string, unknown> }[]; created_at: string };
export type Conversation = { id: number; title: string; messages: ChatMessage[]; pending: Pending[] };
export type ChatReply = { conversation_id: number; reply: string; pending: Pending[] };
export type CheckResult = { ok: boolean; provider: string; model: string; message: string };
export type Autofill = {
  title: string;
  description: string | null;
  objective: string | null;
  tech_stack: string[];
  milestones: string[];
  repo_url: string | null;
  start_date: string | null;
  source: "repo" | "description" | "repo_and_description";
  readme_used: boolean;
};

export const useConversation = (id: number | null) =>
  useQuery({ queryKey: [...ROOT, "conversation", id], queryFn: () => api<Conversation>(`/ai/conversations/${id}`), enabled: id !== null });

/** A chat turn can propose changes, so the approval queue is refreshed too (everything under "ai" is invalidated). */
export const useChat = () =>
  useChanging(({ message, conversation_id }: { message: string; conversation_id: number | null }) =>
    api<ChatReply>("/ai/chat", { method: "POST", body: { message, conversation_id, ...currentChoice() } }),
  );

export const useCheckConnection = () => useMutation({ mutationFn: () => api<CheckResult>("/ai/check", { method: "POST", body: currentChoice() }) });

/** Suggests project fields. Saves nothing. */
export const useAutofill = () =>
  useMutation({ mutationFn: (body: { repo_url?: string; description?: string }) => api<Autofill>("/ai/project-autofill", { method: "POST", body: { ...body, ...currentChoice() } }) });

// ---------------------------------------------------------------- the model menu

export type ModelProvider = { provider: string; label: string; default_model: string; models: string[] };
export type ModelOptions = { default_provider: string | null; providers: ModelProvider[] };
export type ModelChoice = { provider: string; model: string };

export const useModels = () => useQuery({ queryKey: [...ROOT, "models"], queryFn: () => api<ModelOptions>("/ai/models"), staleTime: 5 * 60_000 });

/** The pick is remembered in this browser only. It is sent with each chat, test and autofill request; no pick = the default from backend/.env. */
const KEY = "hub.ai-model";
const listeners = new Set<() => void>();
const read = (): string => {
  try {
    return localStorage.getItem(KEY) ?? "";
  } catch {
    return "";
  }
};
const parse = (raw: string): ModelChoice | null => {
  try {
    const v = JSON.parse(raw) as Partial<ModelChoice>;
    return typeof v?.provider === "string" && typeof v?.model === "string" ? { provider: v.provider, model: v.model } : null;
  } catch {
    return null;
  }
};

export function currentChoice(): Partial<ModelChoice> {
  return parse(read()) ?? {};
}

export function setModelChoice(choice: ModelChoice | null) {
  try {
    if (choice) localStorage.setItem(KEY, JSON.stringify(choice));
    else localStorage.removeItem(KEY);
  } catch {
    /* storage blocked: the pick just isn't remembered */
  }
  listeners.forEach((l) => l());
}

export function useModelChoice(): ModelChoice | null {
  const raw = useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    read,
  );
  return parse(raw);
}
