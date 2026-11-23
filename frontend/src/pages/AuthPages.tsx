import { useState, type FormEvent, type ReactNode } from "react";
import { ApiError } from "../api/client";
import { useLogin, useSetup } from "../api/auth";

function AuthShell({ title, subtitle, children }: { title: string; subtitle: string; children: ReactNode }) {
  return (
    <div className="flex min-h-full items-center justify-center bg-gradient-to-br from-slate-50 to-brand-50 px-4 dark:from-slate-950 dark:to-slate-900 py-10">
      <div className="w-full max-w-md">
        <div className="mb-6 text-center">
          <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-brand-600 text-xl font-bold text-white shadow-lg shadow-brand-600/30">
            AI
          </div>
          <h1 className="text-2xl font-semibold tracking-tight text-slate-900 dark:text-white">{title}</h1>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">{subtitle}</p>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900">{children}</div>
      </div>
    </div>
  );
}

function Field(props: {
  label: string;
  type?: string;
  value: string;
  onChange: (v: string) => void;
  autoComplete?: string;
  hint?: string;
  required?: boolean;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">{props.label}</span>
      <input
        type={props.type ?? "text"}
        value={props.value}
        required={props.required ?? true}
        autoComplete={props.autoComplete}
        onChange={(e) => props.onChange(e.target.value)}
        className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100 transition focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20"
      />
      {props.hint && <span className="mt-1 block text-xs text-slate-500 dark:text-slate-400">{props.hint}</span>}
    </label>
  );
}

function ErrorBox({ error }: { error: unknown }) {
  if (!error) return null;
  const e = error as ApiError;
  const lockout = e.status === 429 && e.retryAfter;
  return (
    <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/50 dark:text-red-300">
      {e.message}
      {lockout ? ` (about ${Math.ceil(e.retryAfter! / 60)} min)` : ""}
    </div>
  );
}

const SubmitButton = ({ pending, children }: { pending: boolean; children: ReactNode }) => (
  <button
    type="submit"
    disabled={pending}
    className="w-full rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-60"
  >
    {pending ? "Please wait…" : children}
  </button>
);

export function SetupPage() {
  const setup = useSetup();
  const [form, setForm] = useState({
    display_name: "",
    email: "",
    password: "",
    confirm: "",
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "Asia/Kolkata",
  });
  const [mismatch, setMismatch] = useState(false);
  const set = (k: keyof typeof form) => (v: string) => setForm((f) => ({ ...f, [k]: v }));

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (form.password !== form.confirm) return setMismatch(true);
    setMismatch(false);
    const { confirm: _c, ...body } = form;
    setup.mutate(body);
  };

  return (
    <AuthShell title="Welcome — let's set up your hub" subtitle="Create the single account that owns this app.">
      <form onSubmit={submit} className="space-y-4">
        <Field label="Your name" value={form.display_name} onChange={set("display_name")} autoComplete="name" />
        <Field label="Email" type="email" value={form.email} onChange={set("email")} autoComplete="email" />
        <Field
          label="Password"
          type="password"
          value={form.password}
          onChange={set("password")}
          autoComplete="new-password"
          hint="At least 10 characters, mixing letters with numbers or symbols."
        />
        <Field
          label="Confirm password"
          type="password"
          value={form.confirm}
          onChange={set("confirm")}
          autoComplete="new-password"
        />
        <Field
          label="Timezone"
          value={form.timezone}
          onChange={set("timezone")}
          hint="Used for 'today', overdue checks and reminder times (IANA name, e.g. Asia/Kolkata)."
        />
        {mismatch && <ErrorBox error={new ApiError(0, "Passwords do not match")} />}
        <ErrorBox error={setup.error} />
        <SubmitButton pending={setup.isPending}>Create account</SubmitButton>
      </form>
    </AuthShell>
  );
}

export function LoginPage() {
  const login = useLogin();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  return (
    <AuthShell title="Welcome back" subtitle="Sign in to your learning hub.">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          login.mutate({ email, password });
        }}
        className="space-y-4"
      >
        <Field label="Email" type="email" value={email} onChange={setEmail} autoComplete="username" />
        <Field label="Password" type="password" value={password} onChange={setPassword} autoComplete="current-password" />
        <ErrorBox error={login.error} />
        <SubmitButton pending={login.isPending}>Sign in</SubmitButton>
      </form>
    </AuthShell>
  );
}
