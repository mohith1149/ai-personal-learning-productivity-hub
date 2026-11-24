/** Video endpoints for the fake API. Mirrors the SERVER'S RESPONSE SHAPES and the derived numbers the UI shows
 *  (progress, watched today, up next). The real rules (recommendation query, timezones, validation) are tested in pytest. */
import type { Playlist, TodayPlan, Video } from "../api/videos";
import { todayIn } from "../lib/dates";
import { USER, type Fake, type Handler } from "./fakeApi";

let nextId = 9000;
const id = () => nextId++;

export function mkVideo(o: Partial<Video> & { playlist_id: number }): Video {
  const n = o.id ?? id();
  return {
    id: n, title: `Video ${n}`, url: null, youtube_video_id: null, description: null, category: null, status: "unwatched",
    position: n, completed_at: null, notes: null, created_at: "2026-11-23T00:00:00Z", ...o,
  };
}

export function mkPlaylist(o: Partial<Playlist> = {}): Playlist {
  const n = o.id ?? id();
  return {
    id: n, name: `Playlist ${n}`, source_url: null, youtube_playlist_id: null, description: null, daily_target: 1, active: true,
    total_videos: 0, completed_videos: 0, percent: 0, watched_today: 0, remaining_today: 1, next_video: null,
    created_at: "2026-11-23T00:00:00Z", ...o,
  };
}

export type FakeVideos = { playlists: Playlist[]; videos: Video[] };

export function installFakeVideos(fake: Fake, seed: Partial<FakeVideos> = {}): FakeVideos {
  const store: FakeVideos = { playlists: seed.playlists ?? [], videos: seed.videos ?? [] };
  const json = (data: unknown, status = 200) => Response.json(data, { status });
  const empty = () => new Response(null, { status: 204 });
  const inPlaylist = (pid: number) => store.videos.filter((v) => v.playlist_id === pid).sort((a, b) => a.position - b.position);
  const open = (pid: number) => inPlaylist(pid).filter((v) => v.status !== "completed");

  /** Recompute every derived field of a playlist from its videos, the way the server does. */
  const summarise = (p: Playlist): Playlist => {
    const vs = inPlaylist(p.id);
    const done = vs.filter((v) => v.status === "completed");
    const watched = done.filter((v) => v.completed_at && todayIn(USER.timezone, new Date(v.completed_at)) === todayIn(USER.timezone)).length;
    Object.assign(p, {
      total_videos: vs.length, completed_videos: done.length, percent: vs.length ? Math.floor((100 * done.length) / vs.length) : 0,
      watched_today: watched, remaining_today: Math.max(p.daily_target - watched, 0), next_video: open(p.id)[0] ?? null,
    });
    return p;
  };
  const playlist = (pid: number) => store.playlists.find((p) => p.id === pid);
  const NF = () => json({ detail: "Playlist not found" }, 404);

  const handler: Handler = ({ method, path, query, body }) => {
    let m: RegExpMatchArray | null;
    if (path === "/api/video-playlists" && method === "GET") return json(store.playlists.map(summarise));
    if (path === "/api/video-playlists" && method === "POST") {
      const b = body as Partial<Playlist>;
      if (store.playlists.some((p) => p.name.toLowerCase() === String(b.name).toLowerCase()))
        return json({ detail: "You already have a playlist with that name" }, 409);
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
        store.videos = store.videos.filter((v) => v.playlist_id !== p.id);
        return empty();
      }
    }
    if ((m = path.match(/^\/api\/video-playlists\/(\d+)\/today$/))) {
      const p = playlist(Number(m[1]));
      if (!p) return NF();
      summarise(p);
      const plan: TodayPlan = {
        daily_target: p.daily_target, watched_today: p.watched_today, remaining_today: p.remaining_today,
        target_met: p.remaining_today === 0, up_next: open(p.id).slice(0, p.remaining_today),
      };
      return json(plan);
    }
    if ((m = path.match(/^\/api\/video-playlists\/(\d+)\/videos$/))) {
      const p = playlist(Number(m[1]));
      if (!p) return NF();
      if (method === "GET") {
        let items = inPlaylist(p.id).filter((v) => query.view === "completed" ? v.status === "completed" : query.view === "open" ? v.status !== "completed" : true);
        if (query.q) items = items.filter((v) => v.title.toLowerCase().includes(query.q.toLowerCase()));
        return json({ items, total: items.length });
      }
      const v = mkVideo({ ...(body as Partial<Video>), playlist_id: p.id, position: inPlaylist(p.id).length + 1 });
      store.videos.push(v);
      return json(v, 201);
    }
    if ((m = path.match(/^\/api\/video-playlists\/(\d+)\/bulk-videos$/))) {
      const p = playlist(Number(m[1]));
      if (!p) return NF();
      const lines = (body as { lines: string[] }).lines;
      const result = { added: 0, duplicates: 0, invalid: [] as string[] };
      for (const line of lines) {
        const url = line.match(/https?:\/\/\S+/)?.[0];
        if (!url) result.invalid.push(line);
        else if (store.videos.some((v) => v.playlist_id === p.id && v.url === url)) result.duplicates++;
        else {
          const title = line.replace(url, "").replace(/[|\s-]+$/g, "").trim() || url;
          store.videos.push(mkVideo({ playlist_id: p.id, title, url, position: inPlaylist(p.id).length + 1 }));
          result.added++;
        }
      }
      return json(result, 201);
    }
    if (path === "/api/videos/next") {
      const first = store.playlists.filter((p) => p.active).flatMap((p) => open(p.id))[0];
      return json(first ?? null);
    }
    if ((m = path.match(/^\/api\/videos\/(\d+)(?:\/(start|complete|uncomplete|move))?$/))) {
      const v = store.videos.find((x) => x.id === Number(m![1]));
      if (!v) return json({ detail: "Video not found" }, 404);
      const action = m[2];
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
      } else if (action === "move") {
        const list = inPlaylist(v.playlist_id);
        const i = list.indexOf(v);
        const j = (body as { direction: string }).direction === "up" ? i - 1 : i + 1;
        if (j >= 0 && j < list.length) [list[i].position, list[j].position] = [list[j].position, list[i].position];
      }
      return json(v);
    }
    return undefined;
  };
  fake.handlers.push(handler);
  return store;
}
