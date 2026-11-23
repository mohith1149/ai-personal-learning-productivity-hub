import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, qs } from "./client";

export type CourseStatus = "active" | "paused" | "completed" | "archived";
export type LessonStatus = "not_started" | "in_progress" | "completed";

export type Progress = {
  total_lessons: number;
  completed_lessons: number;
  percent: number;
  empty_modules: number; // modules with no lessons yet; the course can't complete while any exist
  total_minutes: number;
  remaining_minutes: number;
};

export type NextLesson = {
  id: number;
  title: string;
  module_id: number;
  module_title: string;
  status: LessonStatus;
  url: string | null;
};

export type CourseSummary = {
  id: number;
  title: string;
  provider: string | null;
  url: string | null;
  description: string | null;
  kind: "course" | "video_series";
  status: CourseStatus;
  priority: number;
  target_date: string | null;
  started_at: string | null;
  completed_at: string | null;
  last_studied_at: string | null;
  progress: Progress;
  next_lesson: NextLesson | null;
  minutes_studied: number;
};

export type Lesson = {
  id: number;
  module_id: number;
  course_id: number;
  title: string;
  url: string | null;
  lesson_type: "lesson" | "video";
  duration_minutes: number | null;
  position: number;
  status: LessonStatus;
  completed_at: string | null;
  notes: string | null;
};

export type Module = { id: number; title: string; position: number; total_lessons: number; completed_lessons: number; lessons: Lesson[] };
export type CourseDetail = CourseSummary & { notes: string | null; modules: Module[] };

export type StudySession = { id: number; date: string; minutes: number; course_id: number | null; lesson_id: number | null; notes: string | null; created_at: string };
export type CourseTemplate = { key: string; title: string; provider: string; url: string; description: string; modules: string[]; already_added: boolean };

export type CourseInput = {
  title: string;
  provider?: string | null;
  url?: string | null;
  description?: string | null;
  notes?: string | null;
  kind?: "course" | "video_series";
  priority?: number;
  target_date?: string | null;
  status?: CourseStatus;
};
export type LessonInput = {
  title: string;
  url?: string | null;
  lesson_type?: "lesson" | "video";
  duration_minutes?: number | null;
  notes?: string | null;
  module_id?: number | null;
};

const ROOT = ["courses"] as const;

export const useCourses = (status?: CourseStatus) =>
  useQuery({ queryKey: [...ROOT, "list", status ?? "all"], queryFn: () => api<CourseSummary[]>(`/courses${qs({ status })}`) });

export const useCourse = (id: number) =>
  useQuery({ queryKey: [...ROOT, "detail", id], queryFn: () => api<CourseDetail>(`/courses/${id}`), enabled: Number.isFinite(id) });

export const useCourseTemplates = () =>
  useQuery({ queryKey: [...ROOT, "templates"], queryFn: () => api<CourseTemplate[]>("/course-templates") });

export const useSessions = (courseId: number) =>
  useQuery({
    queryKey: [...ROOT, "sessions", courseId],
    queryFn: () => api<StudySession[]>(`/learning-sessions${qs({ course_id: courseId, limit: 20 })}`),
  });

/** Mutations that return the updated course put it straight into the cache (instant UI), then refresh everything else. */
function useCourseMutation<TVars>(fn: (v: TVars) => Promise<CourseDetail>) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: (course) => {
      qc.setQueryData([...ROOT, "detail", course.id], course);
      qc.invalidateQueries({ queryKey: ROOT });
    },
  });
}

function useInvalidating<TVars, TData>(fn: (v: TVars) => Promise<TData>) {
  const qc = useQueryClient();
  return useMutation({ mutationFn: fn, onSuccess: () => qc.invalidateQueries({ queryKey: ROOT }) });
}

export const useCreateCourse = () => useCourseMutation((body: CourseInput) => api<CourseDetail>("/courses", { method: "POST", body }));
export const useUpdateCourse = () =>
  useCourseMutation(({ id, body }: { id: number; body: Partial<CourseInput> }) => api<CourseDetail>(`/courses/${id}`, { method: "PATCH", body }));
export const useDeleteCourse = () => useInvalidating((id: number) => api<void>(`/courses/${id}`, { method: "DELETE" }));
export const useAddTemplate = () => useCourseMutation((key: string) => api<CourseDetail>(`/course-templates/${key}`, { method: "POST" }));

export const useCreateModule = () =>
  useCourseMutation(({ courseId, title }: { courseId: number; title: string }) =>
    api<CourseDetail>(`/courses/${courseId}/modules`, { method: "POST", body: { title } }));
export const useRenameModule = () =>
  useCourseMutation(({ id, title }: { id: number; title: string }) => api<CourseDetail>(`/modules/${id}`, { method: "PATCH", body: { title } }));
export const useDeleteModule = () => useCourseMutation((id: number) => api<CourseDetail>(`/modules/${id}`, { method: "DELETE" }));
export const useMoveModule = () =>
  useCourseMutation(({ id, direction }: { id: number; direction: "up" | "down" }) =>
    api<CourseDetail>(`/modules/${id}/move`, { method: "POST", body: { direction } }));

export const useCreateLesson = () =>
  useCourseMutation(({ moduleId, body }: { moduleId: number; body: LessonInput }) =>
    api<CourseDetail>(`/modules/${moduleId}/lessons`, { method: "POST", body }));
export const useBulkLessons = () =>
  useCourseMutation(({ courseId, moduleId, titles }: { courseId: number; moduleId: number; titles: string[] }) =>
    api<CourseDetail>(`/courses/${courseId}/bulk-lessons`, { method: "POST", body: { module_id: moduleId, titles } }));
export const useUpdateLesson = () =>
  useCourseMutation(({ id, body }: { id: number; body: Partial<LessonInput> }) => api<CourseDetail>(`/lessons/${id}`, { method: "PATCH", body }));
export const useDeleteLesson = () => useCourseMutation((id: number) => api<CourseDetail>(`/lessons/${id}`, { method: "DELETE" }));
export const useMoveLesson = () =>
  useCourseMutation(({ id, direction }: { id: number; direction: "up" | "down" }) =>
    api<CourseDetail>(`/lessons/${id}/move`, { method: "POST", body: { direction } }));
export const useLessonAction = () =>
  useCourseMutation(({ id, action }: { id: number; action: "start" | "complete" | "uncomplete" }) =>
    api<CourseDetail>(`/lessons/${id}/${action}`, { method: "POST" }));

export const useCreateSession = () =>
  useInvalidating((body: { course_id: number; lesson_id?: number | null; minutes: number; date?: string | null; notes?: string | null }) =>
    api<StudySession>("/learning-sessions", { method: "POST", body }));
export const useDeleteSession = () => useInvalidating((id: number) => api<void>(`/learning-sessions/${id}`, { method: "DELETE" }));
