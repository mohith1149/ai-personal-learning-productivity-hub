import { Check, ChevronLeft, ChevronRight, ExternalLink, ImageOff, NotebookPen, Pencil, RotateCcw, Trash2, X } from "lucide-react";
import { useState } from "react";
import { STATUS_LABEL, useDeleteVideo, useMoveVideo, useSetStatus, useUpdateVideo, useVideoAction, type Video, type VideoStatus } from "../../api/videos";
import { controlClass, FormError, TextArea } from "../../components/forms";
import { ConfirmDialog, Modal } from "../../components/Modal";
import { Badge, Button, StatusBadge, cx } from "../../components/ui";
import { formatDate, formatDuration } from "../../lib/format";

const STATUSES: VideoStatus[] = ["unwatched", "watching", "completed"];

export function Thumbnail({ video, className }: { video: Pick<Video, "thumbnail_url" | "duration_seconds">; className?: string }) {
  const duration = formatDuration(video.duration_seconds);
  return (
    <div className={cx("relative aspect-video overflow-hidden rounded-lg bg-slate-100 dark:bg-slate-800", className)}>
      {video.thumbnail_url ? (
        // Decorative: the title is always shown next to it. Thumbnails are public YouTube image URLs.
        <img src={video.thumbnail_url} alt="" loading="lazy" referrerPolicy="no-referrer" className="h-full w-full object-cover" />
      ) : (
        <div className="flex h-full w-full items-center justify-center text-slate-400" aria-hidden>
          <ImageOff className="h-6 w-6" />
        </div>
      )}
      {duration && (
        <span className="absolute bottom-1 right-1 rounded bg-black/75 px-1.5 py-0.5 text-[11px] font-medium tabular-nums text-white">{duration}</span>
      )}
    </div>
  );
}

function statusTone(s: VideoStatus) {
  return s === "completed" ? "completed" : s === "watching" ? "in_progress" : "not_started";
}

/** Edit just the notes of a video. */
export function NotesModal({ video, onClose }: { video: Video; onClose: () => void }) {
  const update = useUpdateVideo();
  const [notes, setNotes] = useState(video.notes ?? "");
  return (
    <Modal title={`Notes: ${video.title}`} onClose={onClose}>
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          update.mutate({ id: video.id, body: { notes: notes.trim() || null } }, { onSuccess: onClose });
        }}
      >
        <TextArea label="Notes" rows={6} value={notes} onChange={(e) => setNotes(e.target.value)} />
        <FormError message={update.error?.message} />
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={update.isPending}>
            Save notes
          </Button>
        </div>
      </form>
    </Modal>
  );
}

/** Choose between hiding a video (reversible) and erasing it. Neither touches YouTube. */
function RemoveDialog({ video, onClose }: { video: Video; onClose: () => void }) {
  const action = useVideoAction();
  const del = useDeleteVideo();
  const error = action.error ?? del.error;
  return (
    <Modal title="Remove video" onClose={onClose}>
      <div className="space-y-4">
        <p className="text-sm text-slate-700 dark:text-slate-300">
          <strong>{video.title}</strong>
        </p>
        <ul className="space-y-2 text-sm text-slate-600 dark:text-slate-400">
          <li>
            <strong className="text-slate-800 dark:text-slate-200">Remove from library</strong> hides it from your lists, progress and recommendations. You can restore it
            later and your notes are kept.
          </li>
          <li>
            <strong className="text-slate-800 dark:text-slate-200">Delete permanently</strong> erases it and your notes for good.
          </li>
          <li>Nothing happens on YouTube either way.</li>
        </ul>
        <FormError message={error?.message} />
        <div className="flex flex-wrap justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="secondary"
            loading={action.isPending}
            onClick={() => action.mutate({ id: video.id, action: "remove" }, { onSuccess: onClose })}
          >
            Remove from library
          </Button>
          <Button variant="danger" loading={del.isPending} onClick={() => del.mutate(video.id, { onSuccess: onClose })}>
            Delete permanently
          </Button>
        </div>
      </div>
    </Modal>
  );
}

