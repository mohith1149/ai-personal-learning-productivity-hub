"""Read-only client for the official YouTube Data API v3.

What it does: resolve a channel or playlist URL, read its public metadata, and page through its public videos.
What it never does: read anyone's watch history (the API does not offer it), write to YouTube, or guess a number.
If YouTube does not report a count, the value is `None` and the UI says "unavailable".

Security:
  * The API key lives only in backend settings and is sent in the `X-Goog-Api-Key` HEADER. It is deliberately NOT a
    query parameter: httpx logs every request URL at INFO, so a `?key=` would end up in the log files.
  * Error messages are written by this module; raw httpx/Google error text (which can echo request details) is never
    passed on.
  * Only ids parsed out of the URL are sent to Google; the URL itself is never fetched, so there is no SSRF surface.

Quota: every call costs 1 unit of the 10,000/day default; 50 videos cost 2 calls (list page + video details).
"""
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable
from urllib.parse import parse_qs, urlsplit

import httpx

API_BASE = "https://www.googleapis.com/youtube/v3"
PAGE_SIZE = 50  # the API maximum for playlistItems / videos
HARD_CAP = 2000  # most videos one preview may scan (40 pages); beyond that the preview is marked truncated

_CHANNEL_ID = re.compile(r"^UC[A-Za-z0-9_-]{22}$")
_HANDLE = re.compile(r"^@[A-Za-z0-9._-]{3,30}$")
_PLAYLIST_ID = re.compile(r"^[A-Za-z0-9_-]{10,64}$")
_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}
_DURATION = re.compile(r"^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$")


