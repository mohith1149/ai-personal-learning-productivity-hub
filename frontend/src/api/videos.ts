import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, qs } from "./client";

export type VideoStatus = "unwatched" | "watching" | "completed";
export type VideoView = "all" | "open" | "completed" | "removed";
export type VideoSort = "recommended" | "newest" | "oldest" | "completed" | "added";
export type RecommendOrder = "oldest" | "newest" | "manual";
export type PlaylistKind = "collection" | "playlist" | "channel";

/** The labels the tracker shows for the three stored statuses. */
export const STATUS_LABEL: Record<VideoStatus, string> = { unwatched: "Not started", watching: "In progress", completed: "Completed" };

/** One video in the user's library. A YouTube video exists once; `playlist_ids` lists the collections it belongs to. */
export type Video = {
  id: number;
  title: string;
  url: string | null;
  youtube_video_id: string | null;
  description: string | null;
  category: string | null;
  status: VideoStatus;
  completed_at: string | null;
  notes: string | null;
  thumbnail_url: string | null;
  duration_seconds: number | null;
  published_at: string | null;
  channel_id: string | null;
  channel_title: string | null;
  removed_at: string | null;
  created_at: string; // date added
  playlist_ids: number[];
};

export type Playlist = {
  id: number;
  name: string;
  kind: PlaylistKind;
  source_url: string | null;
  youtube_playlist_id: string | null;
  youtube_channel_id: string | null;
  thumbnail_url: string | null;
  description: string | null;
  daily_target: number;
  active: boolean;
  recommend_order: RecommendOrder;
  reported_total: number | null; // what YouTube reported; null = unavailable
  retrieved_count: number; // how many the last fetch retrieved
  total_videos: number; // in the library
  completed_videos: number;
  in_progress_videos: number;
  unwatched_videos: number;
  percent: number;
  watched_today: number;
  remaining_today: number;
  next_video: Video | null;
  created_at: string;
};

export type LibraryStats = {
  total: number;
  completed: number;
  in_progress: number;
  unwatched: number;
  percent: number;
  removed: number;
  next_video: Video | null;
};

export type TodayPlan = { daily_target: number; watched_today: number; remaining_today: number; target_met: boolean; up_next: Video[] };
export type VideoList = { items: Video[]; total: number };
export type BulkResult = { added: number; linked: number; duplicates: number; invalid: string[] };

export type PlaylistInput = {
  name: string;
  source_url?: string | null;
  description?: string | null;
  daily_target?: number;
  active?: boolean;
  recommend_order?: RecommendOrder;
};
export type VideoInput = { title: string; url?: string | null; description?: string | null; category?: string | null; notes?: string | null };

export type VideoFilters = { view: VideoView; status: VideoStatus | ""; sort: VideoSort; q: string };

const ROOT = ["videos"] as const;

export const usePlaylists = () => useQuery({ queryKey: [...ROOT, "playlists"], queryFn: () => api<Playlist[]>("/video-playlists") });

export const useLibraryStats = (order: "oldest" | "newest") =>
  useQuery({ queryKey: [...ROOT, "stats", order], queryFn: () => api<LibraryStats>(`/videos/stats${qs({ order })}`) });

export const useToday = (playlistId: number | undefined) =>
  useQuery({
    queryKey: [...ROOT, "today", playlistId],
    queryFn: () => api<TodayPlan>(`/video-playlists/${playlistId}/today`),
    enabled: playlistId !== undefined,
  });

/** `playlistId` undefined = the whole library. */
export const useVideos = (playlistId: number | undefined, f: VideoFilters) =>
  useQuery({
    queryKey: [...ROOT, "list", playlistId ?? "all", f],
    queryFn: () => {
      const path = playlistId === undefined ? "/videos" : `/video-playlists/${playlistId}/videos`;
      return api<VideoList>(`${path}${qs({ view: f.view, status: f.status, sort: f.sort, q: f.q, limit: 500 })}`);
    },
  });

/** Every change can affect counts, "up next" and the lists, so all video queries are refreshed after a mutation. */
function useInvalidating<TVars, TData>(fn: (v: TVars) => Promise<TData>) {
  const qc = useQueryClient();
  return useMutation({ mutationFn: fn, onSuccess: () => qc.invalidateQueries({ queryKey: ROOT }) });
}

export const useCreatePlaylist = () => useInvalidating((body: PlaylistInput) => api<Playlist>("/video-playlists", { method: "POST", body }));
export const useUpdatePlaylist = () =>
  useInvalidating(({ id, body }: { id: number; body: Partial<PlaylistInput> }) => api<Playlist>(`/video-playlists/${id}`, { method: "PATCH", body }));
export const useDeletePlaylist = () => useInvalidating((id: number) => api<void>(`/video-playlists/${id}`, { method: "DELETE" }));

export const useAddVideo = () =>
  useInvalidating(({ playlistId, body }: { playlistId: number; body: VideoInput }) =>
    api<Video>(`/video-playlists/${playlistId}/videos`, { method: "POST", body }));
export const useBulkVideos = () =>
  useInvalidating(({ playlistId, lines, category }: { playlistId: number; lines: string[]; category?: string | null }) =>
    api<BulkResult>(`/video-playlists/${playlistId}/bulk-videos`, { method: "POST", body: { lines, category: category || null } }));
export const useUpdateVideo = () =>
  useInvalidating(({ id, body }: { id: number; body: Partial<VideoInput> }) => api<Video>(`/videos/${id}`, { method: "PATCH", body }));
/** Permanent: erases the video from the library. Never touches YouTube. */
export const useDeleteVideo = () => useInvalidating((id: number) => api<void>(`/videos/${id}`, { method: "DELETE" }));
export const useVideoAction = () =>
  useInvalidating(({ id, action }: { id: number; action: "start" | "complete" | "uncomplete" | "remove" | "restore" }) =>
    api<Video>(`/videos/${id}/${action}`, { method: "POST" }));
export const useSetStatus = () =>
  useInvalidating(({ id, status }: { id: number; status: VideoStatus }) => api<Video>(`/videos/${id}/status`, { method: "POST", body: { status } }));
export const useMoveVideo = () =>
  useInvalidating(({ id, direction, playlistId }: { id: number; direction: "up" | "down"; playlistId: number }) =>
    api<Video>(`/videos/${id}/move`, { method: "POST", body: { direction, playlist_id: playlistId } }));
