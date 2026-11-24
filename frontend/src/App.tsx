import { Navigate, Route, Routes } from "react-router-dom";
import { useAuthStatus } from "./api/auth";
import { AppLayout } from "./components/AppLayout";
import { NAV_GROUPS } from "./nav";
import { LoginPage, SetupPage } from "./pages/AuthPages";
import { CourseDetailPage } from "./pages/courses/CourseDetailPage";
import { CoursesPage } from "./pages/courses/CoursesPage";
import { HabitsPage } from "./pages/habits/HabitsPage";
import { PlannerPage } from "./pages/planner/PlannerPage";
import { ProjectDetailPage } from "./pages/projects/ProjectDetailPage";
import { ProjectsPage } from "./pages/projects/ProjectsPage";
import { RoadmapPage } from "./pages/roadmap/RoadmapPage";
import { TasksPage } from "./pages/tasks/TasksPage";
import { VideosPage } from "./pages/videos/VideosPage";
import { ComingSoonPage, DashboardPage, NotFoundPage, SettingsPage } from "./pages/ShellPages";

function FullScreenMessage({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-full items-center justify-center p-8 text-slate-500 dark:text-slate-400">{children}</div>
  );
}

export default function App() {
  const status = useAuthStatus();

  if (status.isPending) return <FullScreenMessage>Loading…</FullScreenMessage>;
  if (status.isError)
    return (
      <FullScreenMessage>
        <div className="text-center">
          <p className="font-medium text-red-600">Cannot reach the backend.</p>
          <p className="mt-1 text-sm">Start it with uvicorn on port 8000, then reload.</p>
          <button onClick={() => status.refetch()} className="mt-4 rounded-lg border px-3 py-1.5 text-sm">
            Retry
          </button>
        </div>
      </FullScreenMessage>
    );

  const { setup_required, authenticated } = status.data;

  // Gate everything on server-reported state; the backend independently enforces auth on every API call.
  if (setup_required)
    return (
      <Routes>
        <Route path="/setup" element={<SetupPage />} />
        <Route path="*" element={<Navigate to="/setup" replace />} />
      </Routes>
    );
  if (!authenticated)
    return (
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    );
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<DashboardPage />} />
        {/* Features not built yet render an honest placeholder; each milestone replaces its route below. */}
        {NAV_GROUPS.flatMap((g) => g.items)
          .filter((i) => i.status === "soon")
          .map((i) => (
            <Route key={i.to} path={i.to} element={<ComingSoonPage />} />
          ))}
        <Route path="tasks" element={<TasksPage />} />
        <Route path="courses" element={<CoursesPage />} />
        <Route path="courses/:courseId" element={<CourseDetailPage />} />
        <Route path="videos" element={<VideosPage />} />
        <Route path="roadmap" element={<RoadmapPage />} />
        <Route path="habits" element={<HabitsPage />} />
        <Route path="planner" element={<PlannerPage />} />
        <Route path="projects" element={<ProjectsPage />} />
        <Route path="projects/:projectId" element={<ProjectDetailPage />} />
        <Route path="settings" element={<SettingsPage />} />
        {/* Signed-in users who visit /login or /setup land on the dashboard. */}
        <Route path="login" element={<Navigate to="/" replace />} />
        <Route path="setup" element={<Navigate to="/" replace />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
