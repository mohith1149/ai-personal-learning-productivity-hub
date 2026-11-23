import { ArrowLeft, ChevronDown, ChevronUp, ClipboardPaste, ExternalLink, Pencil, Play, Plus, Trash2, Check } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useAuthStatus } from "../../api/auth";
import { ApiError } from "../../api/client";
import {
  useCourse,
  useDeleteCourse,
  useDeleteLesson,
  useDeleteModule,
  useLessonAction,
  useMoveLesson,
  useMoveModule,
  useUpdateCourse,
  type CourseDetail,
  type Lesson,
  type Module,
} from "../../api/courses";
import { ConfirmDialog } from "../../components/Modal";
import { Badge, Button, Card, ErrorNotice, ProgressBar, Spinner, StatusBadge, cx } from "../../components/ui";
import { formatDay, todayIn } from "../../lib/dates";
import { CourseForm } from "./CourseForm";
import { CourseStatusBadge } from "./CoursesPage";
import { BulkLessonsModal, LessonModal, ModuleModal } from "./LessonForms";
import { SessionModal, StudyLog } from "./StudyLog";

type Confirm = { kind: "lesson"; lesson: Lesson } | { kind: "module"; module: Module } | { kind: "course" };

function IconButton({ label, onClick, disabled, danger, children }: { label: string; onClick: () => void; disabled?: boolean; danger?: boolean; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      title={label}
      className={cx(
        "rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 disabled:opacity-30 dark:hover:bg-slate-800",
        danger ? "hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950/40" : "hover:text-slate-800 dark:hover:text-slate-200",
      )}
    >
      {children}
    </button>
  );
}

