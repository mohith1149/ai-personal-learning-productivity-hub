import { useState } from "react";
import { WEEKDAYS, usePreferences, useUpdatePreferences, type Preferences } from "../../api/planner";
import { FormError, TextInput } from "../../components/forms";
import { Button, Card, ErrorNotice, Spinner } from "../../components/ui";

const DEFAULT_HOURS = 4;
const toHours = (m: number) => String(Math.round((m / 60) * 100) / 100);
type Window = { from: string; to: string };
const DEFAULT_WINDOW: Window = { from: "06:00", to: "09:00" };
const toWindow = (w: string): Window => {
  const [from = "", to = ""] = w.split("-");
  return { from, to };
};

function Form({ initial }: { initial: Preferences }) {
  const save = useUpdatePreferences();
  const [warn, setWarn] = useState(initial.weekday_minutes !== null);
  const [hours, setHours] = useState<string[]>((initial.weekday_minutes ?? Array(7).fill(DEFAULT_HOURS * 60)).map(toHours));
  const [focusOn, setFocusOn] = useState(initial.focus_windows !== null);
  const [windows, setWindows] = useState<Window[]>(initial.focus_windows ? initial.focus_windows.map(toWindow) : Array(7).fill(DEFAULT_WINDOW));
  const [rest, setRest] = useState(String(initial.rest_days_per_month));
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const submit = () => {
    setError(null);
    setSaved(false);
    const restDays = Number(rest);
    if (rest.trim() === "" || !Number.isInteger(restDays) || restDays < 0 || restDays > 31) return setError("Rest days per month must be a whole number from 0 to 31.");
    let minutes: number[] | null = null;
    if (warn) {
      const parsed = hours.map((h) => Math.round(Number(h) * 60));
      if (hours.some((h) => h.trim() === "" || Number.isNaN(Number(h))) || parsed.some((m) => m < 0 || m > 1440)) return setError("Hours must be numbers from 0 to 24.");
      minutes = parsed;
    }
    let focus: string[] | null = null;
    if (focusOn) {
      for (const [i, w] of windows.entries()) {
        if (!w.from !== !w.to) return setError(`${WEEKDAYS[i]}: fill in both the start and the end of your focus hours, or leave both empty.`);
        if (w.from && w.to && w.from >= w.to) return setError(`${WEEKDAYS[i]}: your focus hours must end after they start.`);
      }
      focus = windows.map((w) => (w.from && w.to ? `${w.from}-${w.to}` : ""));
      if (focus.every((w) => w === "")) focus = null;
    }
    save.mutate({ weekday_minutes: minutes, focus_windows: focus, rest_days_per_month: restDays }, { onSuccess: () => setSaved(true) });
  };

  return (
    <form
      className="space-y-4"
      noValidate
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <fieldset className="space-y-3">
        <legend className="text-sm font-medium text-slate-800 dark:text-slate-200">Hours you have each day</legend>
        <label className="flex items-center gap-2 text-sm text-slate-800 dark:text-slate-200">
          <input
            type="checkbox"
            checked={warn}
            onChange={(e) => {
              setSaved(false);
              setWarn(e.target.checked);
            }}
            className="h-4 w-4 rounded border-slate-300"
          />
          Warn me when a day has more planned than I have time for
        </label>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {WEEKDAYS.map((d, i) => (
            <TextInput
              key={d}
              label={`${d} (hours)`}
              type="number"
              inputMode="decimal"
              min={0}
              max={24}
              step={0.25}
              disabled={!warn}
              value={hours[i]}
              onChange={(e) => {
                setSaved(false);
                setHours(hours.map((h, j) => (j === i ? e.target.value : h)));
              }}
            />
          ))}
        </div>
        <p className="text-xs text-slate-500 dark:text-slate-400">
          The planner adds up the time of what is on each day (task estimates, lesson and video lengths) and flags days that go over. Items without a time aren&apos;t guessed; the planner tells you how many were left out.
        </p>
      </fieldset>
      <fieldset className="space-y-3">
        <legend className="text-sm font-medium text-slate-800 dark:text-slate-200">Your best focus hours</legend>
        <label className="flex items-center gap-2 text-sm text-slate-800 dark:text-slate-200">
          <input
            type="checkbox"
            checked={focusOn}
            onChange={(e) => {
              setSaved(false);
              setFocusOn(e.target.checked);
            }}
            className="h-4 w-4 rounded border-slate-300"
          />
          Plan hard topics for the hours I focus best
        </label>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {WEEKDAYS.map((d, i) => (
            <div key={d} className="grid grid-cols-2 gap-2">
              {(["from", "to"] as const).map((side) => (
                <TextInput
                  key={side}
                  label={`${d} focus ${side === "from" ? "from" : "until"}`}
                  type="time"
                  disabled={!focusOn}
                  value={windows[i][side]}
                  onChange={(e) => {
                    setSaved(false);
                    setWindows(windows.map((w, j) => (j === i ? { ...w, [side]: e.target.value } : w)));
                  }}
                />
              ))}
            </div>
          ))}
        </div>
        <p className="text-xs text-slate-500 dark:text-slate-400">
          Mark topics Hard on the roadmap and the planner tells you to do them in these hours. Light topics and videos are marked as fine for a walk or the evening. Leave a day empty if you have no focus time then.
        </p>
      </fieldset>
      <div className="max-w-xs">
        <TextInput label="Rest days per month" type="number" min={0} max={31} step={1} value={rest} onChange={(e) => { setSaved(false); setRest(e.target.value); }} hint="Planned rest days keep your challenge streak alive. Set 0 to turn them off." />
      </div>
      <FormError message={error ?? save.error?.message} />
      <div className="flex items-center gap-3">
        <Button type="submit" loading={save.isPending}>
          Save planning settings
        </Button>
        {saved && (
          <span role="status" className="text-sm text-emerald-700 dark:text-emerald-400">
            Saved
          </span>
        )}
      </div>
    </form>
  );
}

export function PlanningSettings() {
  const prefs = usePreferences();
  return (
    <Card aria-label="Planning settings">
      <h2 className="mb-1 text-sm font-semibold text-slate-900 dark:text-white">Planning</h2>
      <p className="mb-3 text-sm text-slate-500 dark:text-slate-400">How much time you have, and how many rest days you allow yourself.</p>
      {prefs.isPending ? <Spinner label="Loading…" /> : prefs.isError ? <ErrorNotice error={prefs.error} onRetry={() => prefs.refetch()} /> : <Form initial={prefs.data} />}
    </Card>
  );
}
