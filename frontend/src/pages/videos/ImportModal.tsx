import { useState, type FormEvent } from "react";
import { useImport, usePreview, useYouTubeStatus, type ImportResult, type Preview, type PreviewVideo } from "../../api/youtube";
import { FormError, TextInput, controlClass } from "../../components/forms";
import { Modal } from "../../components/Modal";
import { Badge, Button, Spinner, cx } from "../../components/ui";
import { countOrUnavailable, formatDate } from "../../lib/format";
import { Thumbnail } from "./VideoCard";

const PRESETS = [10, 25, 50, 100] as const;
type Amount = "10" | "25" | "50" | "100" | "custom" | "all";

/** What a row in the preview can do. Already-imported videos can't be ticked: importing them again changes nothing. */
const selectable = (v: PreviewVideo) => !v.in_library;

function SourceHeader({ preview, selectedCount }: { preview: Preview; selectedCount: number }) {
  const { source } = preview;
  return (
    <div className="flex gap-3">
      {source.thumbnail_url && <img src={source.thumbnail_url} alt="" referrerPolicy="no-referrer" className="h-14 w-14 shrink-0 rounded-full object-cover" />}
      <div className="min-w-0">
        <h3 className="flex flex-wrap items-center gap-2 text-base font-semibold text-slate-900 dark:text-white">
          <span className="truncate">{source.title}</span>
          <Badge tone="brand">{source.kind === "channel" ? "Channel" : "Playlist"}</Badge>
        </h3>
        <dl className="mt-1 grid grid-cols-2 gap-x-6 gap-y-0.5 text-sm text-slate-600 sm:grid-cols-4 dark:text-slate-400">
          <div>
            <dt className="inline">On YouTube: </dt>
            <dd className="inline font-medium tabular-nums text-slate-900 dark:text-white">{countOrUnavailable(source.total_available)}</dd>
          </div>
          <div>
            <dt className="inline">Retrieved: </dt>
            <dd className="inline font-medium tabular-nums text-slate-900 dark:text-white">{preview.retrieved}</dd>
          </div>
          <div>
            <dt className="inline">Already in library: </dt>
            <dd className="inline font-medium tabular-nums text-slate-900 dark:text-white">{preview.already_in_library}</dd>
          </div>
          <div>
            <dt className="inline">Selected: </dt>
            <dd className="inline font-medium tabular-nums text-slate-900 dark:text-white">{selectedCount}</dd>
          </div>
        </dl>
      </div>
    </div>
  );
}