export function CourseDetailPage() {
  const { courseId } = useParams();
  const id = Number(courseId);
  const user = useAuthStatus().data?.user;
  const timeZone = user?.timezone ?? "UTC";
  const today = todayIn(timeZone);
  const navigate = useNavigate();

  const course = useCourse(id);
  const lessonAction = useLessonAction();
  const updateCourse = useUpdateCourse();
  const delLesson = useDeleteLesson();
  const delModule = useDeleteModule();
  const delCourse = useDeleteCourse();
  const moveModule = useMoveModule();
  const moveLesson = useMoveLesson();

  const [editingCourse, setEditingCourse] = useState(false);
  const [moduleModal, setModuleModal] = useState<Module | "new" | null>(null);
  const [lessonModal, setLessonModal] = useState<{ moduleId: number; lesson: Lesson | null } | null>(null);
  const [bulkFor, setBulkFor] = useState<Module | null>(null);
  const [logging, setLogging] = useState(false);
  const [confirm, setConfirm] = useState<Confirm | null>(null);

  if (course.isPending) return <Spinner label="Loading course…" />;
  if (course.isError) {
    const notFound = course.error instanceof ApiError && course.error.status === 404;
    return (
      <div>
        <Link to="/courses" className="mb-4 inline-flex items-center gap-1 text-sm text-brand-600 hover:underline dark:text-brand-400">
          <ArrowLeft className="h-4 w-4" aria-hidden /> Back to courses
        </Link>
        {notFound ? <p className="text-slate-600 dark:text-slate-300">Course not found.</p> : <ErrorNotice error={course.error} onRetry={() => course.refetch()} />}
      </div>
    );
  }

  const c: CourseDetail = course.data;
  const p = c.progress;
  const lastStudied = c.last_studied_at ? formatDay(todayIn(timeZone, new Date(c.last_studied_at)), today) : null;
  const actionError = lessonAction.error ?? updateCourse.error ?? moveModule.error ?? moveLesson.error;
  const setStatus = (status: "active" | "paused" | "archived") => updateCourse.mutate({ id: c.id, body: { status } });
  const toggle = (l: Lesson) => lessonAction.mutate({ id: l.id, action: l.status === "completed" ? "uncomplete" : "complete" });
  const busyLesson = lessonAction.isPending ? lessonAction.variables?.id : undefined;

  const doConfirm = () => {
    if (!confirm) return;
    const done = () => setConfirm(null);
    if (confirm.kind === "lesson") delLesson.mutate(confirm.lesson.id, { onSuccess: done });
    else if (confirm.kind === "module") delModule.mutate(confirm.module.id, { onSuccess: done });
    else delCourse.mutate(c.id, { onSuccess: () => navigate("/courses") });
  };
  const confirmBusy = delLesson.isPending || delModule.isPending || delCourse.isPending;
  const confirmError = (delLesson.error ?? delModule.error ?? delCourse.error)?.message;
  const cancelConfirm = () => {
    delLesson.reset();
    delModule.reset();
    delCourse.reset();
    setConfirm(null);
  };

  return (
    <>
      <Link to="/courses" className="mb-4 inline-flex items-center gap-1 text-sm text-brand-600 hover:underline dark:text-brand-400">
        <ArrowLeft className="h-4 w-4" aria-hidden /> Back to courses
      </Link>

      <header className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight text-slate-900 dark:text-white">{c.title}</h1>
            <CourseStatusBadge status={c.status} />
          </div>
          <p className="mt-1 flex flex-wrap items-center gap-x-3 text-sm text-slate-500 dark:text-slate-400">
            {c.provider && <span>{c.provider}</span>}
            {c.url && (
              <a href={c.url} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1 text-brand-600 hover:underline dark:text-brand-400">
                Course page <ExternalLink className="h-3.5 w-3.5" aria-hidden />
              </a>
            )}
            {c.target_date && <span>Target: {formatDay(c.target_date, today)}</span>}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" icon={Pencil} onClick={() => setEditingCourse(true)}>
            Edit
          </Button>
          {c.status === "active" && <Button variant="secondary" onClick={() => setStatus("paused")}>Pause</Button>}
          {c.status === "paused" && <Button variant="secondary" onClick={() => setStatus("active")}>Resume</Button>}
          {(c.status === "active" || c.status === "paused" || c.status === "completed") && (
            <Button variant="secondary" onClick={() => setStatus("archived")}>Archive</Button>
          )}
          {c.status === "archived" && <Button variant="secondary" onClick={() => setStatus("active")}>Restore</Button>}
          <Button variant="secondary" icon={Trash2} onClick={() => setConfirm({ kind: "course" })} aria-label="Delete course">
            Delete
          </Button>
        </div>
      </header>

      {actionError && <div className="mb-4"><ErrorNotice error={actionError} /></div>}

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <div className="flex items-baseline justify-between">
            <h2 className="text-sm font-semibold text-slate-900 dark:text-white">Progress</h2>
            <span className="text-2xl font-semibold tabular-nums text-slate-900 dark:text-white">{p.percent}%</span>
          </div>
          <div className="mt-2">
            <ProgressBar percent={p.percent} label="Course progress" />
          </div>
          <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
            {p.total_lessons === 0 ? "No lessons added yet. Add or paste lessons to start tracking." : `${p.completed_lessons} of ${p.total_lessons} lessons completed`}
          </p>
          {p.empty_modules > 0 && p.total_lessons > 0 && (
            <p role="note" className="mt-2 text-xs text-amber-700 dark:text-amber-400">
              {p.empty_modules} module{p.empty_modules === 1 ? " has" : "s have"} no lessons yet, so the course can't be marked complete. Add
              lessons to {p.empty_modules === 1 ? "it" : "them"}, or delete {p.empty_modules === 1 ? "it" : "them"} if you won't take {p.empty_modules === 1 ? "it" : "them"}.
            </p>
          )}
          <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-xs text-slate-500 dark:text-slate-400">
            {p.remaining_minutes > 0 && <span>~{p.remaining_minutes} min of lessons left</span>}
            {c.minutes_studied > 0 && <span>{c.minutes_studied} min studied</span>}
            {lastStudied && <span>Last studied {lastStudied}</span>}
            {c.status === "completed" && c.completed_at && <span>Completed {formatDay(todayIn(timeZone, new Date(c.completed_at)), today)}</span>}
          </div>
        </Card>

        <Card aria-label="Up next">
          <h2 className="text-sm font-semibold text-slate-900 dark:text-white">Up next</h2>
          {c.next_lesson ? (
            <div className="mt-2">
              <p className="text-sm font-medium text-slate-900 dark:text-white">{c.next_lesson.title}</p>
              <p className="text-xs text-slate-500 dark:text-slate-400">{c.next_lesson.module_title}</p>
              <div className="mt-3 flex flex-wrap gap-2">
                {c.next_lesson.status === "not_started" && (
                  <Button variant="secondary" icon={Play} onClick={() => lessonAction.mutate({ id: c.next_lesson!.id, action: "start" })}>
                    Start
                  </Button>
                )}
                <Button icon={Check} onClick={() => lessonAction.mutate({ id: c.next_lesson!.id, action: "complete" })}>
                  Mark complete
                </Button>
                {c.next_lesson.url && (
                  <a href={c.next_lesson.url} target="_blank" rel="noreferrer noopener">
                    <Button variant="ghost" icon={ExternalLink}>Open</Button>
                  </a>
                )}
              </div>
            </div>
          ) : (
            <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
              {p.total_lessons === 0
                ? "Add lessons to see what's next."
                : p.empty_modules > 0
                  ? `All the lessons you've added are done, but ${p.empty_modules} module${p.empty_modules === 1 ? " still has" : "s still have"} no lessons.`
                  : "Every lesson is completed."}
            </p>
          )}
        </Card>
      </div>

      {c.description && <p className="mt-4 text-sm text-slate-600 dark:text-slate-300">{c.description}</p>}
      {c.notes && (
        <Card className="mt-4">
          <h2 className="mb-1 text-sm font-semibold text-slate-900 dark:text-white">Notes</h2>
          <p className="whitespace-pre-wrap text-sm text-slate-600 dark:text-slate-300">{c.notes}</p>
        </Card>
      )}

      <div className="mt-6 mb-2 flex items-center justify-between">
        <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Modules</h2>
        <Button icon={Plus} variant="secondary" onClick={() => setModuleModal("new")}>
          Add module
        </Button>
      </div>

      {c.modules.length === 0 ? (
        <Card>
          <p className="text-sm text-slate-500 dark:text-slate-400">No modules yet. Add a module, then add or paste its lessons.</p>
        </Card>
      ) : (
        <ul className="space-y-3" aria-label="Modules">
          {c.modules.map((m, mi) => (
            <li key={m.id}>
              <Card className="p-0">
                <div className="flex flex-wrap items-center gap-2 border-b border-slate-100 px-4 py-3 dark:border-slate-800">
                  <h3 className="min-w-0 flex-1 truncate text-sm font-semibold text-slate-900 dark:text-white">{m.title}</h3>
                  <span className="text-xs tabular-nums text-slate-500 dark:text-slate-400">
                    {m.completed_lessons}/{m.total_lessons}
                  </span>
                  <IconButton label={`Move module "${m.title}" up`} disabled={mi === 0} onClick={() => moveModule.mutate({ id: m.id, direction: "up" })}>
                    <ChevronUp className="h-4 w-4" aria-hidden />
                  </IconButton>
                  <IconButton label={`Move module "${m.title}" down`} disabled={mi === c.modules.length - 1} onClick={() => moveModule.mutate({ id: m.id, direction: "down" })}>
                    <ChevronDown className="h-4 w-4" aria-hidden />
                  </IconButton>
                  <IconButton label={`Rename module "${m.title}"`} onClick={() => setModuleModal(m)}>
                    <Pencil className="h-4 w-4" aria-hidden />
                  </IconButton>
                  <IconButton label={`Delete module "${m.title}"`} danger onClick={() => setConfirm({ kind: "module", module: m })}>
                    <Trash2 className="h-4 w-4" aria-hidden />
                  </IconButton>
                </div>

                {m.lessons.length > 0 && (
                  <ul className="divide-y divide-slate-100 dark:divide-slate-800" aria-label={`Lessons in ${m.title}`}>
                    {m.lessons.map((l, li) => {
                      const done = l.status === "completed";
                      return (
                        <li key={l.id} className="flex items-center gap-3 px-4 py-2.5">
                          <button
                            role="checkbox"
                            aria-checked={done}
                            aria-label={done ? `Mark "${l.title}" as not done` : `Mark "${l.title}" as done`}
                            disabled={busyLesson === l.id}
                            onClick={() => toggle(l)}
                            className={cx(
                              "flex h-5 w-5 shrink-0 items-center justify-center rounded-md border transition disabled:opacity-50",
                              done ? "border-emerald-600 bg-emerald-600 text-white" : "border-slate-300 hover:border-brand-500 dark:border-slate-600",
                            )}
                          >
                            {done && <Check className="h-3.5 w-3.5" aria-hidden />}
                          </button>
                          <div className="min-w-0 flex-1">
                            {l.url ? (
                              <a
                                href={l.url}
                                target="_blank"
                                rel="noreferrer noopener"
                                className={cx("text-sm hover:underline", done ? "text-slate-400 line-through dark:text-slate-500" : "text-slate-900 dark:text-slate-100")}
                              >
                                {l.title}
                              </a>
                            ) : (
                              <span className={cx("text-sm", done ? "text-slate-400 line-through dark:text-slate-500" : "text-slate-900 dark:text-slate-100")}>{l.title}</span>
                            )}
                            <div className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
                              {l.status === "in_progress" && <StatusBadge status="in_progress" />}
                              {l.lesson_type === "video" && <Badge>Video</Badge>}
                              {l.duration_minutes && <span>{l.duration_minutes} min</span>}
                            </div>
                          </div>
                          {l.status === "not_started" && (
                            <button
                              onClick={() => lessonAction.mutate({ id: l.id, action: "start" })}
                              aria-label={`Start "${l.title}"`}
                              className="rounded-lg px-2 py-1 text-xs font-medium text-brand-600 hover:bg-brand-50 dark:text-brand-400 dark:hover:bg-slate-800"
                            >
                              Start
                            </button>
                          )}
                          <IconButton label={`Move lesson "${l.title}" up`} disabled={li === 0} onClick={() => moveLesson.mutate({ id: l.id, direction: "up" })}>
                            <ChevronUp className="h-4 w-4" aria-hidden />
                          </IconButton>
                          <IconButton label={`Move lesson "${l.title}" down`} disabled={li === m.lessons.length - 1} onClick={() => moveLesson.mutate({ id: l.id, direction: "down" })}>
                            <ChevronDown className="h-4 w-4" aria-hidden />
                          </IconButton>
                          <IconButton label={`Edit lesson "${l.title}"`} onClick={() => setLessonModal({ moduleId: m.id, lesson: l })}>
                            <Pencil className="h-4 w-4" aria-hidden />
                          </IconButton>
                          <IconButton label={`Delete lesson "${l.title}"`} danger onClick={() => setConfirm({ kind: "lesson", lesson: l })}>
                            <Trash2 className="h-4 w-4" aria-hidden />
                          </IconButton>
                        </li>
                      );
                    })}
                  </ul>
                )}

                <div className="flex flex-wrap gap-2 px-4 py-3">
                  <Button variant="ghost" icon={Plus} onClick={() => setLessonModal({ moduleId: m.id, lesson: null })}>
                    Add lesson
                  </Button>
                  <Button variant="ghost" icon={ClipboardPaste} onClick={() => setBulkFor(m)}>
                    Paste lessons
                  </Button>
                </div>
              </Card>
            </li>
          ))}
        </ul>
      )}

      <div className="mt-6">
        <StudyLog course={c} today={today} onLog={() => setLogging(true)} />
      </div>

      {editingCourse && <CourseForm course={c} onClose={() => setEditingCourse(false)} />}
      {moduleModal && <ModuleModal courseId={c.id} module={moduleModal === "new" ? null : moduleModal} onClose={() => setModuleModal(null)} />}
      {lessonModal && <LessonModal moduleId={lessonModal.moduleId} lesson={lessonModal.lesson} modules={c.modules} onClose={() => setLessonModal(null)} />}
      {bulkFor && <BulkLessonsModal courseId={c.id} module={bulkFor} onClose={() => setBulkFor(null)} />}
      {logging && <SessionModal course={c} today={today} onClose={() => setLogging(false)} />}
      {confirm && (
        <ConfirmDialog
          title={confirm.kind === "course" ? "Delete course?" : confirm.kind === "module" ? "Delete module?" : "Delete lesson?"}
          message={
            confirm.kind === "course" ? (
              <>
                <strong>{c.title}</strong> and all its modules and lessons will be permanently deleted. Study time you logged is kept. This can't be undone.
              </>
            ) : confirm.kind === "module" ? (
              <>
                <strong>{confirm.module.title}</strong> and its {confirm.module.total_lessons} lesson{confirm.module.total_lessons === 1 ? "" : "s"} will be permanently deleted.
              </>
            ) : (
              <>
                <strong>{confirm.lesson.title}</strong> will be permanently deleted.
              </>
            )
          }
          busy={confirmBusy}
          error={confirmError}
          onCancel={cancelConfirm}
          onConfirm={doConfirm}
        />
      )}
    </>
  );
}
