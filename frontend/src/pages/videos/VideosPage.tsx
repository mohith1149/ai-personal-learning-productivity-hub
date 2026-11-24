import { Check, ChevronDown, ChevronUp, ClipboardPaste, ExternalLink, Pencil, Play, Plus, Search, Trash2, CirclePlay } from "lucide-react";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useAuthStatus } from "../../api/auth";
import {
  useDeletePlaylist,
  useDeleteVideo,
  useMoveVideo,
  usePlaylists,
  useToday,
  useVideoAction,
  useVideos,
  type Playlist,
  type Video,
  type VideoView,
} from "../../api/videos";
import { controlClass } from "../../components/forms";
import { ConfirmDialog } from "../../components/Modal";
import { Badge, Button, Card, EmptyState, ErrorNotice, PageHeader, ProgressBar, Spinner, StatusBadge, cx } from "../../components/ui";
import { formatDay, todayIn } from "../../lib/dates";
import { BYTEBYTEGO_PRESET, PasteVideosModal, PlaylistForm, VideoForm } from "./VideoForms";

const VIEWS: { key: VideoView; label: string }[] = [
  { key: "open", label: "To watch" },
  { key: "completed", label: "Watched" },
  { key: "all", label: "All" },
];

function IconButton({ label, onClick, disabled, danger, children }: { label: string; onClick: () => void; disabled?: boolean; danger?: boolean; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      title={label}
      className={cx(
        "rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 disabled:opacity-30 dark:hover:bg-slate-800",
        danger ? "hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950/40" : "hover:text-slate-800 dark:hover:text-slate-200",
      )}
    >
      {children}
    </button>
  );
}

function OpenLink({ video }: { video: Video }) {
  if (!video.url) return null;
  return (
    <a
      href={video.url}
      target="_blank"
      rel="noreferrer noopener"
      className="inline-flex items-center gap-1 text-sm text-brand-600 hover:underline dark:text-brand-400"
      aria-label={`Open ${video.title}`}
    >
      Open <ExternalLink className="h-3.5 w-3.5" aria-hidden />
    </a>
  );
}

function VideoStatusBadge({ status }: { status: Video["status"] }) {
  return <StatusBadge status={status === "completed" ? "completed" : status === "watching" ? "in_progress" : "not_started"} />;
}

/* ---------------------------------- today ---------------------------------- */

