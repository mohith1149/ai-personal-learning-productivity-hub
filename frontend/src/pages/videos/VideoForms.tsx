import { useState, type FormEvent } from "react";
import {
  useAddVideo,
  useBulkVideos,
  useCreatePlaylist,
  useUpdatePlaylist,
  useUpdateVideo,
  type BulkResult,
  type Playlist,
  type RecommendOrder,
  type Video,
} from "../../api/videos";
import { FormError, SelectInput, TextArea, TextInput } from "../../components/forms";
import { Modal } from "../../components/Modal";
import { Button } from "../../components/ui";

/** Create or edit a collection (hand-made, or the settings of an imported channel/playlist). */
export function PlaylistForm({
  playlist,
  onClose,
  onSaved,
}: {
  playlist: Playlist | null;
  onClose: () => void;
  onSaved?: (p: Playlist) => void;
}) {
  const create = useCreatePlaylist();
  const update = useUpdatePlaylist();
  const [f, setF] = useState({
    name: playlist?.name ?? "",
    source_url: playlist?.source_url ?? "",
    description: playlist?.description ?? "",
    daily_target: String(playlist?.daily_target ?? 1),
    recommend_order: playlist?.recommend_order ?? ("oldest" as RecommendOrder),
    active: playlist?.active ?? true,
  });
  const [localError, setLocalError] = useState<string | null>(null);
  const pending = create.isPending || update.isPending;
  const serverError = (create.error ?? update.error)?.message ?? null;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setLocalError(null);
    if (!f.name.trim()) return setLocalError("Please give the playlist a name.");
    const target = Number(f.daily_target);
    if (!Number.isInteger(target) || target < 1 || target > 50) return setLocalError("The daily target must be a whole number from 1 to 50.");
    const body = {
      name: f.name.trim(),
      source_url: f.source_url.trim() || null,
      description: f.description.trim() || null,
      daily_target: target,
      active: f.active,
      recommend_order: f.recommend_order,
    };
    const done = (p: Playlist) => {
      onSaved?.(p);
      onClose();
    };
    if (playlist) update.mutate({ id: playlist.id, body }, { onSuccess: done });
    else create.mutate(body, { onSuccess: done });
  };

  return (
    <Modal title={playlist ? "Edit playlist" : "New playlist"} onClose={onClose}>
      <form onSubmit={submit} className="space-y-4" noValidate>
        <TextInput label="Name" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} maxLength={120} required />
        <TextInput
          label="Link"
          type="url"
          placeholder="https://…"
          value={f.source_url}
          onChange={(e) => setF({ ...f, source_url: e.target.value })}
          hint="Optional. Must start with http:// or https://"
        />
        <TextInput
          label="Videos to watch per day"
          type="number"
          min={1}
          max={50}
          value={f.daily_target}
          onChange={(e) => setF({ ...f, daily_target: e.target.value })}
        />
        <SelectInput
          label="Recommend videos"
          value={f.recommend_order}
          onChange={(e) => setF({ ...f, recommend_order: e.target.value as RecommendOrder })}
          hint="Which unwatched video comes next. Completed videos are never recommended."
        >
          <option value="oldest">Oldest published first</option>
          <option value="newest">Newest published first</option>
          <option value="manual">My own order</option>
        </SelectInput>
        <TextArea label="Description" value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} />
        <label className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300">
          <input type="checkbox" checked={f.active} onChange={(e) => setF({ ...f, active: e.target.checked })} />
          Active (inactive playlists are left out of recommendations)
        </label>
        <FormError message={localError ?? serverError} />
        <div className="flex justify-end gap-2 pt-1">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={pending}>
            {playlist ? "Save changes" : "Create playlist"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

/** Add one video, or edit an existing one. */
export function VideoForm({ playlistId, video, onClose }: { playlistId: number; video: Video | null; onClose: () => void }) {
  const add = useAddVideo();
  const update = useUpdateVideo();
  const [f, setF] = useState({
    title: video?.title ?? "",
    url: video?.url ?? "",
    category: video?.category ?? "",
    description: video?.description ?? "",
    notes: video?.notes ?? "",
  });
  const [localError, setLocalError] = useState<string | null>(null);
  const pending = add.isPending || update.isPending;
  const serverError = (add.error ?? update.error)?.message ?? null;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setLocalError(null);
    if (!f.title.trim()) return setLocalError("Please give the video a title.");
    const body = {
      title: f.title.trim(),
      url: f.url.trim() || null,
      category: f.category.trim() || null,
      description: f.description.trim() || null,
      notes: f.notes.trim() || null,
    };
    if (video) update.mutate({ id: video.id, body }, { onSuccess: onClose });
    else add.mutate({ playlistId, body }, { onSuccess: onClose });
  };

  return (
    <Modal title={video ? "Edit video" : "Add video"} onClose={onClose}>
      <form onSubmit={submit} className="space-y-4" noValidate>
        <TextInput label="Title" value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} maxLength={300} required />
        <TextInput
          label="Link"
          type="url"
          placeholder="https://youtu.be/…"
          value={f.url}
          onChange={(e) => setF({ ...f, url: e.target.value })}
          hint={'A single video link. For a playlist or channel use "Import from YouTube".'}
        />
        <TextInput label="Category" placeholder="e.g. System design" value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })} maxLength={80} />
        <TextArea label="Description or topic" value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} />
        <TextArea label="Notes" value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} />
        <FormError message={localError ?? serverError} />
        <div className="flex justify-end gap-2 pt-1">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={pending}>
            {video ? "Save changes" : "Add video"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

/** Paste many links at once, one per line. The server reports what was added, skipped as duplicate, or rejected. */
export function PasteVideosModal({ playlistId, onClose }: { playlistId: number; onClose: () => void }) {
  const bulk = useBulkVideos();
  const [text, setText] = useState("");
  const [category, setCategory] = useState("");
  const [result, setResult] = useState<BulkResult | null>(null);
  const lines = text.split("\n").map((l) => l.trim()).filter(Boolean);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (lines.length === 0) return;
    bulk.mutate({ playlistId, lines, category: category.trim() || null }, { onSuccess: setResult });
  };

  return (
    <Modal title="Paste video links" onClose={onClose} size="lg">
      {result ? (
        <div className="space-y-3" role="status">
          <p className="text-sm text-slate-700 dark:text-slate-300">
            Added <strong>{result.added}</strong> video{result.added === 1 ? "" : "s"}
            {result.linked > 0 && <>, linked {result.linked} already in your library</>}
            {result.duplicates > 0 && <>, skipped {result.duplicates} already in the playlist</>}
            {result.invalid.length > 0 && <>, couldn't read {result.invalid.length} line{result.invalid.length === 1 ? "" : "s"}</>}.
          </p>
          {result.invalid.length > 0 && (
            <ul className="list-disc pl-5 text-sm text-red-600 dark:text-red-400">
              {result.invalid.map((l, i) => (
                <li key={i} className="break-all">
                  {l}
                </li>
              ))}
            </ul>
          )}
          <div className="flex justify-end">
            <Button onClick={onClose}>Done</Button>
          </div>
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-4" noValidate>
          <TextArea
            label="Links, one per line"
            rows={8}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={"https://youtu.be/…\nHow DNS works | https://www.youtube.com/watch?v=…"}
            hint='Each line is a link, or "Title | link". Without a title one is generated from the link. Videos you already added are skipped. To fetch a whole playlist or channel, use "Import from YouTube" instead.'
          />
          <TextInput label="Category for all of these (optional)" value={category} onChange={(e) => setCategory(e.target.value)} maxLength={80} />
          <FormError message={bulk.error?.message} />
          <div className="flex items-center justify-between gap-2 pt-1">
            <span className="text-sm text-slate-500 dark:text-slate-400" aria-live="polite">
              {lines.length === 0 ? "" : `${lines.length} line${lines.length === 1 ? "" : "s"}`}
            </span>
            <div className="flex gap-2">
              <Button type="button" variant="secondary" onClick={onClose}>
                Cancel
              </Button>
              <Button type="submit" loading={bulk.isPending} disabled={lines.length === 0 || lines.length > 200}>
                Add videos
              </Button>
            </div>
          </div>
          {lines.length > 200 && <FormError message="Paste at most 200 lines at a time." />}
        </form>
      )}
    </Modal>
  );
}
