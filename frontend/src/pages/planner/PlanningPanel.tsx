import { AlertTriangle, ArrowRightCircle, BedDouble, Undo2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useAddRestDay, useRemoveRestDay, useRestMonth, useRollOver, type DayPlan, type RollOver } from "../../api/planner";
import { FormError, TextInput } from "../../components/forms";
import { Modal } from "../../components/Modal";
import { Badge, Button, Card, Spinner, cx } from "../../components/ui";
import { addDays, formatDay } from "../../lib/dates";

export const formatMinutes = (m: number) => (m >= 60 ? `${Math.floor(m / 60)}h${m % 60 ? ` ${m % 60}m` : ""}` : `${m}m`);
const monthName = (month: string) => new Date(`${month}-01T12:00:00`).toLocaleDateString("en-GB", { month: "long" });

/** A rest day can be set for today, the last 3 days or later. The server enforces the limit; this just tells you where you stand. */
const BACK_DAYS = 3;

function RestDayModal({ day, month, onClose }: { day: string; month: string; onClose: () => void }) {
  const usage = useRestMonth(month);
  const add = useAddRestDay();
  const [reason, setReason] = useState("");
  const left = usage.data?.left;
  return (
    <Modal title={`Take a rest day: ${day}`} onClose={onClose}>
      <form
        className="space-y-4"
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          add.mutate({ date: day, reason: reason.trim() || undefined }, { onSuccess: onClose });
        }}
      >
        <p className="text-sm text-slate-700 dark:text-slate-300">
          A rest day keeps your streak alive and nothing on it counts as overdue or missed. You can still do things that day and they still count.
        </p>
        {usage.data && (
          <p className="text-sm text-slate-600 dark:text-slate-400" aria-live="polite">
            {usage.data.used} of {usage.data.cap} rest days used in {monthName(month)}
            {left === 0 ? ". None left: change the limit in Settings, or excuse the day on the Challenge page with a reason." : `, ${left} left.`}
          </p>
        )}
        <TextInput label="Reason (optional)" value={reason} maxLength={200} onChange={(e) => setReason(e.target.value)} placeholder="Sick, travelling, …" />
        <FormError message={add.error?.message} />
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={add.isPending} disabled={left === 0}>
            Take the rest day
          </Button>
        </div>
      </form>
    </Modal>
  );
}

export function RestDayCard({ plan, day, today }: { plan: DayPlan; day: string; today: string }) {
  const month = day.slice(0, 7);
  const usage = useRestMonth(month);
  const remove = useRemoveRestDay();
  const [open, setOpen] = useState(false);
  const isRest = plan.summary.rest_day;
  if (!isRest && day < addDays(today, -BACK_DAYS)) return null;

  if (isRest) {
    return (
      <Card aria-label="Rest day" className="border-sky-200 bg-sky-50 dark:border-sky-900 dark:bg-sky-950/40">
        <div className="flex flex-wrap items-center gap-3">
          <BedDouble className="h-5 w-5 text-sky-700 dark:text-sky-300" aria-hidden />
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold text-sky-900 dark:text-sky-200">Rest day</p>
            <p className="text-sm text-sky-800 dark:text-sky-300">
              {usage.data?.days.find((d) => d.date === day)?.reason ?? "Taking it easy."} Your streak is safe and nothing here counts as overdue.
              {usage.data && ` ${usage.data.used} of ${usage.data.cap} rest days used in ${monthName(month)}.`}
            </p>
          </div>
          <Button variant="secondary" icon={Undo2} loading={remove.isPending} onClick={() => remove.mutate(day)}>
            Cancel rest day
          </Button>
        </div>
        <FormError message={remove.error?.message} />
      </Card>
    );
  }
  const none = usage.data?.left === 0;
  return (
    <div className="flex flex-wrap items-center gap-3">
      <Button variant="secondary" icon={BedDouble} onClick={() => setOpen(true)} disabled={none}>
        Take a rest day
      </Button>
      {usage.data && (
        <span className="text-xs text-slate-500 dark:text-slate-400">
          {none ? `No rest days left in ${monthName(month)}` : `${usage.data.left} of ${usage.data.cap} rest days left in ${monthName(month)}`}
        </span>
      )}
      {open && <RestDayModal day={day} month={month} onClose={() => setOpen(false)} />}
    </div>
  );
}

/** Planned time against the hours you have. Warns when a day asks for more; never guesses a time for items that have none. */
export function LoadNotice({ plan }: { plan: DayPlan }) {
  const s = plan.summary;
  if (s.rest_day || (s.planned_minutes === 0 && s.available_minutes === null && s.unestimated === 0)) return null;
  const over = s.available_minutes !== null ? s.planned_minutes - s.available_minutes : 0;
  return (
    <Card aria-label="Time planned" className={cx(s.overloaded && "border-amber-300 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/40")}>
      {s.overloaded ? (
        <div role="status" className="flex items-start gap-3">
          <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-700 dark:text-amber-300" aria-hidden />
          <div>
            <p className="text-sm font-semibold text-amber-900 dark:text-amber-200">Overloaded: {formatMinutes(over)} more than you have</p>
            <p className="text-sm text-amber-800 dark:text-amber-300">
              {formatMinutes(s.planned_minutes)} planned, {formatMinutes(s.available_minutes ?? 0)} available. Move something to another day, or excuse what can wait.
            </p>
          </div>
        </div>
      ) : (
        <p className="text-sm text-slate-700 dark:text-slate-300">
          Planned about <strong className="tabular-nums">{formatMinutes(s.planned_minutes)}</strong>
          {s.available_minutes !== null ? (
            <>
              {" "}
              of <span className="tabular-nums">{formatMinutes(s.available_minutes)}</span> available.
            </>
          ) : (
            <>
              . <Link to="/settings" className="text-brand-600 hover:underline dark:text-brand-400">Set the hours you have each day</Link> to be warned about overloaded days.
            </>
          )}
        </p>
      )}
      {s.unestimated > 0 && (
        <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
          {s.unestimated} open {s.unestimated === 1 ? "item has" : "items have"} no time estimate, so {s.unestimated === 1 ? "it isn't" : "they aren't"} counted.
        </p>
      )}
    </Card>
  );
}

