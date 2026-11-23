import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";
import { cx } from "./ui";

const CONTROL =
  "rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none transition " +
  "placeholder:text-slate-400 focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20 disabled:cursor-not-allowed disabled:opacity-60 " +
  "dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100";

export function FormField({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  // The <label> wraps the control, so clicking the text focuses it and screen readers announce the pairing.
  return (
    <label className="block">
      <span className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-slate-500 dark:text-slate-400">{hint}</span>}
    </label>
  );
}

export function TextInput({ label, hint, className, ...rest }: InputHTMLAttributes<HTMLInputElement> & { label: string; hint?: string }) {
  return (
    <FormField label={label} hint={hint}>
      <input {...rest} className={cx("w-full", CONTROL, className)} />
    </FormField>
  );
}

export function TextArea({ label, hint, className, ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement> & { label: string; hint?: string }) {
  return (
    <FormField label={label} hint={hint}>
      <textarea rows={3} {...rest} className={cx("w-full", CONTROL, className)} />
    </FormField>
  );
}

export function SelectInput({
  label,
  hint,
  className,
  children,
  ...rest
}: SelectHTMLAttributes<HTMLSelectElement> & { label: string; hint?: string }) {
  return (
    <FormField label={label} hint={hint}>
      <select {...rest} className={cx("w-full", CONTROL, className)}>
        {children}
      </select>
    </FormField>
  );
}

/** Base look for bare (label-less) controls in toolbars; the caller chooses the width. aria-label is mandatory. */
export const controlClass = CONTROL;

export function FormError({ message }: { message?: string | null }) {
  if (!message) return null;
  return (
    <div
      role="alert"
      className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/50 dark:text-red-300"
    >
      {message}
    </div>
  );
}
