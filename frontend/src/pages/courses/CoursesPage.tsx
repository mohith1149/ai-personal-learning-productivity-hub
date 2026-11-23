import { BookOpen, ExternalLink, GraduationCap, Plus, Sparkles } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useAuthStatus } from "../../api/auth";
import { useAddTemplate, useCourses, useCourseTemplates, type CourseStatus, type CourseSummary } from "../../api/courses";
import { Badge, Button, Card, EmptyState, ErrorNotice, PageHeader, ProgressBar, Spinner, StatusBadge, cx } from "../../components/ui";
import { formatDay, todayIn } from "../../lib/dates";
import { CourseForm } from "./CourseForm";

const TABS: { key: CourseStatus | "all"; label: string }[] = [
  { key: "active", label: "Active" },
  { key: "paused", label: "Paused" },
  { key: "completed", label: "Completed" },
  { key: "archived", label: "Archived" },
  { key: "all", label: "All" },
];

export function CourseStatusBadge({ status }: { status: CourseStatus }) {
  if (status === "completed") return <StatusBadge status="completed" />;
  if (status === "paused") return <Badge>Paused</Badge>;
  if (status === "archived") return <Badge>Archived</Badge>;
  return <StatusBadge status="in_progress" />;
}

function CourseCard({ course, today, timeZone }: { course: CourseSummary; today: string; timeZone: string }) {
  const p = course.progress;
  const last = course.last_studied_at ? formatDay(todayIn(timeZone, new Date(course.last_studied_at)), today) : null;
  return (
    <li>
      <Link
        to={`/courses/${course.id}`}
        className="block rounded-xl border border-slate-200 bg-white p-4 shadow-sm transition hover:border-brand-500 dark:border-slate-800 dark:bg-slate-900"
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="truncate text-base font-semibold text-slate-900 dark:text-white">{course.title}</h2>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              {course.provider ?? "No provider"}
              {course.kind === "video_series" ? " · Video series" : ""}
            </p>
          </div>
          <CourseStatusBadge status={course.status} />
        </div>

        <div className="mt-3">
          <ProgressBar percent={p.percent} label={`${course.title} progress`} />
          <div className="mt-1.5 flex justify-between text-xs text-slate-500 dark:text-slate-400">
            <span>
              {p.total_lessons === 0 ? "No lessons added yet" : `${p.completed_lessons} of ${p.total_lessons} lessons`}
            </span>
            <span className="tabular-nums">{p.percent}%</span>
          </div>
        </div>

        <div className="mt-3 text-sm text-slate-600 dark:text-slate-300">
          {course.next_lesson ? (
            <>
              <span className="text-slate-500 dark:text-slate-400">Up next: </span>
              {course.next_lesson.title}
            </>
          ) : p.total_lessons > 0 ? (
            p.empty_modules > 0 ? `All added lessons done · ${p.empty_modules} module${p.empty_modules === 1 ? "" : "s"} still empty` : "All lessons completed"
          ) : null}
        </div>
        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500 dark:text-slate-400">
          {last && <span>Last studied {last}</span>}
          {course.minutes_studied > 0 && <span>{course.minutes_studied} min studied</span>}
          {p.remaining_minutes > 0 && <span>~{p.remaining_minutes} min left</span>}
        </div>
      </Link>
    </li>
  );
}

