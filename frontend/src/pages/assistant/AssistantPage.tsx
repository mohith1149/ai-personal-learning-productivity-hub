import { Check, X } from "lucide-react";
import { useAiStatus, useAiTools, useApprove, useCheckConnection, useModelChoice, usePending, useReject, type Pending } from "../../api/assistant";
import { FormError } from "../../components/forms";
import { Badge, Button, Card, ErrorNotice, PageHeader, Spinner } from "../../components/ui";
import { ChatCard } from "./ChatCard";

function StatusCard() {
  const status = useAiStatus();
  const check = useCheckConnection();
  const choice = useModelChoice();
  return (
    <Card aria-label="Assistant status">
      <h2 className="text-sm font-semibold text-slate-900 dark:text-white">Connection</h2>
      {status.isPending ? (
        <Spinner label="Checking…" />
      ) : status.isError ? (
        <ErrorNotice error={status.error} onRetry={() => status.refetch()} />
      ) : (
        <>
          <p className="mt-2 flex flex-wrap items-center gap-2 text-sm text-slate-700 dark:text-slate-300">
            <Badge tone={status.data.connected ? "brand" : "neutral"}>{status.data.connected ? "Provider configured" : "Not connected"}</Badge>
            {status.data.model && <span>Model: {choice?.model ?? status.data.model}</span>}
            {status.data.live_verified ? <Badge tone="brand">Tested live</Badge> : <Badge>Not tested live</Badge>}
          </p>
          <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">{status.data.message}</p>
          {status.data.connected && (
            <div className="mt-3">
              <Button variant="secondary" loading={check.isPending} onClick={() => check.mutate()}>
                Test the connection
              </Button>
              {check.data && (
                <p role="status" className="mt-2 text-sm text-emerald-700 dark:text-emerald-400">
                  {check.data.message} ({check.data.model})
                </p>
              )}
              {check.error && <FormError message={check.error.message} />}
            </div>
          )}
        </>
      )}
    </Card>
  );
}

function PendingRow({ a }: { a: Pending }) {
  const approve = useApprove();
  const reject = useReject();
  const error = approve.error ?? reject.error;
  return (
    <li className="py-3">
      <div className="flex flex-wrap items-center gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-slate-900 dark:text-white">{a.summary}</p>
          <p className="text-xs text-slate-500 dark:text-slate-400">Proposed by the assistant · {a.tool_name}</p>
        </div>
        <Button icon={Check} loading={approve.isPending} onClick={() => approve.mutate(a.id)} aria-label={`Approve: ${a.summary}`} className="px-2.5 py-1.5">
          Approve
        </Button>
        <Button variant="secondary" icon={X} loading={reject.isPending} onClick={() => reject.mutate(a.id)} aria-label={`Reject: ${a.summary}`} className="px-2.5 py-1.5">
          Reject
        </Button>
      </div>
      {error && (
        <p role="alert" className="mt-1 text-sm text-red-600 dark:text-red-400">
          {error.message}
        </p>
      )}
    </li>
  );
}

function ApprovalsCard() {
  const pending = usePending();
  return (
    <Card aria-label="Waiting for approval">
      <h2 className="text-sm font-semibold text-slate-900 dark:text-white">Waiting for your approval</h2>
      <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">The assistant can only propose changes. Nothing happens until you approve it here.</p>
      {pending.isPending ? (
        <Spinner label="Loading…" />
      ) : pending.isError ? (
        <ErrorNotice error={pending.error} onRetry={() => pending.refetch()} />
      ) : pending.data.length === 0 ? (
        <p className="mt-3 text-sm text-slate-500 dark:text-slate-400">No proposals are waiting.</p>
      ) : (
        <ul aria-label="Proposals" className="mt-1 divide-y divide-slate-100 dark:divide-slate-800">
          {pending.data.map((a) => (
            <PendingRow key={a.id} a={a} />
          ))}
        </ul>
      )}
    </Card>
  );
}

function ToolsCard() {
  const tools = useAiTools();
  return (
    <Card aria-label="What the assistant can do">
      <h2 className="text-sm font-semibold text-slate-900 dark:text-white">What the assistant can do</h2>
      <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
        It never touches your data directly. It can only call these actions, which use the same code as the pages. Actions that change something are only proposals until you approve them.
      </p>
      {tools.isPending ? (
        <Spinner label="Loading…" />
      ) : tools.isError ? (
        <ErrorNotice error={tools.error} onRetry={() => tools.refetch()} />
      ) : (
        (["read", "write"] as const).map((kind) => (
          <div key={kind} className="mt-3">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">{kind === "read" ? "Look things up" : "Propose changes (needs your approval)"}</h3>
            <ul aria-label={kind === "read" ? "Read tools" : "Write tools"} className="mt-1 divide-y divide-slate-100 dark:divide-slate-800">
              {tools.data
                .filter((t) => t.kind === kind)
                .map((t) => (
                  <li key={t.name} className="py-1.5 text-sm">
                    <code className="rounded bg-slate-100 px-1 text-xs dark:bg-slate-800">{t.name}</code> <span className="text-slate-600 dark:text-slate-400">{t.description}</span>
                  </li>
                ))}
            </ul>
          </div>
        ))
      )}
    </Card>
  );
}

export function AssistantPage() {
  const connected = useAiStatus().data?.connected === true;
  return (
    <>
      <PageHeader title="AI assistant" description="Chat with the assistant and review what it proposes." />
      <div className="space-y-4">
        {connected && <ChatCard />}
        {connected && <ApprovalsCard />}
        <StatusCard />
        {!connected && <ApprovalsCard />}
        <ToolsCard />
      </div>
    </>
  );
}
