/** E-mail reminder endpoints for the fake API (installed by default, like the dashboard). Real rules are tested in pytest. */
import type { EmailRecord, NotificationSettings } from "../api/notifications";
import type { Handler } from "./fakeApi";

export type FakeNotifications = { settings: NotificationSettings; history: EmailRecord[]; testStatus: "sent" | "failed" | "skipped" };

export function newFakeNotifications(): FakeNotifications {
  return {
    settings: {
      reminder_email: "me@example.com", email_enabled: false, reminder_time: "07:00", overdue_reminders_enabled: true, overdue_reminder_time: "18:00",
      weekly_report_enabled: true, weekly_report_day: 6, weekly_report_time: "18:00", server_ready: true,
    },
    history: [],
    testStatus: "sent",
  };
}

export function notificationsHandler(store: FakeNotifications): Handler {
  return ({ method, path, body }) => {
    if (path === "/api/notifications/settings" && method === "GET") return Response.json(store.settings);
    if (path === "/api/notifications/settings" && method === "PATCH") {
      Object.assign(store.settings, body);
      return Response.json(store.settings);
    }
    if (path === "/api/notifications" && method === "GET") return Response.json(store.history);
    if (path === "/api/notifications/test" && method === "POST") {
      const ok = store.testStatus === "sent";
      const rec: EmailRecord = {
        id: store.history.length + 1, type: "test", period_key: "now", status: store.testStatus, recipient: store.settings.reminder_email, subject: "Test",
        error: ok ? null : "The mail server rejected the username or password.", attempts: 1, sent_at: ok ? "2026-12-02T01:00:00Z" : null, created_at: "2026-12-02T01:00:00Z",
      };
      store.history.unshift(rec);
      return Response.json(rec);
    }
    return undefined;
  };
}