class YouTubeError(Exception):
    """A problem the user should see, with a stable `code` the UI/tests can rely on."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class Source:
    kind: str  # "channel" | "playlist"
    channel_id: str | None = None
    handle: str | None = None
    playlist_id: str | None = None


@dataclass
class SourceInfo:
    kind: str
    id: str  # channel id or playlist id
    title: str
    thumbnail_url: str | None
    total_available: int | None  # what YouTube reports; None = unavailable
    url: str
    channel_id: str | None = None
    channel_title: str | None = None
    handle: str | None = None
    uploads_playlist_id: str | None = None  # channels: the playlist that holds every public upload


@dataclass
class VideoMeta:
    youtube_video_id: str
    title: str
    description: str | None
    thumbnail_url: str | None
    duration_seconds: int | None
    published_at: datetime | None
    channel_id: str | None
    channel_title: str | None

    @property
    def url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.youtube_video_id}"


@dataclass
class FetchResult:
    videos: list[VideoMeta] = field(default_factory=list)
    unavailable: int = 0  # listed but private/deleted, so not retrievable
    scanned: int = 0  # playlist entries looked at
    pages: int = 0
    more_available: bool = False  # stopped early (limit/cap) while YouTube had more


# ---------------------------------------------------------------- URL parsing


def parse_source(text: str) -> Source:
    """Turn what the user pasted into a channel or playlist reference, or raise YouTubeError('invalid_url').

    Accepted: https://www.youtube.com/@Handle[/videos], /channel/UC..., /playlist?list=..., /watch?v=..&list=..,
    and a bare @Handle or UC... channel id.
    """
    raw = (text or "").strip()
    bad = YouTubeError("invalid_url", "That doesn't look like a YouTube channel or playlist link. Try a link like "
                                      "https://www.youtube.com/@ByteByteGo or https://www.youtube.com/playlist?list=...")
    if not raw or len(raw) > 500:
        raise bad
    if _HANDLE.match(raw):
        return Source("channel", handle=raw)
    if _CHANNEL_ID.match(raw):
        return Source("channel", channel_id=raw)
    parts = urlsplit(raw if "://" in raw else f"https://{raw}")
    if parts.scheme not in ("http", "https") or (parts.hostname or "").lower() not in _HOSTS:
        raise bad
    segs = [x for x in parts.path.split("/") if x]
    query = parse_qs(parts.query)
    listed = (query.get("list") or [None])[0]
    if segs and segs[0] == "playlist" or (segs and segs[0] == "watch" and listed):
        if listed and _PLAYLIST_ID.match(listed):
            return Source("playlist", playlist_id=listed)
        raise YouTubeError("invalid_url", "That playlist link has no valid playlist id (the part after list=).")
    if segs and segs[0].startswith("@"):
        handle = segs[0]
        if _HANDLE.match(handle):
            return Source("channel", handle=handle)
        raise YouTubeError("invalid_url", "That @handle doesn't look valid.")
    if len(segs) >= 2 and segs[0] == "channel":
        if _CHANNEL_ID.match(segs[1]):
            return Source("channel", channel_id=segs[1])
        raise YouTubeError("invalid_url", "That channel id doesn't look valid (it should start with UC and be 24 characters).")
    if segs and segs[0] in ("c", "user"):
        raise YouTubeError("invalid_url", "Older /c/ and /user/ channel links can't be resolved. Open the channel and copy "
                                          "its @handle link (https://www.youtube.com/@name) instead.")
    raise bad


def parse_duration(iso: str | None) -> int | None:
    """ISO-8601 duration ("PT1H2M3S", "P1DT2H") -> seconds. None when absent or unparseable (e.g. live, "P0D" -> 0)."""
    if not iso:
        return None
    m = _DURATION.match(iso)
    if not m:
        return None
    d, h, mi, sec = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + sec


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _thumb(thumbs: dict | None) -> str | None:
    for size in ("medium", "high", "standard", "default", "maxres"):
        url = ((thumbs or {}).get(size) or {}).get("url")
        if url and url.startswith("https://"):
            return url
    return None


def _count(value) -> int | None:
    try:
        n = int(value)
        return n if n >= 0 else None
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- client


class YouTubeClient:
    def __init__(self, api_key: str | None, http: httpx.Client | None = None):
        if not api_key:
            raise YouTubeError("not_configured", "YouTube import isn't set up yet. Add YOUTUBE_API_KEY to backend/.env "
                                                 "(a YouTube Data API v3 key) and restart the server.")
        self._http = http or httpx.Client(timeout=httpx.Timeout(15.0), headers={"Accept": "application/json"})
        self._headers = {"X-Goog-Api-Key": api_key}
        self.calls = 0  # API calls made (1 quota unit each); handy for tests and logs

    def close(self) -> None:
        self._http.close()

    # -- transport ---------------------------------------------------

    def _get(self, path: str, **params) -> dict:
        self.calls += 1
        try:
            r = self._http.get(f"{API_BASE}/{path}", params=params, headers=self._headers)
        except httpx.TimeoutException:
            raise YouTubeError("network", "YouTube took too long to answer. Try again in a moment.") from None
        except httpx.HTTPError:
            raise YouTubeError("network", "Couldn't reach YouTube. Check your internet connection and try again.") from None
        if r.status_code == 200:
            try:
                return r.json()
            except ValueError:
                raise YouTubeError("api_error", "YouTube sent a reply that couldn't be read.") from None
        raise self._error(r)

    @staticmethod
    def _error(r: httpx.Response) -> YouTubeError:
        try:
            err = r.json().get("error", {})
            reason = (err.get("errors") or [{}])[0].get("reason", "")
            status_text = err.get("status", "")
        except (ValueError, AttributeError):
            reason = status_text = ""
        if reason in ("quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded", "userRateLimitExceeded"):
            return YouTubeError("quota", "YouTube's daily request limit for this API key is used up. It resets "
                                         "at midnight Pacific time; try again later.")
        text = r.text or ""
        if (r.status_code == 400 and (reason == "keyInvalid" or "API key not valid" in text)) or r.status_code == 401:
            return YouTubeError("bad_key", "YouTube rejected the API key. Check YOUTUBE_API_KEY in backend/.env.")
        if reason in ("accessNotConfigured", "ipRefererBlocked", "referrerBlocked") or "API_KEY_" in text                 or status_text == "PERMISSION_DENIED":
            return YouTubeError("bad_key", "This API key isn't allowed to use the YouTube Data API v3. Enable the API "
                                           "for the key in Google Cloud Console and check the key's restrictions.")
        if reason in ("playlistNotFound", "channelNotFound", "videoNotFound") or r.status_code == 404:
            return YouTubeError("not_found", "YouTube couldn't find that. Check the link.")
        if reason in ("playlistItemsNotAccessible", "playlistForbidden", "forbidden"):
            return YouTubeError("private", "That playlist or channel is private, so its videos can't be read.")
        if r.status_code == 403:
            return YouTubeError("bad_key", "YouTube refused the request (HTTP 403). Check the API key's settings.")
        if r.status_code >= 500:
            return YouTubeError("api_error", "YouTube is having trouble right now. Try again in a moment.")
        return YouTubeError("api_error", f"YouTube returned an error (HTTP {r.status_code}).")

    # -- sources -----------------------------------------------------

    def resolve(self, source: Source) -> SourceInfo:
        return self._resolve_channel(source) if source.kind == "channel" else self._resolve_playlist(source)

    def _resolve_channel(self, source: Source) -> SourceInfo:
        params = {"part": "snippet,statistics,contentDetails", "maxResults": 1}
        if source.channel_id:
            params["id"] = source.channel_id
        else:
            params["forHandle"] = source.handle
        items = self._get("channels", **params).get("items") or []
        if not items:
            raise YouTubeError("not_found", "YouTube has no channel at that link. Check the @handle or channel id.")
        ch = items[0]
        snippet, stats = ch.get("snippet", {}), ch.get("statistics", {})
        uploads = (ch.get("contentDetails", {}).get("relatedPlaylists") or {}).get("uploads")
        cid = ch["id"]
        return SourceInfo(
            kind="channel", id=cid, title=snippet.get("title") or "YouTube channel", thumbnail_url=_thumb(snippet.get("thumbnails")),
            total_available=_count(stats.get("videoCount")), url=f"https://www.youtube.com/channel/{cid}",
            channel_id=cid, channel_title=snippet.get("title"), handle=snippet.get("customUrl"), uploads_playlist_id=uploads)

    def _resolve_playlist(self, source: Source) -> SourceInfo:
        items = self._get("playlists", part="snippet,contentDetails,status", id=source.playlist_id, maxResults=1).get("items") or []
        if not items:
            # YouTube answers an empty list (not an error) for private and for non-existent playlists alike.
            raise YouTubeError("not_found", "YouTube has no public playlist with that id. It may be private or deleted.")
        pl = items[0]
        snippet = pl.get("snippet", {})
        return SourceInfo(
            kind="playlist", id=pl["id"], title=snippet.get("title") or "YouTube playlist",
            thumbnail_url=_thumb(snippet.get("thumbnails")), total_available=_count(pl.get("contentDetails", {}).get("itemCount")),
            url=f"https://www.youtube.com/playlist?list={pl['id']}", channel_id=snippet.get("channelId"),
            channel_title=snippet.get("channelTitle"))

    # -- videos ------------------------------------------------------

    def fetch_videos(self, info: SourceInfo, limit: int | None,
                     on_page: Callable[[int], None] | None = None) -> FetchResult:
        """Page through the source's videos (newest first for a channel, playlist order for a playlist).

        `limit` = how many AVAILABLE videos to retrieve (None = all, up to HARD_CAP entries scanned).
        Private/deleted entries are counted in `unavailable` and don't use up the limit.
        """
        playlist_id = info.uploads_playlist_id if info.kind == "channel" else info.id
        if not playlist_id:
            raise YouTubeError("api_error", "YouTube didn't say where this channel keeps its videos.")
        out = FetchResult()
        token: str | None = None
        seen: set[str] = set()
        while True:
            want = PAGE_SIZE if limit is None else min(PAGE_SIZE, max(limit - len(out.videos), 1))
            params = {"part": "contentDetails", "playlistId": playlist_id, "maxResults": want}
            if token:
                params["pageToken"] = token
            page = self._get("playlistItems", **params)
            out.pages += 1
            ids = []
            for item in page.get("items", []):
                vid = (item.get("contentDetails") or {}).get("videoId")
                out.scanned += 1
                if vid and _VIDEO_ID.match(vid) and vid not in seen:
                    seen.add(vid)
                    ids.append(vid)
            details = self.video_details(ids)
            out.unavailable += len(ids) - len(details)
            room = None if limit is None else max(limit - len(out.videos), 0)
            clipped = room is not None and len(details) > room
            out.videos.extend(details if room is None else details[:room])
            token = page.get("nextPageToken")
            if on_page:
                on_page(len(out.videos))
            if limit is not None and len(out.videos) >= limit:
                out.more_available = bool(token) or clipped
                return out
            if not token:
                return out
            if out.scanned >= HARD_CAP:
                out.more_available = True
                return out

    def video_details(self, ids: list[str]) -> list[VideoMeta]:
        """Metadata for up to many ids (50 per call). Ids YouTube doesn't return (private/deleted) are simply absent;
        the order of `ids` is kept."""
        found: dict[str, VideoMeta] = {}
        for i in range(0, len(ids), PAGE_SIZE):
            chunk = ids[i : i + PAGE_SIZE]
            data = self._get("videos", part="snippet,contentDetails", id=",".join(chunk), maxResults=len(chunk))
            for v in data.get("items", []):
                sn = v.get("snippet", {})
                found[v["id"]] = VideoMeta(
                    youtube_video_id=v["id"], title=(sn.get("title") or "Untitled video")[:300],
                    description=(sn.get("description") or None), thumbnail_url=_thumb(sn.get("thumbnails")),
                    duration_seconds=parse_duration(v.get("contentDetails", {}).get("duration")),
                    published_at=_parse_time(sn.get("publishedAt")), channel_id=sn.get("channelId"),
                    channel_title=(sn.get("channelTitle") or None))
        return [found[i] for i in ids if i in found]
