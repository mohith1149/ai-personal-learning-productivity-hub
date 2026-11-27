import { Copy, ExternalLink, Link2Off, RefreshCw } from "lucide-react";
import { useState } from "react";
import { useCreateShare, useShare, useStopSharing } from "../../api/share";
import { FormError } from "../../components/forms";
import { ConfirmDialog } from "../../components/Modal";
import { Button, Card, ErrorNotice, Spinner } from "../../components/ui";

const WHAT_IS_SHOWN = [
  "your name, streaks, and hours studied and spent building",
  "daily-challenge commits that were verified against GitHub (first line of the message, short hash, date)",
  "projects with their technologies, topics you finished and courses you completed",
];
const NEVER_SHOWN = "Tasks, habits, notes, your write-ups, your e-mail address, unverified commits, and the names and links of private repositories.";

export function ShareSettings() {
  const share = useShare();
  const create = useCreateShare();
  const stop = useStopSharing();
  const [confirm, setConfirm] = useState<"replace" | "stop" | null>(null);
  const [copied, setCopied] = useState(false);
  const url = share.data?.path ? `${window.location.origin}${share.data.path}` : null;

  const copy = async () => {
    if (!url) return;
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
    } catch {
      setCopied(false); // the link is also shown in the box, so it can be copied by hand
    }
  };

  return (
    <Card aria-label="Share your progress">
      <h2 className="mb-1 text-sm font-semibold text-slate-900 dark:text-white">Share your progress</h2>
      <p className="mb-3 text-sm text-slate-500 dark:text-slate-400">
        A private link to a read-only page of your progress, for a friend, a mentor or a portfolio. Anyone who has the link can see it; nobody else can find it.
      </p>
      {share.isPending ? (
        <Spinner label="Loading…" />
      ) : share.isError ? (
        <ErrorNotice error={share.error} onRetry={() => share.refetch()} />
      ) : (
        <div className="space-y-3">
          <div className="text-sm text-slate-700 dark:text-slate-300">
            <p className="font-medium">The page shows</p>
            <ul className="ml-5 list-disc">
              {WHAT_IS_SHOWN.map((t) => (
                <li key={t}>{t}</li>
              ))}
            </ul>
            <p className="mt-1">
              <span className="font-medium">Never shown:</span> {NEVER_SHOWN}
            </p>
          </div>
          {url ? (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <input
                  readOnly
                  aria-label="Share link"
                  value={url}
                  onFocus={(e) => e.currentTarget.select()}
                  className="min-w-0 flex-1 rounded-lg border border-slate-300 bg-slate-50 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
                />
                <Button variant="secondary" icon={Copy} onClick={copy}>
                  {copied ? "Copied" : "Copy"}
                </Button>
                <a href={url} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1 rounded-lg px-2 py-2 text-sm text-brand-600 hover:underline dark:text-brand-400">
                  Preview <ExternalLink className="h-3.5 w-3.5" aria-hidden />
                </a>
              </div>
              <p className="text-xs text-slate-500 dark:text-slate-400">The weekly report e-mail includes this link while sharing is on.</p>
              <div className="flex flex-wrap gap-2">
                <Button variant="secondary" icon={RefreshCw} onClick={() => setConfirm("replace")}>
                  Make a new link
                </Button>
                <Button variant="secondary" icon={Link2Off} onClick={() => setConfirm("stop")}>
                  Stop sharing
                </Button>
              </div>
            </>
          ) : (
            <>
              <FormError message={create.error?.message} />
              <Button loading={create.isPending} onClick={() => create.mutate()}>
                Create a share link
              </Button>
            </>
          )}
        </div>
      )}
      {confirm === "replace" && (
        <ConfirmDialog
          title="Make a new link?"
          message="The current link stops working straight away. Anyone you gave it to will need the new one."
          confirmLabel="Make a new link"
          busy={create.isPending}
          error={create.error?.message}
          onCancel={() => setConfirm(null)}
          onConfirm={() =>
            create.mutate(undefined, {
              onSuccess: () => {
                setCopied(false);
                setConfirm(null);
              },
            })
          }
        />
      )}
      {confirm === "stop" && (
        <ConfirmDialog
          title="Stop sharing?"
          message="The link stops working and the page can no longer be opened. You can create a new link later."
          confirmLabel="Stop sharing"
          busy={stop.isPending}
          error={stop.error?.message}
          onCancel={() => setConfirm(null)}
          onConfirm={() => stop.mutate(undefined, { onSuccess: () => setConfirm(null) })}
        />
      )}
    </Card>
  );
}
