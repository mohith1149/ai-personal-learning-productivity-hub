import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";

export type Share = { enabled: boolean; token: string | null; path: string | null };

const KEY = ["share"] as const;

export const useShare = () => useQuery({ queryKey: KEY, queryFn: () => api<Share>("/share") });

function useShareAction<T>(fn: () => Promise<T>) {
  const qc = useQueryClient();
  return useMutation({ mutationFn: fn, onSuccess: () => qc.invalidateQueries({ queryKey: KEY }) });
}

/** The first call turns sharing on; later calls make a new link and the old one stops working. */
export const useCreateShare = () => useShareAction(() => api<Share>("/share", { method: "POST" }));
export const useStopSharing = () => useShareAction(() => api<void>("/share", { method: "DELETE" }));
