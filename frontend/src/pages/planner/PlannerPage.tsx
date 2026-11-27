import { CalendarClock, Check, ChevronLeft, ChevronRight, ExternalLink, EyeOff, MessageCircleQuestion, RotateCcw, Undo2 } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useAuthStatus } from "../../api/auth";
import {
  KIND_LABEL,
  useCompleteItem,
  useExcuse,
  usePlan,
  useReopenItem,
  useReschedule,
  useUnexcuse,
  type DayPlan,
  type ItemStatus,
  type PlanItem,
} from "../../api/planner";
import { FormError, TextArea, TextInput } from "../../components/forms";
import { GoalsCard } from "../../components/Goals";
import { StartTimerButton } from "../../components/Timer";
import { Modal } from "../../components/Modal";
import { Badge, Button, Card, EmptyState, ErrorNotice, PageHeader, ProgressBar, Spinner, cx } from "../../components/ui";
import { LoadNotice, RestDayCard, RollOverButton, formatMinutes } from "./PlanningPanel";
import { addDays, formatDay, todayIn } from "../../lib/dates";

const SECTIONS: { status: ItemStatus; title: string }[] = [
  { status: "overdue", title: "Overdue" },
  { status: "pending", title: "To do" },
  { status: "completed", title: "Completed" },
  { status: "excused", title: "Excused" },
];

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <dt className="text-xs text-slate-500 dark:text-slate-400">{label}</dt>
      <dd className="text-lg font-semibold tabular-nums text-slate-900 dark:text-white">{value}</dd>
    </div>
  );
}

function RescheduleModal({ item, day, today, onClose }: { item: PlanItem; day: string; today: string; onClose: () => void }) {
  const move = useReschedule();
  const [date, setDate] = useState(addDays(today, 1));
  const [moveDue, setMoveDue] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  return (
    <Modal title={`Reschedule: ${item.title}`} onClose={onClose}>
      <form
        className="space-y-4"
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          setLocalError(null);
          if (!date) return setLocalError("Choose a day.");
          if (date < today) return setLocalError("A task can't be moved into the past.");
          move.mutate({ taskId: item.ref_id, date, from_date: day, move_due_date: moveDue }, { onSuccess: onClose });
        }}
      >
        <TextInput label="New day" type="date" min={today} value={date} onChange={(e) => setDate(e.target.value)} />
        {item.due_date && (
          <label className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300">
            <input type="checkbox" checked={moveDue} onChange={(e) => setMoveDue(e.target.checked)} />
            Also move the deadline (currently {item.due_date})
          </label>
        )}
        <p className="text-xs text-slate-500 dark:text-slate-400">Moving a task does not complete it.</p>
        <FormError message={localError ?? move.error?.message} />
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={move.isPending}>
            Reschedule
          </Button>
        </div>
      </form>
    </Modal>
  );
}

function ExcuseModal({ item, day, onClose }: { item: PlanItem; day: string; onClose: () => void }) {
  const excuse = useExcuse();
  const [reason, setReason] = useState(item.excuse_reason ?? "");
  const [localError, setLocalError] = useState<string | null>(null);
  return (
    <Modal title={`Excuse: ${item.title}`} onClose={onClose}>
      <form
        className="space-y-4"
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          setLocalError(null);
          if (reason.trim().length < 3) return setLocalError("Give a reason (at least a few words).");
          excuse.mutate({ kind: item.kind, ref_id: item.ref_id, date: day, reason: reason.trim() }, { onSuccess: onClose });
        }}
      >
        <TextArea label="Why is it being skipped today?" rows={3} value={reason} onChange={(e) => setReason(e.target.value)} hint="Excused activities aren't counted as missed. The activity itself isn't changed." />
        <FormError message={localError ?? excuse.error?.message} />
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={excuse.isPending}>
            Excuse for this day
          </Button>
        </div>
      </form>
    </Modal>
  );
}

