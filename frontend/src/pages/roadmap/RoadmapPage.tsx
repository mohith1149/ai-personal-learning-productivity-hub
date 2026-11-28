import { Map as MapIcon, NotebookPen, Plus, Timer, Trash2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useAuthStatus } from "../../api/auth";
import {
  DIFFICULTY_LABEL,
  TOPIC_STATUS_LABEL,
  useAddTopic,
  useDeleteStudy,
  useDeleteTopic,
  useLogStudy,
  useRoadmap,
  useSetTopicStatus,
  useStudy,
  useUpdateTopic,
  type Stage,
  type Difficulty,
  type Topic,
  type TopicStatus,
} from "../../api/roadmap";
import { FormError, TextArea, TextInput, controlClass } from "../../components/forms";
import { ConfirmDialog, Modal } from "../../components/Modal";
import { StartTimerButton } from "../../components/Timer";
import { Button, Card, ErrorNotice, PageHeader, ProgressBar, Spinner, cx } from "../../components/ui";
import { formatDay, todayIn } from "../../lib/dates";

const STATUSES: TopicStatus[] = ["not_started", "in_progress", "completed"];
const DIFFICULTIES: Difficulty[] = ["hard", "normal", "light"];

/** 95 -> "1h 35m", 40 -> "40m", 0 -> "0m" */
export function formatMinutes(m: number): string {
  const h = Math.floor(m / 60);
  return h > 0 ? `${h}h ${m % 60}m` : `${m}m`;
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <dt className="text-xs text-slate-500 dark:text-slate-400">{label}</dt>
      <dd className="text-lg font-semibold tabular-nums text-slate-900 dark:text-white">{value}</dd>
    </div>
  );
}

/* ---------------------------------- modals ---------------------------------- */

function StudyModal({ topic, today, onClose }: { topic: Topic; today: string; onClose: () => void }) {
  const log = useLogStudy();
  const sessions = useStudy(topic.id);
  const del = useDeleteStudy();
  const [minutes, setMinutes] = useState("30");
  const [date, setDate] = useState(today);
  const [notes, setNotes] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setLocalError(null);
    const n = Number(minutes);
    if (!Number.isInteger(n) || n < 1 || n > 1440) return setLocalError("Minutes must be a whole number from 1 to 1440.");
    if (date > today) return setLocalError("You can't log study time in the future.");
    log.mutate({ topicId: topic.id, body: { minutes: n, date, notes: notes.trim() || null } }, { onSuccess: () => setNotes("") });
  };

  return (
    <Modal title={`Study time: ${topic.title}`} onClose={onClose}>
      <form onSubmit={submit} className="space-y-3" noValidate>
        <div className="grid grid-cols-2 gap-3">
          <TextInput label="Minutes studied" type="number" min={1} max={1440} value={minutes} onChange={(e) => setMinutes(e.target.value)} />
          <TextInput label="Date" type="date" max={today} value={date} onChange={(e) => setDate(e.target.value)} />
        </div>
        <TextArea label="What did you cover? (optional)" rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />
        <FormError message={localError ?? log.error?.message} />
        <div className="flex justify-end">
          <Button type="submit" loading={log.isPending}>
            Log study time
          </Button>
        </div>
      </form>
      <h3 className="mb-1 mt-5 text-sm font-semibold text-slate-900 dark:text-white">History</h3>
      {sessions.isPending ? (
        <Spinner label="Loading history…" />
      ) : sessions.isError ? (
        <ErrorNotice error={sessions.error} onRetry={() => sessions.refetch()} />
      ) : sessions.data.length === 0 ? (
        <p className="text-sm text-slate-500 dark:text-slate-400">No study time logged yet.</p>
      ) : (
        <ul aria-label="Study history" className="divide-y divide-slate-100 dark:divide-slate-800">
          {sessions.data.map((s) => (
            <li key={s.id} className="flex items-center justify-between gap-2 py-1.5 text-sm">
              <span className="text-slate-700 dark:text-slate-300">
                {formatDay(s.date, today)} · {formatMinutes(s.minutes)}
                {s.notes && <span className="text-slate-500 dark:text-slate-400"> · {s.notes}</span>}
              </span>
              <button
                onClick={() => del.mutate(s.id)}
                aria-label={`Delete ${formatMinutes(s.minutes)} session on ${s.date}`}
                className="rounded p-1 text-slate-400 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950/40"
              >
                <Trash2 className="h-4 w-4" aria-hidden />
              </button>
            </li>
          ))}
        </ul>
      )}
      <FormError message={del.error?.message} />
    </Modal>
  );
}

