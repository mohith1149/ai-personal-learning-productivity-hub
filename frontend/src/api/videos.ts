import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, qs } from "./client";

export type VideoStatus = "unwatched" | "watching" | "completed";
export type VideoView = "all" | "open" | "completed";

export type Video = {
  id: number;
  playlist_id: number;
  title: string;
  url: string | null;
  youtube_video_id: string | null;
  description: string | null;
  category: string | null;
  status: VideoStatus;
  position: number;
  completed_at: string | null;
  notes: string | null;
  created_at: string;
};

export type Playlist = {
  id: number;
  name: string;
  source_url: string | null;
  youtube_playlist_id: string | null;
  description: string | null;
  daily_target: number;
  active: boolean;
  total_videos: number;
  completed_videos: number;
  percent: number;
  watched_today: number;
  remaining_today: number;
  next_video: Video | null;
  created_at: string;
};

export type TodayPlan = { daily_target: number; watched_today: number; remaining_today: number; target_met: boolean; up_next: Video[] };
export type VideoList = { items: Video[]; total: number };
export type BulkResult = { added: number; duplicates: number; invalid: string[] };

export type PlaylistInput = {
  name: string;
  source_url?: string | null;
  description?: string | null;
  daily_target?: number;
  active?: boolean;
};
export type VideoInput = { title: string; url?: string | null; description?: string | null; category?: string | null; notes?: string | null };

const ROOT = ["videos"] as const;

export const usePlaylists = () => useQuery({ queryKey: [...ROOT, "playlists"], queryFn: () => api<Playlist[]>("/video-playlists") });

export const useToday = (playlistId: number | undefined) =>
  useQuery({
    queryKey: [...ROOT, "today", playlistId],
    queryFn: () => api<TodayPlan>(`/video-playlists/${playlistId}/today`),
    enabled: playlistId !== undefined,
  });

export const useVideos = (playlistId: number | undefined, view: VideoView, q: string) =>
  useQuery({
    queryKey: [...ROOT, "list", playlistId, view, q],
    queryFn: () => api<VideoList>(`/video-playlists/${playlistId}/videos${qs({ view, q, limit: 500 })}`),
    enabled: playlistId !== undefined,
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
export const useDeleteVideo = () => useInvalidating((id: number) => api<void>(`/videos/${id}`, { method: "DELETE" }));
export const useVideoAction = () =>
  useInvalidating(({ id, action }: { id: number; action: "start" | "complete" | "uncomplete" }) =>
    api<Video>(`/videos/${id}/${action}`, { method: "POST" }));
export const useMoveVideo = () =>
  useInvalidating(({ id, direction }: { id: number; direction: "up" | "down" }) =>
    api<Video>(`/videos/${id}/move`, { method: "POST", body: { direction } }));
