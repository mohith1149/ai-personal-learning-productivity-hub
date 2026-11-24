/** Video + YouTube endpoints for the fake API. Mirrors the SERVER'S RESPONSE SHAPES and the derived numbers the UI shows
 *  (progress, watched today, up next). The real rules (recommendation query, de-duplication, timezones, YouTube
 *  paging) are tested in pytest against the real code. */
import type { LibraryStats, Playlist, TodayPlan, Video } from "../api/videos";
import type { Preview, PreviewVideo, YouTubeSource } from "../api/youtube";
import { todayIn } from "../lib/dates";
import { USER, type Fake, type Handler } from "./fakeApi";

let nextId = 9000;
const id = () => nextId++;

export function mkVideo(o: Partial<Video> = {}): Video {
  const n = o.id ?? id();
  return {
    id: n, title: `Video ${n}`, url: null, youtube_video_id: null, description: null, category: null, status: "unwatched",
    completed_at: null, notes: null, thumbnail_url: null, duration_seconds: null, published_at: null, channel_id: null,
    channel_title: null, removed_at: null, created_at: "2026-11-23T00:00:00Z", playlist_ids: [], ...o,
  };
}

export function mkPlaylist(o: Partial<Playlist> = {}): Playlist {
  const n = o.id ?? id();
  return {
    id: n, name: `Playlist ${n}`, kind: "collection", source_url: null, youtube_playlist_id: null, youtube_channel_id: null,
    thumbnail_url: null, description: null, daily_target: 1, active: true, recommend_order: "oldest", reported_total: null,
    retrieved_count: 0, total_videos: 0, completed_videos: 0, in_progress_videos: 0, unwatched_videos: 0, percent: 0,
    watched_today: 0, remaining_today: 1, next_video: null, created_at: "2026-11-23T00:00:00Z", ...o,
  };
}

/** A YouTube video as the preview lists it (newest first, like a channel). */
export function mkYt(n: number, o: Partial<PreviewVideo> = {}): PreviewVideo {
  const idStr = `yt${String(n).padStart(9, "0")}`;
  return {
    youtube_video_id: idStr, title: `YT video ${n}`, url: `https://www.youtube.com/watch?v=${idStr}`, thumbnail_url: `https://i.ytimg.com/vi/${idStr}/mq.jpg`,
    duration_seconds: 600 + n, published_at: new Date(Date.UTC(2024, 0, n)).toISOString(), channel_title: "Fake Channel", in_library: false,
    removed: false, status: null, ...o,
  };
}

export type FakeYouTubeCfg = {
  configured: boolean;
  source: YouTubeSource;
  catalog: PreviewVideo[]; // newest first
  unavailable: number;
};
export type FakeVideos = { playlists: Playlist[]; videos: Video[]; youtube: FakeYouTubeCfg };

const CHANNEL: YouTubeSource = {
  kind: "channel", id: "UCfake", title: "Fake Channel", url: "https://www.youtube.com/channel/UCfake", thumbnail_url: "https://yt3.ggpht.com/x",
  total_available: 120, handle: "@fakechannel", channel_title: "Fake Channel",
};

