import { Navigate, Route, Routes } from "react-router-dom";
import { useAuthStatus, useLogout } from "./api/auth";
import { LoginPage, SetupPage } from "./pages/AuthPages";

function FullScreenMessage({ children }: { children: React.ReactNode }) {
  return <div className="flex min-h-full items-center justify-center p-8 text-slate-500">{children}</div>;
}

/** Temporary signed-in landing page; replaced by the real app shell in the next milestone. */
function Home() {
  const { data } = useAuthStatus();
  const logout = useLogout();
  return (
    <main className="mx-auto max-w-xl p-8">
      <h1 className="text-2xl font-semibold">Hello, {data?.user?.display_name}</h1>
      <p className="mt-2 text-slate-500">You are signed in. The application shell arrives next.</p>
      <button
        onClick={() => logout.mutate()}
        className="mt-6 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium hover:bg-slate-50"
      >
        Sign out
      </button>
    </main>
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
      <Route path="/" element={<Home />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