export function VideoCard({
  video,
  timeZone,
  playlistId,
  canReorder,
  isFirst,
  isLast,
  onEdit,
}: {
  video: Video;
  timeZone: string;
  playlistId?: number;
  canReorder: boolean;
  isFirst: boolean;
  isLast: boolean;
  onEdit: (v: Video) => void;
}) {
  const action = useVideoAction();
  const status = useSetStatus();
  const move = useMoveVideo();
  const [notesOpen, setNotesOpen] = useState(false);
  const [removeOpen, setRemoveOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const del = useDeleteVideo();
  const removed = video.removed_at !== null;
  const done = video.status === "completed";
  const busy = action.isPending || status.isPending || move.isPending;
  const published = formatDate(video.published_at, timeZone);
  const completedOn = formatDate(video.completed_at, timeZone);
  const error = action.error ?? status.error ?? move.error;

  return (
    <li className="flex flex-col rounded-xl border border-slate-200 bg-white p-3 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <Thumbnail video={video} />
      <div className="mt-3 flex-1">
        <h3 className={cx("line-clamp-2 text-sm font-semibold", done ? "text-slate-500 dark:text-slate-500" : "text-slate-900 dark:text-white")}>{video.title}</h3>
        <p className="mt-1 flex flex-wrap gap-x-2 text-xs text-slate-500 dark:text-slate-400">
          {published && <span>Published {published}</span>}
          {video.channel_title && <span>{video.channel_title}</span>}
          {video.category && <span>{video.category}</span>}
        </p>
        <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
          Added {formatDate(video.created_at, timeZone)}
          {completedOn && <> · Completed {completedOn}</>}
        </p>
        {video.notes && <p className="mt-1.5 line-clamp-2 text-xs italic text-slate-600 dark:text-slate-400">Note: {video.notes}</p>}
      </div>

      <div className="mt-3 flex items-center justify-between gap-2">
        {removed ? (
          <Badge>Removed</Badge>
        ) : (
          <>
            <StatusBadge status={statusTone(video.status)} />
            <select
              aria-label={`Status of ${video.title}`}
              value={video.status}
              disabled={busy}
              onChange={(e) => status.mutate({ id: video.id, status: e.target.value as VideoStatus })}
              className={cx("w-32 py-1 text-xs", controlClass)}
            >
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {STATUS_LABEL[s]}
                </option>
              ))}
            </select>
          </>
        )}
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-1.5">
        {removed ? (
          <>
            <Button variant="secondary" icon={RotateCcw} loading={action.isPending} onClick={() => action.mutate({ id: video.id, action: "restore" })} aria-label={`Restore ${video.title}`}>
              Restore
            </Button>
            <Button variant="ghost" icon={Trash2} onClick={() => setDeleteOpen(true)} aria-label={`Delete ${video.title} permanently`}>
              Delete permanently
            </Button>
          </>
        ) : (
          <>
            {video.url && (
              <a
                href={video.url}
                target="_blank"
                rel="noreferrer noopener"
                aria-label={`Watch ${video.title}`}
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
              >
                Watch <ExternalLink className="h-3.5 w-3.5" aria-hidden />
              </a>
            )}
            <Button
              variant={done ? "secondary" : "primary"}
              icon={done ? RotateCcw : Check}
              disabled={busy}
              onClick={() => action.mutate({ id: video.id, action: done ? "uncomplete" : "complete" })}
              aria-label={done ? `Reopen ${video.title}` : `Mark ${video.title} as completed`}
              className="px-2.5 py-1.5"
            >
              {done ? "Reopen" : "Mark completed"}
            </Button>
            <button
              onClick={() => setNotesOpen(true)}
              aria-label={`Notes for ${video.title}`}
              title="Notes"
              className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 hover:text-slate-800 dark:hover:bg-slate-800 dark:hover:text-slate-200"
            >
              <NotebookPen className="h-4 w-4" aria-hidden />
            </button>
            <button
              onClick={() => onEdit(video)}
              aria-label={`Edit ${video.title}`}
              title="Edit"
              className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 hover:text-slate-800 dark:hover:bg-slate-800 dark:hover:text-slate-200"
            >
              <Pencil className="h-4 w-4" aria-hidden />
            </button>
            {canReorder && playlistId !== undefined && (
              <>
                <button
                  onClick={() => move.mutate({ id: video.id, direction: "up", playlistId })}
                  disabled={busy || isFirst}
                  aria-label={`Move ${video.title} earlier`}
                  className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 disabled:opacity-30 dark:hover:bg-slate-800"
                >
                  <ChevronLeft className="h-4 w-4" aria-hidden />
                </button>
                <button
                  onClick={() => move.mutate({ id: video.id, direction: "down", playlistId })}
                  disabled={busy || isLast}
                  aria-label={`Move ${video.title} later`}
                  className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 disabled:opacity-30 dark:hover:bg-slate-800"
                >
                  <ChevronRight className="h-4 w-4" aria-hidden />
                </button>
              </>
            )}
            <button
              onClick={() => setRemoveOpen(true)}
              aria-label={`Remove ${video.title}`}
              title="Remove"
              className="ml-auto rounded-lg p-1.5 text-slate-500 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950/40"
            >
              <X className="h-4 w-4" aria-hidden />
            </button>
          </>
        )}
      </div>
      {error && (
        <p role="alert" className="mt-2 text-sm text-red-600 dark:text-red-400">
          {error.message}
        </p>
      )}

      {notesOpen && <NotesModal video={video} onClose={() => setNotesOpen(false)} />}
      {removeOpen && <RemoveDialog video={video} onClose={() => setRemoveOpen(false)} />}
      {deleteOpen && (
        <ConfirmDialog
          title="Delete permanently?"
          confirmLabel="Delete permanently"
          message={
            <>
              <strong>{video.title}</strong> and its notes will be erased for good. Nothing happens on YouTube.
            </>
          }
          busy={del.isPending}
          error={del.error?.message}
          onCancel={() => {
            setDeleteOpen(false);
            del.reset();
          }}
          onConfirm={() => del.mutate(video.id, { onSuccess: () => setDeleteOpen(false) })}
        />
      )}
    </li>
  );
}
