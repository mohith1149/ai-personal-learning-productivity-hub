import { Play, Square, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useDiscardTimer, useStartTimer, useStopTimer, useTimer, type Logged, type RunningTimer, type TimerKind } from "../api/timer";
import { FormError, TextArea, TextInput } from "./forms";
import { Modal } from "./Modal";
import { Button, cx } from "./ui";

/** Seconds as H:MM:SS (or M:SS under an hour). */
export function clock(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const two = (n: number) => String(n).padStart(2, "0");
  return h > 0 ? `${h}:${two(m)}:${two(sec)}` : `${m}:${two(sec)}`;
}

/** Elapsed seconds that keep counting on screen. The server's figure is the anchor, so a wrong clock on this computer doesn't matter. */
function useElapsed(timer: RunningTimer | null | undefined, anchoredAt: number): number {
  const [, tick] = useState(0);
  useEffect(() => {
    if (!timer) return;
    const id = window.setInterval(() => tick((n) => n + 1), 1000);
    return () => window.clearInterval(id);
  }, [timer]);
  return timer ? timer.elapsed_seconds + Math.max(0, (Date.now() - anchoredAt) / 1000) : 0;
}

function StopModal({ timer, elapsed, onClose }: { timer: RunningTimer; elapsed: number; onClose: () => void }) {
  const stop = useStopTimer();
  const guess = Math.max(1, Math.round(elapsed / 60));
  const tooLong = guess > 1440;
  const [minutes, setMinutes] = useState(tooLong ? "" : String(guess));
  const [summary, setSummary] = useState("");
  const [logged, setLogged] = useState<Logged | null>(null);
  const [error, setError] = useState<string | null>(null);
  const toProject = timer.project_id !== null;

  const submit = () => {
    setError(null);
    const n = Number(minutes);
    if (minutes.trim() === "" || !Number.isInteger(n) || n < 1 || n > 1440) return setError("Minutes must be a whole number from 1 to 1440.");
    if (summary.trim() !== "" && summary.trim().length < 3) return setError("Say briefly what you did (at least 3 characters), or leave it empty.");
    stop.mutate({ minutes: n, summary: summary.trim() || undefined }, { onSuccess: setLogged });
  };

  if (logged) {
    return (
      <Modal title="Time logged" onClose={onClose}>
        <div className="space-y-4">
          <p role="status" className="text-sm text-slate-700 dark:text-slate-300">
            Logged <strong>{logged.minutes} min</strong> on {logged.label}
            {logged.logged_to === "project" ? " (project)" : logged.logged_to === "course" ? " (course study time)" : logged.logged_to === "topic" ? " (roadmap topic)" : " (the task's actual time)"}.
          </p>
          <div className="flex justify-end">
            <Button onClick={onClose}>Close</Button>
          </div>
        </div>
      </Modal>
    );
  }

  return (
    <Modal title={`Stop the timer: ${timer.label}`} onClose={onClose}>
      <form
        className="space-y-4"
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <p className="text-sm text-slate-700 dark:text-slate-300">
          {tooLong ? "This timer has been running for more than 24 hours, so enter the minutes you actually worked." : `Running for ${clock(elapsed)}. Change the minutes if you forgot to stop it.`}
          {timer.logs_to ? ` It will be logged to ${timer.logs_to.toLowerCase()}.` : " It will be added to the task's actual time."}
        </p>
        <TextInput label="Minutes to log" type="number" min={1} max={1440} step={1} value={minutes} onChange={(e) => setMinutes(e.target.value)} />
        {toProject && (
          <TextArea label="What did you do? (optional)" rows={2} value={summary} onChange={(e) => setSummary(e.target.value)} hint={`Leave it empty to save "Worked on ${timer.label}".`} />
        )}
        <FormError message={error ?? stop.error?.message} />
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Keep running
          </Button>
          <Button type="submit" icon={Square} loading={stop.isPending}>
            Stop and log
          </Button>
        </div>
      </form>
    </Modal>
  );
}

/** Shown under the header on every page while a timer runs. */
export function TimerBar() {
  const q = useTimer();
  const discard = useDiscardTimer();
  const [stopping, setStopping] = useState(false);
  const timer = q.data ?? null;
  const elapsed = useElapsed(timer, q.dataUpdatedAt);
  if (!timer) return null;
  return (
    <div role="region" aria-label="Running timer" className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-brand-200 bg-brand-50 px-4 py-2 sm:px-6 dark:border-brand-900 dark:bg-brand-950/40">
      <span className="relative flex h-2.5 w-2.5" aria-hidden>
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-brand-500 opacity-60 motion-reduce:animate-none" />
        <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-brand-600" />
      </span>
      <span className="min-w-0 flex-1 truncate text-sm font-medium text-slate-900 dark:text-white">{timer.label}</span>
      {timer.logs_to && <span className="hidden text-xs text-slate-600 sm:inline dark:text-slate-400">{timer.logs_to}</span>}
      <span className="text-sm font-semibold tabular-nums text-brand-700 dark:text-brand-300" aria-label="Elapsed time">
        {clock(elapsed)}
      </span>
      <Button icon={Square} onClick={() => setStopping(true)} className="px-2.5 py-1.5">
        Stop and log
      </Button>
      <Button variant="ghost" icon={Trash2} loading={discard.isPending} onClick={() => discard.mutate()} aria-label="Discard the timer without logging" className="px-2.5 py-1.5">
        Discard
      </Button>
      {discard.error && (
        <span role="alert" className="text-sm text-red-600 dark:text-red-400">
          {discard.error.message}
        </span>
      )}
      {stopping && <StopModal timer={timer} elapsed={elapsed} onClose={() => setStopping(false)} />}
    </div>
  );
}

/** A small "Start timer" button for any item. Only one timer can run, so it is disabled (with the reason) while another one does. */
export function StartTimerButton({ kind, id, label, className }: { kind: TimerKind; id: number; label: string; className?: string }) {
  const running = useTimer();
  const start = useStartTimer();
  const busy = !!running.data;
  return (
    <>
      <Button
        variant="ghost"
        icon={Play}
        loading={start.isPending}
        disabled={busy}
        title={busy ? "A timer is already running. Stop it first." : "Start a timer; the time is logged when you stop it"}
        onClick={() => start.mutate({ kind, ref_id: id })}
        aria-label={`Start timer for ${label}`}
        className={cx("px-2.5 py-1.5", className)}
      >
        Timer
      </Button>
      {start.error && (
        <span role="alert" className="text-xs text-red-600 dark:text-red-400">
          {start.error.message}
        </span>
      )}
    </>
  );
}
