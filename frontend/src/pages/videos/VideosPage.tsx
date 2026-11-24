import { Check, ClipboardPaste, CirclePlay, Download, ExternalLink, Pencil, Plus, Search, Trash2 } from "lucide-react";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useAuthStatus } from "../../api/auth";
import {
  STATUS_LABEL,
  useDeletePlaylist,
  useLibraryStats,
  usePlaylists,
  useToday,
  useVideoAction,
  useVideos,
  type LibraryStats,
  type Playlist,
  type Video,
  type VideoFilters,
  type VideoSort,
  type VideoStatus,
} from "../../api/videos";
import { controlClass } from "../../components/forms";
import { ConfirmDialog } from "../../components/Modal";
import { Badge, Button, Card, EmptyState, ErrorNotice, PageHeader, ProgressBar, Spinner, cx } from "../../components/ui";
import { countOrUnavailable, formatDate } from "../../lib/format";
import { ImportModal } from "./ImportModal";
import { Thumbnail, VideoCard } from "./VideoCard";
import { PasteVideosModal, PlaylistForm, VideoForm } from "./VideoForms";

const SORTS: { key: VideoSort; label: string }[] = [
  { key: "recommended", label: "Recommended order" },
  { key: "newest", label: "Newest first" },
  { key: "oldest", label: "Oldest first" },
  { key: "completed", label: "Recently completed" },
  { key: "added", label: "Recently added" },
];

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <dt className="text-xs text-slate-500 dark:text-slate-400">{label}</dt>
      <dd className="text-lg font-semibold tabular-nums text-slate-900 dark:text-white">{value}</dd>
    </div>
  );
}

/* ---------------------------------- overall + recommendation ---------------------------------- */

function Overview({ stats }: { stats: LibraryStats }) {
  return (
    <Card aria-label="Overall progress">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h2 className="text-sm font-semibold text-slate-900 dark:text-white">Overall progress</h2>
        <span className="text-sm tabular-nums text-slate-600 dark:text-slate-300">{stats.percent}%</span>
      </div>
      <div className="mt-2">
        <ProgressBar percent={stats.percent} label="Overall progress" />
      </div>
      <dl className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="In library" value={stats.total} />
        <Stat label="Completed" value={stats.completed} />
        <Stat label="In progress" value={stats.in_progress} />
        <Stat label="Not started" value={stats.unwatched} />
      </dl>
    </Card>
  );
}

/** Next video to watch: the selected collection's own order when one is open, else the whole library by publish date. */
function UpNext({ timeZone, playlist }: { timeZone: string; playlist?: Playlist }) {
  const [order, setOrder] = useState<"oldest" | "newest">("oldest");
  const stats = useLibraryStats(order);
  const action = useVideoAction();
  const v = playlist ? playlist.next_video : stats.data?.next_video;
  return (
    <Card aria-label="Recommended next video">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-slate-900 dark:text-white">{playlist ? `Watch next in ${playlist.name}` : "Watch next"}</h2>
        {!playlist && <select aria-label="Recommendation order" value={order} onChange={(e) => setOrder(e.target.value as "oldest" | "newest")} className={cx("w-44 py-1 text-xs", controlClass)}>
          <option value="oldest">Oldest published first</option>
          <option value="newest">Newest published first</option>
        </select>}
      </div>
      {stats.isError ? (
        <ErrorNotice error={stats.error} onRetry={() => stats.refetch()} />
      ) : !stats.data ? (
        <Spinner label="Finding your next video…" />
      ) : !v ? (
        <p className="mt-3 text-sm text-slate-500 dark:text-slate-400">
          {stats.data.total === 0 ? "Import or add videos to get a recommendation." : "Nothing left to watch. Every video in your library is completed."}
        </p>
      ) : (
        <div className="mt-3 flex flex-wrap gap-4">
          <Thumbnail video={v} className="w-44 shrink-0" />
          <div className="min-w-0 flex-1">
            <p className="line-clamp-2 text-sm font-semibold text-slate-900 dark:text-white">{v.title}</p>
            <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
              {formatDate(v.published_at, timeZone) ? `Published ${formatDate(v.published_at, timeZone)}` : "No publish date"}
              {v.channel_title && <> · {v.channel_title}</>}
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {v.url && (
                <a
                  href={v.url}
                  target="_blank"
                  rel="noreferrer noopener"
                  aria-label={`Watch ${v.title} next`}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
                >
                  Watch <ExternalLink className="h-3.5 w-3.5" aria-hidden />
                </a>
              )}
              <Button icon={Check} loading={action.isPending} onClick={() => action.mutate({ id: v.id, action: "complete" })} aria-label={`Mark ${v.title} as completed (next)`}>
                Mark completed
              </Button>
            </div>
            {action.error && (
              <p role="alert" className="mt-2 text-sm text-red-600 dark:text-red-400">
                {action.error.message}
              </p>
            )}
          </div>
        </div>
      )}
    </Card>
  );
}

