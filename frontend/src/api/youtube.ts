import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type { Playlist, VideoStatus } from "./videos";

export type YouTubeSource = {
  kind: "channel" | "playlist";
  id: string;
  title: string;
  url: string;
  thumbnail_url: string | null;
  total_available: number | null; // null = YouTube did not say; never estimated
  handle: string | null;
  channel_title: string | null;
};

export type PreviewVideo = {
  youtube_video_id: string;
  title: string;
  url: string;
  thumbnail_url: string | null;
  duration_seconds: number | null;
  published_at: string | null;
  channel_title: string | null;
  in_library: boolean;
  removed: boolean;
  status: VideoStatus | null;
};

export type Preview = {
  source: YouTubeSource;
  retrieved: number;
  unavailable: number;
  more_available: boolean;
  already_in_library: number;
  videos: PreviewVideo[];
};

export type ImportResult = { collection: Playlist; created: number; linked: number; already_in_collection: number; unavailable: number };

/** Whether the server has a YouTube API key. The key itself never reaches the browser. */
export const useYouTubeStatus = () => useQuery({ queryKey: ["youtube", "status"], queryFn: () => api<{ configured: boolean }>("/youtube/status") });

/** Read-only: fetches a preview from YouTube. Nothing is saved. `limit` null = all. */
export const usePreview = () => useMutation({ mutationFn: (body: { url: string; limit: number | null }) => api<Preview>("/youtube/preview", { method: "POST", body }) });

export const useImport = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { url: string; video_ids: string[]; retrieved: number }) => api<ImportResult>("/youtube/import", { method: "POST", body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["videos"] }),
  });
};
