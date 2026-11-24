import { Check, Trash2, X } from "lucide-react";
import { useState } from "react";
import {
  useAddMemory,
  useAiStatus,
  useAiTools,
  useApprove,
  useDeleteMemory,
  useMemories,
  usePending,
  useReject,
  type Memory,
  type Pending,
} from "../../api/assistant";
import { FormError, SelectInput, TextInput } from "../../components/forms";
import { Badge, Button, Card, ErrorNotice, PageHeader, Spinner } from "../../components/ui";

function StatusCard() {
  const status = useAiStatus();
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
            {status.data.model && <span>Model: {status.data.model}</span>}
            {!status.data.live_verified && <Badge>Not tested live</Badge>}
          </p>
          <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">{status.data.message}</p>
          <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
            The chat window arrives with the live Claude connection in a later phase. Until then this page shows what the assistant will be allowed to do, and it already
            holds your memory and the approval queue.
          </p>
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

function MemoryRow({ m }: { m: Memory }) {
  const del = useDeleteMemory();
  return (
    <li className="flex items-center gap-3 py-2">
      <Badge>{m.kind}</Badge>
      <span className="min-w-0 flex-1 text-sm text-slate-900 dark:text-slate-100">{m.content}</span>
      <span className="text-xs text-slate-500 dark:text-slate-400">{m.source === "assistant" ? "added by assistant" : "added by you"}</span>
      <Button variant="ghost" icon={Trash2} loading={del.isPending} onClick={() => del.mutate(m.id)} aria-label={`Delete memory: ${m.content}`} className="px-2 py-1" />
    </li>
  );
}

function MemoryCard() {
  const memories = useMemories();
  const add = useAddMemory();
  const [content, setContent] = useState("");
  const [kind, setKind] = useState<Memory["kind"]>("preference");
  const [localError, setLocalError] = useState<string | null>(null);
  return (
    <Card aria-label="Memory">
      <h2 className="text-sm font-semibold text-slate-900 dark:text-white">Memory</h2>
      <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">Short notes the assistant will see. You can read and delete every one. It can only add a note if you approve it.</p>
      <form
        className="mt-3 flex flex-wrap items-end gap-3"
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          setLocalError(null);
          if (content.trim().length < 3) return setLocalError("A memory needs at least 3 characters.");
          add.mutate({ content: content.trim(), kind }, { onSuccess: () => setContent("") });
        }}
      >
        <div className="min-w-[14rem] flex-1">
          <TextInput label="Add a note" value={content} onChange={(e) => setContent(e.target.value)} maxLength={500} />
        </div>
        <SelectInput label="Type" value={kind} onChange={(e) => setKind(e.target.value as Memory["kind"])}>
          <option value="preference">Preference</option>
          <option value="fact">Fact</option>
          <option value="goal">Goal</option>
        </SelectInput>
        <Button type="submit" loading={add.isPending}>
          Save note
        </Button>
      </form>
      <div className="mt-2">
        <FormError message={localError ?? add.error?.message} />
      </div>
      {memories.isPending ? (
        <Spinner label="Loading…" />
      ) : memories.isError ? (
        <ErrorNotice error={memories.error} onRetry={() => memories.refetch()} />
      ) : memories.data.length === 0 ? (
        <p className="mt-3 text-sm text-slate-500 dark:text-slate-400">Nothing saved yet.</p>
      ) : (
        <ul aria-label="Saved notes" className="mt-2 divide-y divide-slate-100 dark:divide-slate-800">
          {memories.data.map((m) => (
            <MemoryRow key={m.id} m={m} />
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
  return (
    <>
      <PageHeader title="AI assistant" description="The foundation for the assistant: what it may do, your approval queue and its memory." />
      <div className="space-y-4">
        <StatusCard />
        <ApprovalsCard />
        <MemoryCard />
        <ToolsCard />
      </div>
    </>
  );
}