/* ---------------------------------- today (daily target) ---------------------------------- */

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
          {playlist.total_videos === 0 ? "Add videos to get a daily list." : "Every video in this playlist is completed."}
        </p>
      ) : (
        <ul className="mt-3 divide-y divide-slate-100 dark:divide-slate-800" aria-label="Up next today">
          {t.up_next.map((v) => (
            <li key={v.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
              <p className="min-w-0 truncate text-sm font-medium text-slate-900 dark:text-white">{v.title}</p>
              <div className="flex items-center gap-3">
                {v.url && (
                  <a
                    href={v.url}
                    target="_blank"
                    rel="noreferrer noopener"
                    aria-label={`Open ${v.title}`}
                    className="inline-flex items-center gap-1 text-sm text-brand-600 hover:underline dark:text-brand-400"
                  >
                    Open <ExternalLink className="h-3.5 w-3.5" aria-hidden />
                  </a>
                )}
                <Button
                  icon={Check}
                  variant="secondary"
                  loading={action.isPending && action.variables?.id === v.id}
                  onClick={() => action.mutate({ id: v.id, action: "complete" })}
                  aria-label={`Mark ${v.title} as watched today`}
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

/* ---------------------------------- collection overview ---------------------------------- */

function CollectionOverview({ playlist, onEdit, onDelete }: { playlist: Playlist; onEdit: () => void; onDelete: () => void }) {
  const imported = playlist.kind !== "collection";
  return (
    <Card aria-label={`${playlist.name} overview`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 gap-3">
          {playlist.thumbnail_url && <img src={playlist.thumbnail_url} alt="" referrerPolicy="no-referrer" className="h-14 w-14 shrink-0 rounded-full object-cover" />}
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="truncate text-lg font-semibold text-slate-900 dark:text-white">{playlist.name}</h2>
              {playlist.kind !== "collection" && <Badge tone="brand">{playlist.kind === "channel" ? "Channel" : "YouTube playlist"}</Badge>}
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
        </div>
        <div className="flex gap-1">
          <Button variant="secondary" icon={Pencil} onClick={onEdit}>
            Edit
          </Button>
          <Button variant="ghost" icon={Trash2} onClick={onDelete} aria-label={`Delete playlist ${playlist.name}`}>
            Delete
          </Button>
        </div>
      </div>

      <div className="mt-4">
        <ProgressBar percent={playlist.percent} label={`${playlist.name} progress`} />
        <div className="mt-1.5 flex justify-between text-xs text-slate-500 dark:text-slate-400">
          <span>{playlist.total_videos === 0 ? "No videos in the library yet" : `${playlist.completed_videos} of ${playlist.total_videos} completed`}</span>
          <span className="tabular-nums">{playlist.percent}%</span>
        </div>
      </div>

      <dl className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        {imported && <Stat label="On YouTube" value={countOrUnavailable(playlist.reported_total)} />}
        {imported && <Stat label="Retrieved" value={playlist.retrieved_count} />}
        <Stat label="In library" value={playlist.total_videos} />
        <Stat label="Completed" value={playlist.completed_videos} />
        <Stat label="In progress" value={playlist.in_progress_videos} />
        <Stat label="Not started" value={playlist.unwatched_videos} />
      </dl>
    </Card>
  );
}

/* ---------------------------------- the grid ---------------------------------- */

function Library({ playlist, timeZone, stats }: { playlist: Playlist | undefined; timeZone: string; stats: LibraryStats | undefined }) {
  const [showRemoved, setShowRemoved] = useState(false);
  const [status, setStatus] = useState<VideoStatus | "">("");
  const [sort, setSort] = useState<VideoSort>("recommended");
  const [search, setSearch] = useState("");
  const [videoForm, setVideoForm] = useState<{ video: Video | null } | null>(null);
  const [pasting, setPasting] = useState(false);

  const q = search.trim();
  const filters: VideoFilters = { view: showRemoved ? "removed" : "all", status, sort, q };
  const videos = useVideos(playlist?.id, filters);
  const items = videos.data?.items ?? [];
  const filtered = Boolean(q || status);
  const canReorder = playlist?.recommend_order === "manual" && sort === "recommended" && !filtered && !showRemoved;

  return (
    <section className="mt-6" aria-label="Videos">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div role="tablist" aria-label="Video views" className="flex gap-1">
          {[
            { removed: false, label: "Library" },
            { removed: true, label: `Removed${stats ? ` (${stats.removed})` : ""}` },
          ].map((t) => (
            <button
              key={t.label}
              role="tab"
              aria-selected={showRemoved === t.removed}
              onClick={() => setShowRemoved(t.removed)}
              className={cx(
                "rounded-lg px-3 py-1.5 text-sm font-medium transition",
                showRemoved === t.removed ? "bg-brand-600 text-white" : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800",
              )}
            >
              {t.label}
            </button>
          ))}
        </div>
        {playlist && (
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" icon={ClipboardPaste} onClick={() => setPasting(true)}>
              Paste links
            </Button>
            <Button icon={Plus} onClick={() => setVideoForm({ video: null })}>
              Add video
            </Button>
          </div>
        )}
      </div>

      <div className="mb-4 flex flex-wrap gap-2">
        <div className="relative min-w-48 flex-1">
          <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400" aria-hidden />
          <input type="search" aria-label="Search videos" placeholder="Search by title" value={search} onChange={(e) => setSearch(e.target.value)} className={cx("w-full pl-9", controlClass)} />
        </div>
        <select aria-label="Filter by status" value={status} onChange={(e) => setStatus(e.target.value as VideoStatus | "")} className={cx("w-40", controlClass)}>
          <option value="">All statuses</option>
          {(Object.keys(STATUS_LABEL) as VideoStatus[]).map((s) => (
            <option key={s} value={s}>
              {STATUS_LABEL[s]}
            </option>
          ))}
        </select>
        <select aria-label="Sort videos" value={sort} onChange={(e) => setSort(e.target.value as VideoSort)} className={cx("w-48", controlClass)}>
          {SORTS.map((s) => (
            <option key={s.key} value={s.key}>
              {s.label}
            </option>
          ))}
        </select>
      </div>

      {videos.isPending ? (
        <Spinner label="Loading videos…" />
      ) : videos.isError ? (
        <ErrorNotice error={videos.error} onRetry={() => videos.refetch()} />
      ) : items.length === 0 ? (
        <EmptyState
          icon={CirclePlay}
          title={filtered ? "No videos match" : showRemoved ? "Nothing removed" : "No videos yet"}
        >
          {filtered
            ? "Try a different search or filter."
            : showRemoved
              ? "Videos you remove from the library show up here so you can restore them."
              : "Import a YouTube channel or playlist, paste links, or add a video by hand."}
        </EmptyState>
      ) : (
        <>
          <p className="mb-2 text-xs text-slate-500 dark:text-slate-400" aria-live="polite">
            {videos.data!.total} video{videos.data!.total === 1 ? "" : "s"}
          </p>
          <ul aria-label="Video library" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {items.map((v, i) => (
              <VideoCard
                key={v.id}
                video={v}
                timeZone={timeZone}
                playlistId={playlist?.id}
                canReorder={canReorder}
                isFirst={i === 0}
                isLast={i === items.length - 1}
                onEdit={(video) => setVideoForm({ video })}
              />
            ))}
          </ul>
        </>
      )}

      {videoForm && playlist && <VideoForm playlistId={playlist.id} video={videoForm.video} onClose={() => setVideoForm(null)} />}
      {videoForm && !playlist && videoForm.video && <VideoForm playlistId={videoForm.video.playlist_ids[0] ?? 0} video={videoForm.video} onClose={() => setVideoForm(null)} />}
      {pasting && playlist && <PasteVideosModal playlistId={playlist.id} onClose={() => setPasting(false)} />}
    </section>
  );
}

/* ---------------------------------- page ---------------------------------- */

export function VideosPage() {
  const [params, setParams] = useSearchParams();
  const playlists = usePlaylists();
  const user = useAuthStatus().data?.user;
  const timeZone = user?.timezone ?? "UTC";
  const stats = useLibraryStats("oldest");
  const [creating, setCreating] = useState(false);
  const [importing, setImporting] = useState(false);
  const [editing, setEditing] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const delPlaylist = useDeletePlaylist();

  const list = playlists.data ?? [];
  const wanted = Number(params.get("playlist"));
  const selected = list.find((p) => p.id === wanted); // none selected = the whole library
  const select = (id: number | null) => setParams(id === null ? {} : { playlist: String(id) }, { replace: true });

  const tab = (label: string, active: boolean, onClick: () => void) => (
    <button
      key={label}
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={cx(
        "shrink-0 rounded-lg px-3 py-1.5 text-sm font-medium transition",
        active ? "bg-brand-600 text-white" : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800",
      )}
    >
      {label}
    </button>
  );

  return (
    <>
      <PageHeader
        title="Videos"
        description="Your video library. Import a YouTube channel or playlist, pick what you want, and track what you've completed. A video only counts as completed when you mark it."
        actions={
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" icon={Plus} onClick={() => setCreating(true)}>
              New playlist
            </Button>
            <Button icon={Download} onClick={() => setImporting(true)}>
              Import from YouTube
            </Button>
          </div>
        }
      />

      {playlists.isPending ? (
        <Spinner label="Loading playlists…" />
      ) : playlists.isError ? (
        <ErrorNotice error={playlists.error} onRetry={() => playlists.refetch()} />
      ) : (
        <>
          {stats.data && (
            <div className="mb-4 grid gap-4 lg:grid-cols-2">
              <Overview stats={stats.data} />
              <UpNext timeZone={timeZone} playlist={selected} />
            </div>
          )}

          <div role="tablist" aria-label="Collections" className="-mx-1 mb-4 flex gap-1 overflow-x-auto px-1 pb-1">
            {tab("All videos", !selected, () => select(null))}
            {list.map((p) => tab(p.name, selected?.id === p.id, () => select(p.id)))}
          </div>

          {selected && (
            <div className="space-y-4">
              <CollectionOverview playlist={selected} onEdit={() => setEditing(true)} onDelete={() => setConfirmDelete(true)} />
              <TodayCard playlist={selected} />
            </div>
          )}

          <Library key={selected?.id ?? "all"} playlist={selected} timeZone={timeZone} stats={stats.data} />
        </>
      )}

      {creating && <PlaylistForm playlist={null} onClose={() => setCreating(false)} onSaved={(p) => select(p.id)} />}
      {editing && selected && <PlaylistForm playlist={selected} onClose={() => setEditing(false)} />}
      {importing && <ImportModal onClose={() => setImporting(false)} onImported={(r) => select(r.collection.id)} />}
      {confirmDelete && selected && (
        <ConfirmDialog
          title="Delete playlist?"
          message={
            <>
              <strong>{selected.name}</strong> will be deleted. Its {selected.total_videos} video{selected.total_videos === 1 ? "" : "s"} stay in your library
              (with their progress), and nothing happens on YouTube.
            </>
          }
          busy={delPlaylist.isPending}
          error={delPlaylist.error?.message}
          onCancel={() => {
            setConfirmDelete(false);
            delPlaylist.reset();
          }}
          onConfirm={() =>
            delPlaylist.mutate(selected.id, {
              onSuccess: () => {
                setConfirmDelete(false);
                select(null);
              },
            })
          }
        />
      )}
    </>
  );
}