export function installFakeVideos(fake: Fake, seed: Partial<FakeVideos> = {}): FakeVideos {
  const store: FakeVideos = {
    playlists: seed.playlists ?? [],
    videos: seed.videos ?? [],
    youtube: seed.youtube ?? { configured: true, source: CHANNEL, catalog: Array.from({ length: 120 }, (_, i) => mkYt(120 - i)), unavailable: 0 },
  };
  const json = (data: unknown, status = 200) => Response.json(data, { status });
  const empty = () => new Response(null, { status: 204 });
  const alive = () => store.videos.filter((v) => v.removed_at === null);
  const members = (pid: number) => alive().filter((v) => v.playlist_ids.includes(pid));
  const recommended = (list: Video[], order: string) => {
    const open = list.filter((v) => v.status !== "completed");
    if (order === "manual") return open;
    const ts = (v: Video) => (v.published_at ? Date.parse(v.published_at) : Number.POSITIVE_INFINITY);
    return [...open].sort((a, b) => (order === "newest" ? (b.published_at ? ts(b) : -1) - (a.published_at ? ts(a) : -1) : ts(a) - ts(b)));
  };

  const summarise = (p: Playlist): Playlist => {
    const vs = members(p.id);
    const done = vs.filter((v) => v.status === "completed");
    const prog = vs.filter((v) => v.status === "watching");
    const watched = done.filter((v) => v.completed_at && todayIn(USER.timezone, new Date(v.completed_at)) === todayIn(USER.timezone)).length;
    Object.assign(p, {
      total_videos: vs.length, completed_videos: done.length, in_progress_videos: prog.length, unwatched_videos: vs.length - done.length - prog.length,
      percent: vs.length ? Math.floor((100 * done.length) / vs.length) : 0, watched_today: watched,
      remaining_today: Math.max(p.daily_target - watched, 0), next_video: recommended(vs, p.recommend_order)[0] ?? null,
    });
    return p;
  };
  const playlist = (pid: number) => store.playlists.find((p) => p.id === pid);
  const NF = () => json({ detail: "Playlist not found" }, 404);

  const listVideos = (items: Video[], query: Record<string, string>, order: string) => {
    let out = query.view === "removed" ? store.videos.filter((v) => v.removed_at !== null && items.includes(v)) : items.filter((v) => v.removed_at === null);
    if (query.status) out = out.filter((v) => v.status === query.status);
    if (query.q) out = out.filter((v) => v.title.toLowerCase().includes(query.q.toLowerCase()));
    const ts = (v: Video) => (v.published_at ? Date.parse(v.published_at) : Number.POSITIVE_INFINITY);
    const sort = query.sort || "recommended";
    const mode = sort === "recommended" ? order : sort;
    if (mode === "oldest") out = [...out].sort((a, b) => ts(a) - ts(b));
    else if (mode === "newest") out = [...out].sort((a, b) => (b.published_at ? ts(b) : -1) - (a.published_at ? ts(a) : -1));
    else if (mode === "completed") out = [...out].sort((a, b) => Date.parse(b.completed_at ?? "0") - Date.parse(a.completed_at ?? "0"));
    else if (mode === "added") out = [...out].sort((a, b) => b.id - a.id);
    return { items: out, total: out.length };
  };

  const handler: Handler = ({ method, path, query, body }) => {
    let m: RegExpMatchArray | null;

    // ---------------- YouTube ----------------
    if (path === "/api/youtube/status") return json({ configured: store.youtube.configured });
    if (path === "/api/youtube/preview" && method === "POST") {
      const b = body as { url: string; limit: number | null };
      if (!/youtube\.com\/(@|channel\/|playlist\?list=)/.test(b.url)) return json({ detail: "That doesn't look like a YouTube channel or playlist link." }, 422);
      const slice = store.youtube.catalog.slice(0, b.limit ?? store.youtube.catalog.length);
      const videos = slice.map((v) => {
        const have = store.videos.find((x) => x.youtube_video_id === v.youtube_video_id);
        return { ...v, in_library: !!have && have.removed_at === null, removed: !!have && have.removed_at !== null, status: have && have.removed_at === null ? have.status : null };
      });
      const preview: Preview = {
        source: store.youtube.source, retrieved: videos.length, unavailable: store.youtube.unavailable,
        more_available: videos.length < store.youtube.catalog.length, already_in_library: videos.filter((v) => v.in_library).length, videos,
      };
      return json(preview);
    }
    if (path === "/api/youtube/import" && method === "POST") {
      const b = body as { url: string; video_ids: string[]; retrieved: number };
      const src = store.youtube.source;
      let col = store.playlists.find((p) => p.kind === src.kind && (src.kind === "channel" ? p.youtube_channel_id === src.id : p.youtube_playlist_id === src.id));
      if (!col) {
        col = mkPlaylist({ name: src.title, kind: src.kind, youtube_channel_id: src.kind === "channel" ? src.id : null, youtube_playlist_id: src.kind === "playlist" ? src.id : null, source_url: src.url, thumbnail_url: src.thumbnail_url });
        store.playlists.push(col);
      }
      col.reported_total = src.total_available;
      col.retrieved_count = b.retrieved;
      const out = { created: 0, linked: 0, already_in_collection: 0, unavailable: 0 };
      for (const yid of b.video_ids) {
        const meta = store.youtube.catalog.find((v) => v.youtube_video_id === yid);
        if (!meta) {
          out.unavailable++;
          continue;
        }
        const have = store.videos.find((v) => v.youtube_video_id === yid);
        if (!have) {
          store.videos.push(mkVideo({ title: meta.title, url: meta.url, youtube_video_id: yid, thumbnail_url: meta.thumbnail_url, duration_seconds: meta.duration_seconds, published_at: meta.published_at, channel_title: meta.channel_title, playlist_ids: [col.id] }));
          out.created++;
        } else if (!have.playlist_ids.includes(col.id)) {
          have.playlist_ids.push(col.id);
          have.removed_at = null;
          out.linked++;
        } else if (have.removed_at !== null) {
          have.removed_at = null;
          out.linked++;
        } else out.already_in_collection++;
      }
      return json({ collection: summarise(col), ...out }, 201);
    }

    // ---------------- playlists ----------------
    if (path === "/api/video-playlists" && method === "GET") return json(store.playlists.map(summarise));
    if (path === "/api/video-playlists" && method === "POST") {
      const b = body as Partial<Playlist>;
      if (store.playlists.some((p) => p.name.toLowerCase() === String(b.name).toLowerCase())) return json({ detail: "You already have a playlist with that name" }, 409);
      const p = mkPlaylist({ ...b });
      store.playlists.push(p);
      return json(summarise(p), 201);
    }
    if ((m = path.match(/^\/api\/video-playlists\/(\d+)$/))) {
      const p = playlist(Number(m[1]));
      if (!p) return NF();
      if (method === "GET") return json(summarise(p));
      if (method === "PATCH") {
        Object.assign(p, body);
        return json(summarise(p));
      }
      if (method === "DELETE") {
        store.playlists.splice(store.playlists.indexOf(p), 1);
        store.videos.forEach((v) => (v.playlist_ids = v.playlist_ids.filter((x) => x !== p.id))); // videos stay in the library
        return empty();
      }
    }
    if ((m = path.match(/^\/api\/video-playlists\/(\d+)\/today$/))) {
      const p = playlist(Number(m[1]));
      if (!p) return NF();
      summarise(p);
      const plan: TodayPlan = {
        daily_target: p.daily_target, watched_today: p.watched_today, remaining_today: p.remaining_today,
        target_met: p.remaining_today === 0, up_next: recommended(members(p.id), p.recommend_order).slice(0, p.remaining_today),
      };
      return json(plan);
    }
    if ((m = path.match(/^\/api\/video-playlists\/(\d+)\/videos$/))) {
      const p = playlist(Number(m[1]));
      if (!p) return NF();
      if (method === "GET") return json(listVideos(store.videos.filter((v) => v.playlist_ids.includes(p.id)), query, p.recommend_order));
      const v = mkVideo({ ...(body as Partial<Video>), playlist_ids: [p.id] });
      store.videos.push(v);
      return json(v, 201);
    }
    if ((m = path.match(/^\/api\/video-playlists\/(\d+)\/bulk-videos$/))) {
      const p = playlist(Number(m[1]));
      if (!p) return NF();
      const result = { added: 0, linked: 0, duplicates: 0, invalid: [] as string[] };
      for (const line of (body as { lines: string[] }).lines) {
        const url = line.match(/https?:\/\/\S+/)?.[0];
        if (!url) {
          result.invalid.push(line);
          continue;
        }
        const have = store.videos.find((v) => v.url === url);
        if (have && have.playlist_ids.includes(p.id)) result.duplicates++;
        else if (have) {
          have.playlist_ids.push(p.id);
          result.linked++;
        } else {
          const title = line.replace(url, "").replace(/[|\s-]+$/g, "").trim() || url;
          store.videos.push(mkVideo({ title, url, playlist_ids: [p.id] }));
          result.added++;
        }
      }
      return json(result, 201);
    }

    // ---------------- library ----------------
    if (path === "/api/videos" && method === "GET") return json(listVideos(store.videos, query, "oldest"));
    if (path === "/api/videos/stats") {
      const vs = alive();
      const done = vs.filter((v) => v.status === "completed").length;
      const prog = vs.filter((v) => v.status === "watching").length;
      const stats: LibraryStats = {
        total: vs.length, completed: done, in_progress: prog, unwatched: vs.length - done - prog, percent: vs.length ? Math.floor((100 * done) / vs.length) : 0,
        removed: store.videos.length - vs.length, next_video: recommended(vs, query.order === "newest" ? "newest" : "oldest")[0] ?? null,
      };
      return json(stats);
    }
    if (path === "/api/videos/next") return json(recommended(alive(), query.order === "newest" ? "newest" : "oldest")[0] ?? null);
    if ((m = path.match(/^\/api\/videos\/(\d+)(?:\/(start|complete|uncomplete|status|remove|restore|move))?$/))) {
      const v = store.videos.find((x) => x.id === Number(m![1]));
      const action = m[2];
      if (!v || (v.removed_at !== null && action !== "restore" && method !== "DELETE")) return json({ detail: "Video not found" }, 404);
      if (!action && method === "PATCH") Object.assign(v, body);
      else if (!action && method === "DELETE") {
        store.videos.splice(store.videos.indexOf(v), 1);
        return empty();
      } else if (action === "start") {
        if (v.status === "completed") return json({ detail: "This video is already completed; reopen it first" }, 422);
        v.status = "watching";
      } else if (action === "complete") {
        if (v.status !== "completed") {
          v.status = "completed";
          v.completed_at = new Date().toISOString();
        }
      } else if (action === "uncomplete") {
        v.status = "unwatched";
        v.completed_at = null;
      } else if (action === "status") {
        const s = (body as { status: Video["status"] }).status;
        v.status = s;
        v.completed_at = s === "completed" ? (v.completed_at ?? new Date().toISOString()) : null;
      } else if (action === "remove") v.removed_at = new Date().toISOString();
      else if (action === "restore") v.removed_at = null;
      else if (action === "move") {
        const { direction, playlist_id } = body as { direction: string; playlist_id: number };
        const list = store.videos.filter((x) => x.playlist_ids.includes(playlist_id));
        const i = list.indexOf(v);
        const j = direction === "up" ? i - 1 : i + 1;
        if (j >= 0 && j < list.length) {
          const a = store.videos.indexOf(list[i]);
          const b = store.videos.indexOf(list[j]);
          [store.videos[a], store.videos[b]] = [store.videos[b], store.videos[a]];
        }
      }
      return json(v);
    }
    return undefined;
  };
  fake.handlers.push(handler);
  return store;
}