export function ImportModal({ onClose, onImported }: { onClose: () => void; onImported?: (r: ImportResult) => void }) {
  const status = useYouTubeStatus();
  const previewMut = usePreview();
  const importMut = useImport();
  const [url, setUrl] = useState("");
  const [amount, setAmount] = useState<Amount>("25");
  const [custom, setCustom] = useState("30");
  const [localError, setLocalError] = useState<string | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [result, setResult] = useState<ImportResult | null>(null);
  const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;

  const limit = (): number | null | "bad" => {
    if (amount === "all") return null;
    if (amount === "custom") {
      const n = Number(custom);
      return Number.isInteger(n) && n >= 1 && n <= 2000 ? n : "bad";
    }
    return Number(amount);
  };

  const runPreview = (e: FormEvent) => {
    e.preventDefault();
    setLocalError(null);
    if (!url.trim()) return setLocalError("Paste a YouTube channel or playlist link.");
    const n = limit();
    if (n === "bad") return setLocalError("Enter a whole number of videos from 1 to 2000.");
    previewMut.mutate(
      { url: url.trim(), limit: n },
      {
        onSuccess: (p) => {
          setPreview(p);
          setPicked(new Set()); // nothing is pre-selected: the user decides
        },
      },
    );
  };

  const toggle = (id: string) =>
    setPicked((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const doImport = () => {
    if (!preview || picked.size === 0) return;
    // Keep the order shown on screen.
    const ids = preview.videos.filter((v) => picked.has(v.youtube_video_id)).map((v) => v.youtube_video_id);
    importMut.mutate(
      { url: url.trim(), video_ids: ids, retrieved: preview.retrieved },
      {
        onSuccess: (r) => {
          setResult(r);
          onImported?.(r);
        },
      },
    );
  };

  /* ---------------- step 3: result ---------------- */
  if (result) {
    return (
      <Modal title="Import YouTube videos" onClose={onClose} size="lg">
        <div className="space-y-3" role="status">
          <p className="text-sm text-slate-700 dark:text-slate-300">
            Imported <strong>{result.created}</strong> new video{result.created === 1 ? "" : "s"} into <strong>{result.collection.name}</strong>.
          </p>
          <ul className="list-disc pl-5 text-sm text-slate-600 dark:text-slate-400">
            {result.linked > 0 && <li>{result.linked} already in your library, now also linked to this collection (or restored).</li>}
            {result.already_in_collection > 0 && <li>{result.already_in_collection} were already in this collection.</li>}
            {result.unavailable > 0 && <li>{result.unavailable} are no longer available on YouTube and were skipped.</li>}
            <li>Nothing was marked as watched.</li>
          </ul>
          <div className="flex justify-end">
            <Button onClick={onClose}>Done</Button>
          </div>
        </div>
      </Modal>
    );
  }

  /* ---------------- step 2: preview + choose ---------------- */
  if (preview) {
    const newOnes = preview.videos.filter(selectable);
    return (
      <Modal title="Choose videos to import" onClose={onClose} size="lg">
        <div className="space-y-4">
          <SourceHeader preview={preview} selectedCount={picked.size} />
          {preview.unavailable > 0 && (
            <p className="text-sm text-slate-500 dark:text-slate-400">
              {preview.unavailable} video{preview.unavailable === 1 ? " is" : "s are"} private or deleted and can't be shown.
            </p>
          )}
          {preview.more_available && (
            <p className="text-sm text-slate-500 dark:text-slate-400">YouTube has more videos than the {preview.retrieved} retrieved. Go back to retrieve more.</p>
          )}

          {preview.videos.length === 0 ? (
            <p className="text-sm text-slate-500 dark:text-slate-400">No public videos were found here.</p>
          ) : (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <Button variant="secondary" onClick={() => setPicked(new Set(newOnes.map((v) => v.youtube_video_id)))} disabled={newOnes.length === 0}>
                  Select all new ({newOnes.length})
                </Button>
                <Button variant="ghost" onClick={() => setPicked(new Set())} disabled={picked.size === 0}>
                  Clear selection
                </Button>
              </div>
              <ul aria-label="Videos found" className="max-h-[50vh] divide-y divide-slate-100 overflow-y-auto rounded-lg border border-slate-200 dark:divide-slate-800 dark:border-slate-800">
                {preview.videos.map((v) => {
                  const date = formatDate(v.published_at, tz);
                  return (
                    <li key={v.youtube_video_id}>
                      <label className={cx("flex items-center gap-3 p-2.5", selectable(v) ? "cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800/50" : "opacity-60")}>
                        <input
                          type="checkbox"
                          aria-label={`Select ${v.title}`}
                          checked={picked.has(v.youtube_video_id)}
                          disabled={!selectable(v)}
                          onChange={() => toggle(v.youtube_video_id)}
                        />
                        <Thumbnail video={v} className="w-28 shrink-0" />
                        <span className="min-w-0 flex-1">
                          <span className="line-clamp-2 text-sm font-medium text-slate-900 dark:text-white">{v.title}</span>
                          <span className="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs text-slate-500 dark:text-slate-400">
                            {date && <span>{date}</span>}
                            {v.in_library && <Badge>Already in library</Badge>}
                            {v.removed && <Badge>Removed earlier, will be restored</Badge>}
                          </span>
                        </span>
                      </label>
                    </li>
                  );
                })}
              </ul>
            </>
          )}

          <FormError message={importMut.error?.message} />
          <div className="flex flex-wrap items-center justify-between gap-2">
            <Button
              variant="secondary"
              onClick={() => {
                setPreview(null);
                importMut.reset();
              }}
            >
              Back
            </Button>
            <Button onClick={doImport} loading={importMut.isPending} disabled={picked.size === 0}>
              {`Import ${picked.size} selected`}
            </Button>
          </div>
        </div>
      </Modal>
    );
  }

  /* ---------------- step 1: choose a source ---------------- */
  const notConfigured = status.data?.configured === false;
  return (
    <Modal title="Import from YouTube" onClose={onClose} size="lg">
      {status.isPending ? (
        <Spinner label="Checking YouTube setup…" />
      ) : notConfigured ? (
        <div role="alert" className="space-y-2 rounded-lg bg-amber-50 p-3 text-sm text-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
          <p className="font-medium">YouTube import isn't set up yet.</p>
          <p>
            Create a YouTube Data API v3 key in Google Cloud Console, add it to <code>backend/.env</code> as <code>YOUTUBE_API_KEY=…</code>, then restart the backend. The key stays on the
            server and is never sent to your browser.
          </p>
        </div>
      ) : (
        <form onSubmit={runPreview} className="space-y-4" noValidate>
          <TextInput
            label="YouTube channel or playlist link"
            placeholder="https://www.youtube.com/@ByteByteGo"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            hint="A channel (@handle or /channel/ID) or a playlist link. You'll see the videos first; nothing is imported until you choose."
          />
          <div>
            <label htmlFor="import-amount" className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">
              How many videos to retrieve
            </label>
            <div className="flex flex-wrap items-center gap-2">
              <select id="import-amount" value={amount} onChange={(e) => setAmount(e.target.value as Amount)} className={cx("w-48", controlClass)}>
                {PRESETS.map((n) => (
                  <option key={n} value={String(n)}>
                    Latest {n}
                  </option>
                ))}
                <option value="custom">Custom number</option>
                <option value="all">All videos</option>
              </select>
              {amount === "custom" && (
                <input
                  type="number"
                  min={1}
                  max={2000}
                  aria-label="Custom number of videos"
                  value={custom}
                  onChange={(e) => setCustom(e.target.value)}
                  className={cx("w-28", controlClass)}
                />
              )}
            </div>
            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">Channels list newest first. "All" reads every page, up to 2000 videos.</p>
          </div>
          <FormError message={localError ?? previewMut.error?.message} />
          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" loading={previewMut.isPending}>
              Preview videos
            </Button>
          </div>
        </form>
      )}
    </Modal>
  );
}
