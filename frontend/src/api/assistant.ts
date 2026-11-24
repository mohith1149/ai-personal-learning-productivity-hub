import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";

export type AiStatus = { provider: string; connected: boolean; model: string | null; live_verified: boolean; message: string };
export type AiTool = { name: string; description: string; kind: "read" | "write"; input_schema: Record<string, unknown> };
export type Memory = { id: number; kind: "preference" | "fact" | "goal"; content: string; source: "user" | "assistant"; created_at: string };
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
export const useMemories = () => useQuery({ queryKey: [...ROOT, "memories"], queryFn: () => api<Memory[]>("/ai/memories") });
export const usePending = () => useQuery({ queryKey: [...ROOT, "pending"], queryFn: () => api<Pending[]>("/ai/pending") });

function useChanging<T>(fn: (v: T) => Promise<unknown>, extra: string[] = []) {
  const qc = useQueryClient();
  return useMutation({ mutationFn: fn, onSuccess: () => Promise.all(["ai", ...extra].map((k) => qc.invalidateQueries({ queryKey: [k] }))) });
}

export const useAddMemory = () => useChanging((body: { content: string; kind: Memory["kind"] }) => api<Memory>("/ai/memories", { method: "POST", body }));
export const useDeleteMemory = () => useChanging((id: number) => api<void>(`/ai/memories/${id}`, { method: "DELETE" }));
/** An approved proposal changes real data (tasks, projects, challenges...), so those pages' cached data is refreshed too. */
export const useApprove = () => useChanging((id: number) => api<Pending>(`/ai/pending/${id}/approve`, { method: "POST" }), ["tasks", "projects", "challenges", "planner", "dashboard"]);
export const useReject = () => useChanging((id: number) => api<Pending>(`/ai/pending/${id}/reject`, { method: "POST" }));