function NotesModal({ topic, onClose }: { topic: Topic; onClose: () => void }) {
  const update = useUpdateTopic();
  const [notes, setNotes] = useState(topic.notes ?? "");
  return (
    <Modal title={`Notes: ${topic.title}`} onClose={onClose}>
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          update.mutate({ id: topic.id, body: { notes: notes.trim() || null } }, { onSuccess: onClose });
        }}
      >
        <TextArea label="Notes" rows={6} value={notes} onChange={(e) => setNotes(e.target.value)} />
        <FormError message={update.error?.message} />
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={update.isPending}>
            Save notes
          </Button>
        </div>
      </form>
    </Modal>
  );
}

function AddTopicModal({ stage, onClose }: { stage: Stage; onClose: () => void }) {
  const add = useAddTopic();
  const [title, setTitle] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);
  return (
    <Modal title={`Add a topic to ${stage.title}`} onClose={onClose}>
      <form
        className="space-y-4"
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          setLocalError(null);
          if (!title.trim()) return setLocalError("Please give the topic a name.");
          add.mutate({ stage_id: stage.id, title: title.trim() }, { onSuccess: onClose });
        }}
      >
        <TextInput label="Topic" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} />
        <FormError message={localError ?? add.error?.message} />
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={add.isPending}>
            Add topic
          </Button>
        </div>
      </form>
    </Modal>
  );
}

/* ---------------------------------- topic row ---------------------------------- */

function TopicRow({ topic, today, timeZone }: { topic: Topic; today: string; timeZone: string }) {
  const setStatus = useSetTopicStatus();
  const setDifficulty = useUpdateTopic();
  const del = useDeleteTopic();
  const [study, setStudy] = useState(false);
  const [notes, setNotes] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const done = topic.status === "completed";
  const completedOn = topic.completed_at ? formatDay(todayIn(timeZone, new Date(topic.completed_at)), today) : null;

  return (
    <li className="py-3">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <div className="min-w-0 flex-1">
          <p className={cx("text-sm font-medium", done ? "text-slate-500 line-through dark:text-slate-500" : "text-slate-900 dark:text-white")}>{topic.title}</p>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            {topic.minutes_spent > 0 ? `${formatMinutes(topic.minutes_spent)} over ${topic.study_days} day${topic.study_days === 1 ? "" : "s"}` : "No study time logged"}
            {topic.last_studied_on && <> · last studied {formatDay(topic.last_studied_on, today)}</>}
            {completedOn && <> · completed {completedOn}</>}
          </p>
          {topic.notes && <p className="mt-0.5 line-clamp-2 text-xs italic text-slate-600 dark:text-slate-400">Note: {topic.notes}</p>}
        </div>
        <select
          aria-label={`Status of ${topic.title}`}
          value={topic.status}
          disabled={setStatus.isPending}
          onChange={(e) => setStatus.mutate({ id: topic.id, status: e.target.value as TopicStatus })}
          className={cx("w-36 py-1 text-xs", controlClass)}
        >
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {TOPIC_STATUS_LABEL[s]}
            </option>
          ))}
        </select>
        <select
          aria-label={`Difficulty of ${topic.title}`}
          title="Hard topics are planned for your best focus hours; light ones suit a walk or the evening"
          value={topic.difficulty}
          disabled={setDifficulty.isPending}
          onChange={(e) => setDifficulty.mutate({ id: topic.id, body: { difficulty: e.target.value as Difficulty } })}
          className={cx("w-24 py-1 text-xs", controlClass)}
        >
          {DIFFICULTIES.map((d) => (
            <option key={d} value={d}>
              {DIFFICULTY_LABEL[d]}
            </option>
          ))}
        </select>
        <div className="flex items-center">
          {!done && <StartTimerButton kind="topic" id={topic.id} label={topic.title} className="py-1" />}
          <button onClick={() => setStudy(true)} aria-label={`Log study time for ${topic.title}`} title="Log study time" className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 hover:text-slate-800 dark:hover:bg-slate-800">
            <Timer className="h-4 w-4" aria-hidden />
          </button>
          <button onClick={() => setNotes(true)} aria-label={`Notes for ${topic.title}`} title="Notes" className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 hover:text-slate-800 dark:hover:bg-slate-800">
            <NotebookPen className="h-4 w-4" aria-hidden />
          </button>
          <button onClick={() => setConfirm(true)} aria-label={`Delete ${topic.title}`} title="Delete topic" className="rounded-lg p-1.5 text-slate-500 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950/40">
            <Trash2 className="h-4 w-4" aria-hidden />
          </button>
        </div>
      </div>
      {setDifficulty.error && (
        <p role="alert" className="mt-1 text-sm text-red-600 dark:text-red-400">
          {setDifficulty.error.message}
        </p>
      )}
      {setStatus.error && (
        <p role="alert" className="mt-1 text-sm text-red-600 dark:text-red-400">
          {setStatus.error.message}
        </p>
      )}
      {study && <StudyModal topic={topic} today={today} onClose={() => setStudy(false)} />}
      {notes && <NotesModal topic={topic} onClose={() => setNotes(false)} />}
      {confirm && (
        <ConfirmDialog
          title="Delete topic?"
          message={
            <>
              <strong>{topic.title}</strong> and its notes will be deleted. Study time you logged stays in your history.
            </>
          }
          busy={del.isPending}
          error={del.error?.message}
          onCancel={() => {
            setConfirm(false);
            del.reset();
          }}
          onConfirm={() => del.mutate(topic.id, { onSuccess: () => setConfirm(false) })}
        />
      )}
    </li>
  );
}