function TodayCard({ playlist }: { playlist: Playlist }) {
  const today = useToday(playlist.id);
  const action = useVideoAction();
  const t = today.data;

  return (
    <Card aria-label="Today's videos">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-slate-900 dark:text-white">Today</h2>
        {t && (
          <span className="text-sm tabular-nums text-slate-600 dark:text-slate-300" aria-label="Today's progress">
            Watched {t.watched_today} of {t.daily_target} today
          </span>
        )}
      </div>

      {today.isError ? (
        <ErrorNotice error={today.error} onRetry={() => today.refetch()} />
      ) : !t ? (
        <Spinner label="Loading today's videos…" />
      ) : t.target_met ? (
        <p role="status" className="mt-3 rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300">
          Today's target is met. Anything more is a bonus.
          {playlist.next_video && (
            <>
              {" "}
              Next in line: <strong>{playlist.next_video.title}</strong>.
            </>
          )}
        </p>
      ) : t.up_next.length === 0 ? (
        <p className="mt-3 text-sm text-slate-500 dark:text-slate-400">
          {playlist.total_videos === 0 ? "Add videos to get a daily list." : "Every video in this playlist is watched."}
        </p>
      ) : (
        <ul className="mt-3 divide-y divide-slate-100 dark:divide-slate-800" aria-label="Up next today">
          {t.up_next.map((v) => (
            <li key={v.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-slate-900 dark:text-white">{v.title}</p>
                {v.category && <p className="text-xs text-slate-500 dark:text-slate-400">{v.category}</p>}
              </div>
              <div className="flex items-center gap-3">
                <OpenLink video={v} />
                <Button
                  icon={Check}
                  variant="secondary"
                  loading={action.isPending && action.variables?.id === v.id}
                  onClick={() => action.mutate({ id: v.id, action: "complete" })}
                  aria-label={`Mark ${v.title} as watched`}
                >
                  Watched
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}
      {action.error && (
        <p role="alert" className="mt-2 text-sm text-red-600 dark:text-red-400">
          {action.error.message}
        </p>
      )}
    </Card>
  );
}

/* ---------------------------------- list ---------------------------------- */

type Confirm = { kind: "video"; video: Video } | { kind: "playlist" };

function VideoRow({ video, first, last, timeZone, today, onEdit, onDelete }: {
  video: Video; first: boolean; last: boolean; timeZone: string; today: string; onEdit: () => void; onDelete: () => void;
}) {
  const action = useVideoAction();
  const move = useMoveVideo();
  const done = video.status === "completed";
  const busy = action.isPending || move.isPending;
  const watchedOn = video.completed_at ? formatDay(todayIn(timeZone, new Date(video.completed_at)), today) : null;

  return (
    <li className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2.5">
      <button
        onClick={() => action.mutate({ id: video.id, action: done ? "uncomplete" : "complete" })}
        disabled={busy}
        role="checkbox"
        aria-checked={done}
        aria-label={done ? `Reopen ${video.title}` : `Mark ${video.title} as watched`}
        className={cx(
          "flex h-5 w-5 shrink-0 items-center justify-center rounded border transition disabled:opacity-50",
          done ? "border-emerald-500 bg-emerald-500 text-white" : "border-slate-300 hover:border-brand-500 dark:border-slate-600",
        )}
      >
        {done && <Check className="h-3.5 w-3.5" aria-hidden />}
      </button>
      <div className="min-w-0 flex-1">
        <p className={cx("truncate text-sm font-medium", done ? "text-slate-500 line-through dark:text-slate-500" : "text-slate-900 dark:text-white")}>
          {video.title}
        </p>
        <p className="flex flex-wrap gap-x-3 text-xs text-slate-500 dark:text-slate-400">
          {video.category && <span>{video.category}</span>}
          {watchedOn && <span>Watched {watchedOn}</span>}
          {video.notes && <span className="truncate">Note: {video.notes}</span>}
        </p>
      </div>
      <VideoStatusBadge status={video.status} />
      <OpenLink video={video} />
      <div className="flex items-center">
        {!done && video.status === "unwatched" && (
          <IconButton label={`Start ${video.title}`} onClick={() => action.mutate({ id: video.id, action: "start" })} disabled={busy}>
            <Play className="h-4 w-4" aria-hidden />
          </IconButton>
        )}
        <IconButton label={`Move ${video.title} up`} onClick={() => move.mutate({ id: video.id, direction: "up" })} disabled={busy || first}>
          <ChevronUp className="h-4 w-4" aria-hidden />
        </IconButton>
        <IconButton label={`Move ${video.title} down`} onClick={() => move.mutate({ id: video.id, direction: "down" })} disabled={busy || last}>
          <ChevronDown className="h-4 w-4" aria-hidden />
        </IconButton>
        <IconButton label={`Edit ${video.title}`} onClick={onEdit}>
          <Pencil className="h-4 w-4" aria-hidden />
        </IconButton>
        <IconButton label={`Delete ${video.title}`} onClick={onDelete} danger>
          <Trash2 className="h-4 w-4" aria-hidden />
        </IconButton>
      </div>
      {(action.error || move.error) && (
        <p role="alert" className="basis-full pl-8 text-sm text-red-600 dark:text-red-400">
          {(action.error ?? move.error)!.message}
        </p>
      )}
    </li>
  );
}

function PlaylistView({ playlist, onDeleted }: { playlist: Playlist; onDeleted: () => void }) {
  const user = useAuthStatus().data?.user;
  const timeZone = user?.timezone ?? "UTC";
  const today = todayIn(timeZone);
  const [view, setView] = useState<VideoView>("open");
  const [search, setSearch] = useState("");
  const videos = useVideos(playlist.id, view, search.trim());
  const [editingPlaylist, setEditingPlaylist] = useState(false);
  const [videoForm, setVideoForm] = useState<{ video: Video | null } | null>(null);
  const [pasting, setPasting] = useState(false);
  const [confirm, setConfirm] = useState<Confirm | null>(null);
  const delVideo = useDeleteVideo();
  const delPlaylist = useDeletePlaylist();

  const items = videos.data?.items ?? [];
  const reorderable = view !== "completed" && !search.trim();

  return (
    <>
      <Card aria-label={`${playlist.name} progress`}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h2 className="truncate text-lg font-semibold text-slate-900 dark:text-white">{playlist.name}</h2>
              {!playlist.active && <Badge>Inactive</Badge>}
            </div>
            {playlist.description && <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">{playlist.description}</p>}
            {playlist.source_url && (
              <a
                href={playlist.source_url}
                target="_blank"
                rel="noreferrer noopener"
                className="mt-1 inline-flex items-center gap-1 text-sm text-brand-600 hover:underline dark:text-brand-400"
              >
                Source <ExternalLink className="h-3.5 w-3.5" aria-hidden />
              </a>
            )}
          </div>
          <div className="flex gap-1">
            <Button variant="secondary" icon={Pencil} onClick={() => setEditingPlaylist(true)}>
              Edit
            </Button>
            <Button variant="ghost" icon={Trash2} onClick={() => setConfirm({ kind: "playlist" })} aria-label={`Delete playlist ${playlist.name}`}>
              Delete
            </Button>
          </div>
        </div>
        <div className="mt-4">
          <ProgressBar percent={playlist.percent} label={`${playlist.name} progress`} />
          <div className="mt-1.5 flex justify-between text-xs text-slate-500 dark:text-slate-400">
            <span>
              {playlist.total_videos === 0 ? "No videos added yet" : `${playlist.completed_videos} of ${playlist.total_videos} watched`}
            </span>
            <span className="tabular-nums">{playlist.percent}%</span>
          </div>
        </div>
      </Card>

      <div className="mt-4">
        <TodayCard playlist={playlist} />
      </div>

      <section className="mt-6" aria-label="Videos">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div role="tablist" aria-label="Video views" className="flex gap-1">
            {VIEWS.map(({ key, label }) => (
              <button
                key={key}
                role="tab"
                aria-selected={view === key}
                onClick={() => setView(key)}
                className={cx(
                  "rounded-lg px-3 py-1.5 text-sm font-medium transition",
                  view === key ? "bg-brand-600 text-white" : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800",
                )}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" icon={ClipboardPaste} onClick={() => setPasting(true)}>
              Paste links
            </Button>
            <Button icon={Plus} onClick={() => setVideoForm({ video: null })}>
              Add video
            </Button>
          </div>
        </div>

        <div className="relative mb-3">
          <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400" aria-hidden />
          <input
            type="search"
            aria-label="Search videos"
            placeholder="Search videos"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className={cx("w-full pl-9", controlClass)}
          />
        </div>

        {videos.isPending ? (
          <Spinner label="Loading videos…" />
        ) : videos.isError ? (
          <ErrorNotice error={videos.error} onRetry={() => videos.refetch()} />
        ) : items.length === 0 ? (
          <EmptyState
            icon={CirclePlay}
            title={search.trim() ? "No videos match your search" : view === "completed" ? "Nothing watched yet" : view === "open" ? (playlist.total_videos > 0 ? "Everything is watched" : "No videos yet") : "No videos yet"}
          >
            {search.trim()
              ? "Try a different word."
              : view === "completed"
                ? "Videos you mark as watched will appear here."
                : playlist.total_videos > 0
                  ? "Every video in this playlist is marked watched."
                  : "Paste a list of links, or add videos one at a time."}
          </EmptyState>
        ) : (
          <Card>
            <ul className="divide-y divide-slate-100 dark:divide-slate-800" aria-label="Video list">
              {items.map((v, i) => (
                <VideoRow
                  key={v.id}
                  video={v}
                  first={!reorderable || i === 0}
                  last={!reorderable || i === items.length - 1}
                  timeZone={timeZone}
                  today={today}
                  onEdit={() => setVideoForm({ video: v })}
                  onDelete={() => setConfirm({ kind: "video", video: v })}
                />
              ))}
            </ul>
          </Card>
        )}
      </section>

      {editingPlaylist && <PlaylistForm playlist={playlist} onClose={() => setEditingPlaylist(false)} />}
      {videoForm && <VideoForm playlistId={playlist.id} video={videoForm.video} onClose={() => setVideoForm(null)} />}
      {pasting && <PasteVideosModal playlistId={playlist.id} onClose={() => setPasting(false)} />}
      {confirm && (
        <ConfirmDialog
          title={confirm.kind === "playlist" ? "Delete playlist?" : "Delete video?"}
          message={
            confirm.kind === "playlist" ? (
              <>
                <strong>{playlist.name}</strong> and its {playlist.total_videos} video{playlist.total_videos === 1 ? "" : "s"} (including your watched
                history) will be permanently deleted. This can't be undone.
              </>
            ) : (
              <>
                <strong>{confirm.video.title}</strong> will be permanently deleted.
              </>
            )
          }
          busy={delVideo.isPending || delPlaylist.isPending}
          error={(delVideo.error ?? delPlaylist.error)?.message}
          onCancel={() => {
            setConfirm(null);
            delVideo.reset();
            delPlaylist.reset();
          }}
          onConfirm={() => {
            if (confirm.kind === "video") delVideo.mutate(confirm.video.id, { onSuccess: () => setConfirm(null) });
            else
              delPlaylist.mutate(playlist.id, {
                onSuccess: () => {
                  setConfirm(null);
                  onDeleted();
                },
              });
          }}
        />
      )}
    </>
  );
}

/* ---------------------------------- page ---------------------------------- */

export function VideosPage() {
  const [params, setParams] = useSearchParams();
  const playlists = usePlaylists();
  const [creating, setCreating] = useState<null | "blank" | "bytebytego">(null);

  const list = playlists.data ?? [];
  const wanted = Number(params.get("playlist"));
  const selected = list.find((p) => p.id === wanted) ?? list[0];
  const select = (id: number) => setParams({ playlist: String(id) }, { replace: true });

  return (
    <>
      <PageHeader
        title="Videos"
        description="Playlists with a daily watch target. A video only counts as watched when you mark it, and watched videos are never recommended again."
        actions={
          <Button icon={Plus} onClick={() => setCreating("blank")}>
            New playlist
          </Button>
        }
      />

      {playlists.isPending ? (
        <Spinner label="Loading playlists…" />
      ) : playlists.isError ? (
        <ErrorNotice error={playlists.error} onRetry={() => playlists.refetch()} />
      ) : list.length === 0 ? (
        <EmptyState
          icon={CirclePlay}
          title="No playlists yet"
          action={
            <div className="flex flex-wrap justify-center gap-2">
              <Button onClick={() => setCreating("bytebytego")}>Start a ByteByteGo playlist</Button>
              <Button variant="secondary" icon={Plus} onClick={() => setCreating("blank")}>
                New playlist
              </Button>
            </div>
          }
        >
          Create a playlist, then paste the links of the videos you want to get through. Nothing is added for you.
        </EmptyState>
      ) : (
        <>
          <div role="tablist" aria-label="Playlists" className="-mx-1 mb-4 flex gap-1 overflow-x-auto px-1 pb-1">
            {list.map((p) => (
              <button
                key={p.id}
                role="tab"
                aria-selected={selected?.id === p.id}
                onClick={() => select(p.id)}
                className={cx(
                  "shrink-0 rounded-lg px-3 py-1.5 text-sm font-medium transition",
                  selected?.id === p.id ? "bg-brand-600 text-white" : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800",
                )}
              >
                {p.name}
              </button>
            ))}
          </div>
          {selected && <PlaylistView key={selected.id} playlist={selected} onDeleted={() => setParams({}, { replace: true })} />}
        </>
      )}

      {creating && (
        <PlaylistForm
          playlist={null}
          preset={creating === "bytebytego" ? BYTEBYTEGO_PRESET : undefined}
          onClose={() => setCreating(null)}
          onSaved={(p) => select(p.id)}
        />
      )}
    </>
  );
}
