import { useQuery } from "@tanstack/react-query";

type Health = { status: string; database: string; version: string };

export default function App() {
  const health = useQuery({
    queryKey: ["health"],
    queryFn: async (): Promise<Health> => {
      const res = await fetch("/api/health");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.json();
    },
  });

  return (
    <main className="mx-auto max-w-xl p-8">
      <h1 className="text-2xl font-semibold">AI Personal Learning &amp; Productivity Hub</h1>
      <p className="mt-2 text-slate-500">Phase 2 scaffold — backend connectivity check.</p>
      <div className="mt-6 rounded-lg border border-slate-200 bg-white p-4">
        {health.isPending && <span>Checking backend…</span>}
        {health.isError && (
          <span className="text-red-600">Backend unreachable: {String(health.error)}</span>
        )}
        {health.data && (
          <span className="text-emerald-700">
            Backend {health.data.status} · database {health.data.database} · v{health.data.version}
          </span>
        )}
      </div>
    </main>
  );
}
