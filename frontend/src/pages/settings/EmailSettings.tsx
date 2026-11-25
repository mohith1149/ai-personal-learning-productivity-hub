import { useState } from "react";
import { DAYS, TYPE_LABEL, useEmailHistory, useNotificationSettings, useSaveNotificationSettings, useSendTestEmail, type NotificationSettings, type SettingsInput } from "../../api/notifications";
import { FormError, SelectInput, TextInput } from "../../components/forms";
import { Badge, Button, Card, ErrorNotice, Spinner } from "../../components/ui";

const STATUS_TEXT = { sent: "Sent", failed: "Failed", skipped: "Not sent", pending: "Pending" } as const;

function Check({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex items-center gap-2 text-sm text-slate-800 dark:text-slate-200">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="h-4 w-4 rounded border-slate-300" />
      {label}
    </label>
  );
}

function Form({ initial }: { initial: NotificationSettings }) {
  const save = useSaveNotificationSettings();
  const test = useSendTestEmail();
  const { server_ready, ...start } = initial;
  const [f, setF] = useState<Required<SettingsInput>>(start);
  const [saved, setSaved] = useState(false);
  const edit = (patch: SettingsInput) => {
    setSaved(false);
    setF({ ...f, ...patch });
  };

  return (
    <form
      className="space-y-3"
      noValidate
      onSubmit={(e) => {
        e.preventDefault();
        setSaved(false);
        save.mutate(f, { onSuccess: () => setSaved(true) });
      }}
    >
      {!server_ready && (
        <p role="status" className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-300">
          The server has no e-mail account yet, so nothing can be sent. Set EMAIL_PROVIDER=smtp and the SMTP settings in backend/.env, then restart it.
        </p>
      )}
      <Check label="Send me e-mail reminders" checked={f.email_enabled} onChange={(v) => edit({ email_enabled: v })} />
      <TextInput label="Send to" type="email" value={f.reminder_email ?? ""} onChange={(e) => edit({ reminder_email: e.target.value })} />
      <div className="grid gap-3 sm:grid-cols-2">
        <TextInput label="Daily plan at" type="time" value={f.reminder_time} onChange={(e) => edit({ reminder_time: e.target.value })} />
        <TextInput label="Overdue reminder at" type="time" value={f.overdue_reminder_time} disabled={!f.overdue_reminders_enabled} onChange={(e) => edit({ overdue_reminder_time: e.target.value })} />
      </div>
      <Check label="Send the evening overdue reminder" checked={f.overdue_reminders_enabled} onChange={(v) => edit({ overdue_reminders_enabled: v })} />
      <Check label="Send a weekly report" checked={f.weekly_report_enabled} onChange={(v) => edit({ weekly_report_enabled: v })} />
      <div className="grid gap-3 sm:grid-cols-2">
        <SelectInput label="Weekly report day" value={String(f.weekly_report_day)} disabled={!f.weekly_report_enabled} onChange={(e) => edit({ weekly_report_day: Number(e.target.value) })}>
          {DAYS.map((d, i) => (
            <option key={d} value={i}>
              {d}
            </option>
          ))}
        </SelectInput>
        <TextInput label="Weekly report at" type="time" value={f.weekly_report_time} disabled={!f.weekly_report_enabled} onChange={(e) => edit({ weekly_report_time: e.target.value })} />
      </div>
      <FormError message={save.error?.message} />
      <div className="flex flex-wrap items-center gap-2">
        <Button type="submit" loading={save.isPending}>
          Save reminders
        </Button>
        <Button type="button" variant="secondary" loading={test.isPending} onClick={() => test.mutate()}>
          Send a test e-mail
        </Button>
        {saved && (
          <span role="status" className="text-sm text-emerald-700 dark:text-emerald-400">
            Saved.
          </span>
        )}
      </div>
      {test.data && (
        <p role="status" className={test.data.status === "sent" ? "text-sm text-emerald-700 dark:text-emerald-400" : "text-sm text-red-700 dark:text-red-400"}>
          {test.data.status === "sent" ? `Test e-mail sent to ${test.data.recipient}.` : `The test e-mail was not sent. ${test.data.error ?? ""}`}
        </p>
      )}
      {test.error && <FormError message={test.error.message} />}
    </form>
  );
}

export function EmailSettings() {
  const q = useNotificationSettings();
  const history = useEmailHistory();
  return (
    <Card aria-label="E-mail reminders">
      <h2 className="mb-1 text-sm font-semibold text-slate-900 dark:text-white">E-mail reminders</h2>
      <p className="mb-3 text-sm text-slate-600 dark:text-slate-400">A morning plan, an evening nudge for what is still open, and a weekly report. Times are in your timezone.</p>
      {q.isLoading && <Spinner />}
      {q.error && <ErrorNotice error={q.error} onRetry={() => q.refetch()} />}
      {q.data && <Form initial={q.data} />}
      {history.data && history.data.length > 0 && (
        <div className="mt-4 border-t border-slate-100 pt-3 dark:border-slate-800">
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Recent e-mails</h3>
          <ul aria-label="Recent e-mails" className="space-y-1.5 text-sm">
            {history.data.slice(0, 8).map((r) => (
              <li key={r.id} className="flex flex-wrap items-center gap-2">
                <Badge tone={r.status === "sent" ? "brand" : "neutral"}>{STATUS_TEXT[r.status]}</Badge>
                <span className="text-slate-800 dark:text-slate-200">{TYPE_LABEL[r.type]}</span>
                <span className="text-slate-500 dark:text-slate-400">{r.type === "test" ? (r.sent_at ?? r.created_at).slice(0, 10) : r.period_key}</span>
                {r.error && <span className="text-xs text-slate-500 dark:text-slate-400">{r.error}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
}