export function CoursesPage() {
  const user = useAuthStatus().data?.user;
  const timeZone = user?.timezone ?? "UTC";
  const today = todayIn(timeZone);
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const raw = params.get("status");
  const tab = (TABS.some((t) => t.key === raw) ? raw : "active") as CourseStatus | "all";
  const courses = useCourses(tab === "all" ? undefined : tab);
  const templates = useCourseTemplates();
  const addTemplate = useAddTemplate();
  const [creating, setCreating] = useState(false);

  const available = templates.data?.filter((t) => !t.already_added) ?? [];

  return (
    <>
      <PageHeader
        title="Courses"
        description="Track the courses you take, lesson by lesson. Progress only moves when you mark a lesson done."
        actions={
          <Button icon={Plus} onClick={() => setCreating(true)}>
            New course
          </Button>
        }
      />

      <div role="tablist" aria-label="Course views" className="-mx-1 mb-4 flex gap-1 overflow-x-auto px-1 pb-1">
        {TABS.map(({ key, label }) => (
          <button
            key={key}
            role="tab"
            aria-selected={tab === key}
            onClick={() => setParams(key === "active" ? {} : { status: key }, { replace: true })}
            className={cx(
              "shrink-0 rounded-lg px-3 py-1.5 text-sm font-medium transition",
              tab === key ? "bg-brand-600 text-white" : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800",
            )}
          >
            {label}
          </button>
        ))}
      </div>

      {courses.isPending ? (
        <Spinner label="Loading courses…" />
      ) : courses.isError ? (
        <ErrorNotice error={courses.error} onRetry={() => courses.refetch()} />
      ) : courses.data.length === 0 ? (
        <EmptyState
          icon={GraduationCap}
          title={tab === "all" ? "No courses yet" : `No ${tab} courses`}
          action={
            tab === "active" || tab === "all" ? (
              <Button icon={Plus} onClick={() => setCreating(true)}>
                New course
              </Button>
            ) : undefined
          }
        >
          {tab === "active" || tab === "all"
            ? "Add a course you are taking, or start from a template below."
            : "Courses with this status will appear here."}
        </EmptyState>
      ) : (
        <ul className="grid gap-3 md:grid-cols-2" aria-label="Courses">
          {courses.data.map((c) => (
            <CourseCard key={c.id} course={c} today={today} timeZone={timeZone} />
          ))}
        </ul>
      )}

      {available.length > 0 && (
        <section className="mt-8" aria-label="Course templates">
          <h2 className="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-900 dark:text-white">
            <Sparkles className="h-4 w-4 text-brand-500" aria-hidden />
            Quick start
          </h2>
          <div className="grid gap-3 md:grid-cols-2">
            {available.map((t) => (
              <Card key={t.key}>
                <div className="flex items-start gap-3">
                  <BookOpen className="mt-0.5 h-5 w-5 shrink-0 text-brand-500" aria-hidden />
                  <div className="min-w-0 flex-1">
                    <h3 className="font-semibold text-slate-900 dark:text-white">
                      {t.provider}: {t.title}
                    </h3>
                    <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">{t.description}</p>
                    <ul className="mt-2 list-disc pl-5 text-sm text-slate-600 dark:text-slate-300">
                      {t.modules.map((m) => (
                        <li key={m}>{m}</li>
                      ))}
                    </ul>
                    <div className="mt-3 flex flex-wrap items-center gap-3">
                      <Button
                        loading={addTemplate.isPending && addTemplate.variables === t.key}
                        onClick={() => addTemplate.mutate(t.key, { onSuccess: (c) => navigate(`/courses/${c.id}`) })}
                      >
                        Add this course
                      </Button>
                      <a
                        href={t.url}
                        target="_blank"
                        rel="noreferrer noopener"
                        className="inline-flex items-center gap-1 text-sm text-brand-600 hover:underline dark:text-brand-400"
                      >
                        Course page <ExternalLink className="h-3.5 w-3.5" aria-hidden />
                      </a>
                    </div>
                    {addTemplate.error && (
                      <p role="alert" className="mt-2 text-sm text-red-600 dark:text-red-400">
                        {addTemplate.error.message}
                      </p>
                    )}
                  </div>
                </div>
              </Card>
            ))}
          </div>
        </section>
      )}

      {creating && <CourseForm course={null} onClose={() => setCreating(false)} onSaved={(c) => navigate(`/courses/${c.id}`)} />}
    </>
  );
}