function ItemRow({ item, day, today, restDay }: { item: PlanItem; day: string; today: string; restDay: boolean }) {
  const complete = useCompleteItem();
  const reopen = useReopenItem();
  const unexcuse = useUnexcuse();
  const [moving, setMoving] = useState(false);
  const [excusing, setExcusing] = useState(false);
  const ref = { kind: item.kind, ref_id: item.ref_id, date: day };
  const done = item.status === "completed";
  const error = complete.error ?? reopen.error ?? unexcuse.error;

  return (
    <li className="py-3">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <Badge tone={item.kind === "task" ? "neutral" : "brand"}>{KIND_LABEL[item.kind]}</Badge>
        {item.slipping && <Badge tone="warn">Slipping: moved {item.carry_count}×</Badge>}
        <div className="min-w-0 flex-1">
          <p className={cx("text-sm font-medium", done || item.status === "excused" ? "text-slate-500 line-through dark:text-slate-500" : "text-slate-900 dark:text-white")}>
            <Link to={item.link} className="hover:underline">
              {item.title}
            </Link>
          </p>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            {item.subtitle}
            {item.due_date && <>{item.subtitle ? " · " : ""}due {formatDay(item.due_date, today)}</>}
            {item.minutes ? <>{item.subtitle || item.due_date ? " · " : ""}~{formatMinutes(item.minutes)}</> : null}
          </p>
          {item.slipping && item.status !== "completed" && (
            <p className="text-xs text-amber-800 dark:text-amber-300">
              <Link
                to={`/assistant?ask=${encodeURIComponent(`Why does "${item.title}" keep slipping? I've moved it ${item.carry_count} times.`)}`}
                className="inline-flex items-center gap-1 font-medium hover:underline"
              >
                <MessageCircleQuestion className="h-3.5 w-3.5" aria-hidden /> Ask the assistant why
              </Link>
            </p>
          )}
          {item.status === "excused" && <p className="text-xs italic text-slate-500 dark:text-slate-400">Excused: {item.excuse_reason}</p>}
        </div>
        <div className="flex flex-wrap items-center gap-1">
          {item.url && (
            <a href={item.url} target="_blank" rel="noreferrer noopener" aria-label={`Open ${item.title}`} className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-sm text-brand-600 hover:underline dark:text-brand-400">
              Open <ExternalLink className="h-3.5 w-3.5" aria-hidden />
            </a>
          )}
          {item.kind === "project" && item.status !== "completed" && (
            <Link to={item.link} className="rounded-lg px-2 py-1 text-sm text-brand-600 hover:underline dark:text-brand-400">
              Log a session
            </Link>
          )}
          {!done && item.status !== "excused" && (item.kind === "task" || item.kind === "lesson" || item.kind === "topic" || item.kind === "project") && (
            <StartTimerButton kind={item.kind} id={item.ref_id} label={item.title} />
          )}
          {item.can_complete && !done && (
            <Button icon={Check} loading={complete.isPending} onClick={() => complete.mutate(ref)} aria-label={`Complete ${item.title}`} className="px-2.5 py-1.5">
              Done
            </Button>
          )}
          {item.can_complete && done && (
            <Button variant="secondary" icon={RotateCcw} loading={reopen.isPending} onClick={() => reopen.mutate(ref)} aria-label={`Reopen ${item.title}`} className="px-2.5 py-1.5">
              Reopen
            </Button>
          )}
          {item.can_reschedule && (
            <Button variant="ghost" icon={CalendarClock} onClick={() => setMoving(true)} aria-label={`Reschedule ${item.title}`} className="px-2.5 py-1.5">
              Reschedule
            </Button>
          )}
          {item.status === "excused" ? (
            restDay && item.excuse_reason === "Rest day" ? null : <Button variant="ghost" icon={Undo2} loading={unexcuse.isPending} onClick={() => unexcuse.mutate(ref)} aria-label={`Remove excuse for ${item.title}`} className="px-2.5 py-1.5">
              Remove excuse
            </Button>
          ) : (
            item.can_excuse && (
              <Button variant="ghost" icon={EyeOff} onClick={() => setExcusing(true)} aria-label={`Excuse ${item.title}`} className="px-2.5 py-1.5">
                Excuse
              </Button>
            )
          )}
        </div>
      </div>
      {error && (
        <p role="alert" className="mt-1 text-sm text-red-600 dark:text-red-400">
          {error.message}
        </p>
      )}
      {moving && <RescheduleModal item={item} day={day} today={today} onClose={() => setMoving(false)} />}
      {excusing && <ExcuseModal item={item} day={day} onClose={() => setExcusing(false)} />}
    </li>
  );
}

function Summary({ plan }: { plan: DayPlan }) {
  const s = plan.summary;
  return (
    <Card aria-label="Day summary">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <h2 className="text-sm font-semibold text-slate-900 dark:text-white">{plan.is_today ? "Today's progress" : "Progress"}</h2>
        <span className="text-sm tabular-nums text-slate-600 dark:text-slate-300">{s.percent}%</span>
      </div>
      <div className="mt-2">
        <ProgressBar percent={s.percent} label="Day progress" />
      </div>
      <dl className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <Stat label="Completed" value={`${s.completed}/${s.total}`} />
        <Stat label="To do" value={s.pending} />
        <Stat label="Overdue" value={s.overdue} />
        <Stat label="Excused" value={s.excused} />
        <Stat label="Study time" value={formatMinutes(s.study_minutes)} />
        <Stat label="Project time" value={formatMinutes(s.dev_minutes)} />
      </dl>
      {s.by_kind.length > 0 && (
        <ul aria-label="Progress by type" className="mt-3 flex flex-wrap gap-1.5">
          {s.by_kind.map((k) => (
            <li key={k.kind}>
              <Badge>
                {KIND_LABEL[k.kind]}s {k.completed}/{k.total}
              </Badge>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

export function PlannerPage() {
  const tz = useAuthStatus().data?.user?.timezone ?? "UTC";
  const today = todayIn(tz);
  const [day, setDay] = useState<string | null>(null);
  const current = day ?? today;
  const plan = usePlan(current);

  const go = (d: string) => setDay(d === today ? null : d);

  return (
    <>
      <PageHeader
        title="Daily planner"
        description="Everything for the day in one list: tasks and deadlines, lessons, videos, roadmap topics, habits and project work. Completing something here completes it in its own page."
      />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Button variant="secondary" icon={ChevronLeft} onClick={() => go(addDays(current, -1))} aria-label="Previous day">
          Previous
        </Button>
        <Button variant="secondary" onClick={() => go(today)} disabled={current === today}>
          Today
        </Button>
        <Button variant="secondary" onClick={() => go(addDays(current, 1))} aria-label="Next day">
          Next <ChevronRight className="h-4 w-4" aria-hidden />
        </Button>
        <TextInput label="Go to day" type="date" value={current} onChange={(e) => e.target.value && go(e.target.value)} className="w-44" />
        <h2 className="ml-2 text-lg font-semibold text-slate-900 dark:text-white" aria-live="polite">
          {formatDay(current, today)} <span className="text-sm font-normal text-slate-500 dark:text-slate-400">{current}</span>
        </h2>
      </div>

      {plan.isPending ? (
        <Spinner label="Loading the plan…" />
      ) : plan.isError ? (
        <ErrorNotice error={plan.error} onRetry={() => plan.refetch()} />
      ) : (
        <div className="space-y-4">
          <Summary plan={plan.data} />
          <RestDayCard plan={plan.data} day={current} today={today} />
          <LoadNotice plan={plan.data} />
          <RollOverButton plan={plan.data} day={current} today={today} />
          {current === today && <GoalsCard />}
          {current > today && <p className="text-sm text-slate-500 dark:text-slate-400">Future days only show tasks scheduled for them. Lessons, videos and habits are suggested on the day itself.</p>}
          {plan.data.items.length === 0 ? (
            <EmptyState icon={CalendarClock} title="Nothing planned for this day">
              {plan.data.is_today ? "No tasks, lessons, videos, topics, habits or projects are due. Add some on their pages." : "Nothing was scheduled or completed on this day."}
            </EmptyState>
          ) : (
            SECTIONS.map(({ status, title }) => {
              const items = plan.data.items.filter((i) => i.status === status);
              if (items.length === 0) return null;
              return (
                <Card key={status} aria-label={title}>
                  <h2 className="text-sm font-semibold text-slate-900 dark:text-white">
                    {title} <span className="font-normal text-slate-500 dark:text-slate-400">({items.length})</span>
                  </h2>
                  <ul aria-label={`${title} activities`} className="mt-1 divide-y divide-slate-100 dark:divide-slate-800">
                    {items.map((i) => (
                      <ItemRow key={i.key} item={i} day={current} today={today} restDay={plan.data.summary.rest_day} />
                    ))}
                  </ul>
                </Card>
              );
            })
          )}
        </div>
      )}
    </>
  );
}
