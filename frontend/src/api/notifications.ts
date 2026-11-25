import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";

export type NotificationSettings = {
  reminder_email: string | null;
  email_enabled: boolean;
  reminder_time: string;
  overdue_reminders_enabled: boolean;
  overdue_reminder_time: string;
  weekly_report_enabled: boolean;
  weekly_report_day: number;
  weekly_report_time: string;
  server_ready: boolean;
};
export type SettingsInput = Partial<Omit<NotificationSettings, "server_ready">>;

export type EmailRecord = {
  id: number;
  type: "daily_plan" | "overdue" | "weekly_report" | "test";
  period_key: string;
  status: "pending" | "sent" | "failed" | "skipped";
  recipient: string | null;
  subject: string | null;
  error: string | null;
  attempts: number;
  sent_at: string | null;
  created_at: string;
};

export const TYPE_LABEL: Record<EmailRecord["type"], string> = { daily_plan: "Daily plan", overdue: "Overdue reminder", weekly_report: "Weekly report", test: "Test" };
export const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

export const useNotificationSettings = () => useQuery({ queryKey: ["notifications", "settings"], queryFn: () => api<NotificationSettings>("/notifications/settings") });
export const useEmailHistory = () => useQuery({ queryKey: ["notifications", "history"], queryFn: () => api<EmailRecord[]>("/notifications") });

export function useSaveNotificationSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: SettingsInput) => api<NotificationSettings>("/notifications/settings", { method: "PATCH", body }),
    onSuccess: (data) => qc.setQueryData(["notifications", "settings"], data),
  });
}

export function useSendTestEmail() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api<EmailRecord>("/notifications/test", { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications", "history"] }),
  });
}