function TomorrowLine({ t }: { t: RollOver["tomorrow"] }) {
  if (t.rest_day) return <p className="text-sm text-slate-700 dark:text-slate-300">Tomorrow is a rest day.</p>;
  return (
    <p className={cx("text-sm", t.overloaded ? "font-medium text-amber-800 dark:text-amber-300" : "text-slate-700 dark:text-slate-300")} role={t.overloaded ? "alert" : undefined}>
      {t.overloaded && <AlertTriangle className="mr-1 inline h-4 w-4" aria-hidden />}
      Tomorrow would have about {formatMinutes(t.planned_minutes)} planned
      {t.available_minutes !== null ? ` of ${formatMinutes(t.available_minutes)} available${t.overloaded ? ": that is too much. Move something further out afterwards." : "."}` : "."}
      {t.unestimated > 0 && ` (${t.unestimated} without a time estimate.)`}
    </p>
  );
}

function RollOverModal({ today, onClose }: { today: string; onClose: () => void }) {
  const roll = useRollOver();
  const [preview, setPreview] = useState<RollOver | null>(null);
  const [result, setResult] = useState<RollOver | null>(null);
  const { mutate } = roll;
  useEffect(() => {
    mutate({ dry_run: true }, { onSuccess: setPreview });
  }, [mutate]);
  const shown = result ?? preview;
  return (
    <Modal title="Move unfinished tasks to tomorrow" onClose={onClose}>
      <div className="space-y-4">
        {!shown && !roll.isError && <Spinner label="Checking tomorrow…" />}
        <FormError message={roll.error?.message} />
        {shown && (
          <>
            {shown.moved.length === 0 ? (
              <p className="text-sm text-slate-700 dark:text-slate-300">Nothing to move: every open task is already planned for later.</p>
            ) : (
              <>
                <p className="text-sm text-slate-700 dark:text-slate-300">
                  {result ? "Moved" : "These"} {shown.moved.length} {shown.moved.length === 1 ? "task" : "tasks"} {result ? "to" : "will move to"} {formatDay(shown.tomorrow.date, today)}. Moving a task does not complete it.
                </p>
                <ul aria-label="Tasks to move" className="divide-y divide-slate-100 rounded-lg border border-slate-200 dark:divide-slate-800 dark:border-slate-800">
                  {shown.moved.map((m) => (
                    <li key={m.task_id} className="flex flex-wrap items-center gap-2 px-3 py-2 text-sm">
                      <span className="min-w-0 flex-1 text-slate-900 dark:text-white">{m.title}</span>
                      {m.minutes ? <span className="text-xs text-slate-500 dark:text-slate-400">~{formatMinutes(m.minutes)}</span> : null}
                      <Badge tone={m.slipping ? "warn" : "neutral"}>{m.slipping ? `Slipping: moved ${m.carry_count}×` : `moved ${m.carry_count}×`}</Badge>
                    </li>
                  ))}
                </ul>
                <TomorrowLine t={shown.tomorrow} />
              </>
            )}
            <div className="flex justify-end gap-2">
              <Button variant="secondary" onClick={onClose}>
                {result ? "Close" : "Cancel"}
              </Button>
              {!result && shown.moved.length > 0 && (
                <Button icon={ArrowRightCircle} loading={roll.isPending} onClick={() => roll.mutate({ dry_run: false, task_ids: shown.moved.map((m) => m.task_id) }, { onSuccess: setResult })}>
                  Move {shown.moved.length === 1 ? "it" : `all ${shown.moved.length}`}
                </Button>
              )}
            </div>
          </>
        )}
      </div>
    </Modal>
  );
}

/** Only on today's plan: end-of-day clean-up for whatever is still open. */
export function RollOverButton({ plan, day, today }: { plan: DayPlan; day: string; today: string }) {
  const [open, setOpen] = useState(false);
  const openTasks = plan.items.filter((i) => i.kind === "task" && (i.status === "pending" || i.status === "overdue")).length;
  if (day !== today || openTasks === 0 || plan.summary.rest_day) return null;
  return (
    <>
      <Button variant="secondary" icon={ArrowRightCircle} onClick={() => setOpen(true)}>
        Move unfinished to tomorrow ({openTasks})
      </Button>
      {open && <RollOverModal today={today} onClose={() => setOpen(false)} />}
    </>
  );
}
