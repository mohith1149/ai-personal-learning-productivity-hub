import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";

export type TopicStatus = "not_started" | "in_progress" | "completed";
export const TOPIC_STATUS_LABEL: Record<TopicStatus, string> = { not_started: "Not started", in_progress: "In progress", completed: "Completed" };

export type Topic = {
  id: number;
  stage_id: number;
  title: string;
  description: string | null;
  position: number;
  status: TopicStatus;
  notes: string | null;
  minutes_spent: number; // from logged study sessions
  study_days: number;
  last_studied_on: string | null; // YYYY-MM-DD
  completed_at: string | null;
};

export type Stage = {
  id: number;
  title: string;
  description: string | null;
  position: number;
  total: number;
  completed: number;
  in_progress: number;
  not_started: number;
  percent: number;
  minutes_spent: number;
  topics: Topic[];
};

export type Overall = { total: number; completed: number; in_progress: number; not_started: number; percent: number; minutes_spent: number };
export type Roadmap = { stages: Stage[]; overall: Overall; next_topic: Topic | null };
export type StudySession = { id: number; date: string; minutes: number; notes: string | null; created_at: string };

const ROOT = ["roadmap"] as const;

export const useRoadmap = () => useQuery({ queryKey: ROOT, queryFn: () => api<Roadmap>("/roadmap") });
export const useStudy = (topicId: number) =>
  useQuery({ queryKey: [...ROOT, "study", topicId], queryFn: () => api<StudySession[]>(`/roadmap/topics/${topicId}/study`) });

function useInvalidating<TVars, TData>(fn: (v: TVars) => Promise<TData>) {
  const qc = useQueryClient();
  return useMutation({ mutationFn: fn, onSuccess: () => qc.invalidateQueries({ queryKey: ROOT }) });
}

export const useSetTopicStatus = () =>
  useInvalidating(({ id, status }: { id: number; status: TopicStatus }) => api<Topic>(`/roadmap/topics/${id}/status`, { method: "POST", body: { status } }));
export const useUpdateTopic = () =>
  useInvalidating(({ id, body }: { id: number; body: { title?: string; description?: string | null; notes?: string | null } }) =>
    api<Topic>(`/roadmap/topics/${id}`, { method: "PATCH", body }));
export const useAddTopic = () =>
  useInvalidating((body: { stage_id: number; title: string; description?: string | null }) => api<Topic>("/roadmap/topics", { method: "POST", body }));
export const useDeleteTopic = () => useInvalidating((id: number) => api<void>(`/roadmap/topics/${id}`, { method: "DELETE" }));
export const useLogStudy = () =>
  useInvalidating(({ topicId, body }: { topicId: number; body: { minutes: number; date?: string; notes?: string | null } }) =>
    api<StudySession>(`/roadmap/topics/${topicId}/study`, { method: "POST", body }));
export const useDeleteStudy = () => useInvalidating((id: number) => api<void>(`/learning-sessions/${id}`, { method: "DELETE" }));