/* ---------------------------------- page ---------------------------------- */

export function RoadmapPage() {
  const roadmap = useRoadmap();
  const user = useAuthStatus().data?.user;
  const timeZone = user?.timezone ?? "UTC";
  const today = todayIn(timeZone);
  const [adding, setAdding] = useState<Stage | null>(null);

  return (
    <>
      <PageHeader
        title="AI roadmap"
        description="Five stages from programming foundations to AI engineering. A topic is only completed when you mark it; logging study time never completes it."
      />
      {roadmap.isPending ? (
        <Spinner label="Loading roadmap…" />
      ) : roadmap.isError ? (
        <ErrorNotice error={roadmap.error} onRetry={() => roadmap.refetch()} />
      ) : (
        <div className="space-y-4">
          <Card aria-label="Overall roadmap progress">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-900 dark:text-white">
                <MapIcon className="h-4 w-4" aria-hidden /> Overall progress
              </h2>
              <span className="text-sm tabular-nums text-slate-600 dark:text-slate-300">{roadmap.data.overall.percent}%</span>
            </div>
            <div className="mt-2">
              <ProgressBar percent={roadmap.data.overall.percent} label="Overall roadmap progress" />
            </div>
            <dl className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-5">
              <Stat label="Topics" value={roadmap.data.overall.total} />
              <Stat label="Completed" value={roadmap.data.overall.completed} />
              <Stat label="In progress" value={roadmap.data.overall.in_progress} />
              <Stat label="Not started" value={roadmap.data.overall.not_started} />
              <Stat label="Study time" value={formatMinutes(roadmap.data.overall.minutes_spent)} />
            </dl>
            {roadmap.data.next_topic ? (
              <p className="mt-3 text-sm text-slate-600 dark:text-slate-300">
                Next up: <strong>{roadmap.data.next_topic.title}</strong>
              </p>
            ) : (
              <p className="mt-3 text-sm text-emerald-700 dark:text-emerald-400">Every topic is completed.</p>
            )}
          </Card>

          {roadmap.data.stages.map((stage) => (
            <Card key={stage.id} aria-label={stage.title}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-base font-semibold text-slate-900 dark:text-white">{stage.title}</h2>
                <Button variant="secondary" icon={Plus} onClick={() => setAdding(stage)} aria-label={`Add topic to ${stage.title}`}>
                  Add topic
                </Button>
              </div>
              <div className="mt-3">
                <ProgressBar percent={stage.percent} label={`${stage.title} progress`} />
                <div className="mt-1.5 flex flex-wrap justify-between gap-2 text-xs text-slate-500 dark:text-slate-400">
                  <span>
                    {stage.completed} of {stage.total} completed · {stage.in_progress} in progress · {formatMinutes(stage.minutes_spent)} studied
                  </span>
                  <span className="tabular-nums">{stage.percent}%</span>
                </div>
              </div>
              <ul aria-label={`${stage.title} topics`} className="mt-2 divide-y divide-slate-100 dark:divide-slate-800">
                {stage.topics.map((t) => (
                  <TopicRow key={t.id} topic={t} today={today} timeZone={timeZone} />
                ))}
              </ul>
            </Card>
          ))}
        </div>
      )}
      {adding && <AddTopicModal stage={adding} onClose={() => setAdding(null)} />}
    </>
  );
}
