import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";

export type User = { id: number; email: string; display_name: string; timezone: string };
export type AuthStatus = { setup_required: boolean; authenticated: boolean; user: User | null };

export const AUTH_KEY = ["auth", "status"] as const;

export function useAuthStatus() {
  return useQuery({
    queryKey: AUTH_KEY,
    queryFn: () => api<AuthStatus>("/auth/status"),
    staleTime: 30_000,
    retry: false,
  });
}

export function useSetup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { email: string; password: string; display_name: string; timezone: string }) =>
      api<User>("/auth/setup", { method: "POST", body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: AUTH_KEY }),
  });
}

export function useLogin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { email: string; password: string }) =>
      api<User>("/auth/login", { method: "POST", body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: AUTH_KEY }),
  });
}

export function useLogout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api<void>("/auth/logout", { method: "POST" }),
    onSettled: () => {
      // Drop every cached query so no data from the old session stays in memory.
      qc.clear();
      qc.invalidateQueries({ queryKey: AUTH_KEY });
    },
  });
}
