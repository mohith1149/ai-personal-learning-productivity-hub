"""A fake YouTube Data API v3 for tests: httpx.MockTransport answering the four endpoints the app uses.

Mirrors the real behaviour verified against the live API: channels.list returns an empty list for an unknown
handle, playlists.list returns an empty list for a private/unknown playlist, playlistItems.list pages with
nextPageToken, and videos.list silently omits private/deleted videos.
"""
import json
from datetime import datetime, timedelta, timezone

import httpx

CHANNEL_ID = "UC" + "a" * 22
UPLOADS_ID = "UU" + "a" * 22
KEY = "test-key-NOT-REAL-123"


def vid(i: int) -> str:
    return f"v{i:010d}"  # 11 chars


def video_item(i: int, channel: str = CHANNEL_ID) -> dict:
    return {
        "id": vid(i),
        "snippet": {
            "title": f"Video number {i}", "description": f"About {i}", "channelId": channel, "channelTitle": "Fake Channel",
            "publishedAt": (datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(days=i)).isoformat().replace("+00:00", "Z"),
            "thumbnails": {"default": {"url": f"https://i.ytimg.com/vi/{vid(i)}/default.jpg"},
                           "medium": {"url": f"https://i.ytimg.com/vi/{vid(i)}/mqdefault.jpg"}},
        },
        "contentDetails": {"duration": f"PT{i % 60 + 1}M{i % 59}S"},
    }


class FakeYouTube:
    """`uploads`: video numbers newest-first (what a real uploads playlist returns). `hidden`: numbers that are
    listed but private/deleted (absent from videos.list)."""

    def __init__(self, uploads: list[int] | None = None, hidden: set[int] | None = None, page_size_cap: int = 50):
        self.uploads = uploads if uploads is not None else list(range(120, 0, -1))
        self.hidden = hidden or set()
        self.channel_video_count: int | str | None = len(self.uploads)
        self.playlists = {"PL" + "p" * 10: {"title": "Fake playlist", "items": [5, 3, 9, 1], "count": 4}}
        self.requests: list[httpx.Request] = []
        self.fail: tuple[int, str] | None = None  # (status, reason) to return for every call
        self.fail_after: int | None = None  # start failing after N successful calls
        self.network_error = False

    # -- helpers ----------------------------------------------------
    def calls(self, path: str) -> list[httpx.Request]:
        return [r for r in self.requests if r.url.path.endswith("/" + path)]

    def _json(self, data, status=200) -> httpx.Response:
        return httpx.Response(status, json=data)

    def _error(self, status: int, reason: str, message: str = "boom") -> httpx.Response:
        return self._json({"error": {"code": status, "message": message, "errors": [{"reason": reason}]}}, status)

    # -- handler ----------------------------------------------------
    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.network_error:
            raise httpx.ConnectError("no route", request=request)
        if request.headers.get("X-Goog-Api-Key") != KEY:
            return self._error(400, "keyInvalid", "API key not valid. Please pass a valid API key.")
        if self.fail_after is not None and len(self.requests) > self.fail_after:
            return self._error(*self.fail)
        if self.fail and self.fail_after is None:
            return self._error(*self.fail)
        q = dict(request.url.params)
        path = request.url.path.rsplit("/", 1)[-1]
        if path == "channels":
            known = q.get("id") == CHANNEL_ID or q.get("forHandle", "").lower().lstrip("@") == "fakechannel"
            if not known:
                return self._json({"items": []})
            stats = {} if self.channel_video_count is None else {"videoCount": str(self.channel_video_count)}
            return self._json({"items": [{
                "id": CHANNEL_ID,
                "snippet": {"title": "Fake Channel", "customUrl": "@fakechannel",
                            "thumbnails": {"medium": {"url": "https://yt3.ggpht.com/fake=s240"}}},
                "statistics": stats, "contentDetails": {"relatedPlaylists": {"uploads": UPLOADS_ID}}}]})
        if path == "playlists":
            pl = self.playlists.get(q.get("id", ""))
            if pl is None:
                return self._json({"items": []})
            return self._json({"items": [{"id": q["id"], "snippet": {
                "title": pl["title"], "channelId": CHANNEL_ID, "channelTitle": "Fake Channel",
                "thumbnails": {"high": {"url": "https://i.ytimg.com/vi/x/hqdefault.jpg"}}},
                "contentDetails": {"itemCount": pl["count"]}}]})
        if path == "playlistItems":
            pid = q.get("playlistId")
            if pid == UPLOADS_ID:
                nums = self.uploads
            elif pid in self.playlists:
                nums = self.playlists[pid]["items"]
            elif pid == "PL" + "x" * 10:
                return self._error(403, "playlistItemsNotAccessible", "private")
            else:
                return self._error(404, "playlistNotFound", "not found")
            size = min(int(q.get("maxResults", 5)), 50)
            start = int(q.get("pageToken", "0") or 0)
            chunk = nums[start : start + size]
            out = {"items": [{"contentDetails": {"videoId": vid(n)}} for n in chunk]}
            if start + size < len(nums):
                out["nextPageToken"] = str(start + size)
            return self._json(out)
        if path == "videos":
            ids = q.get("id", "").split(",")
            assert len(ids) <= 50, "videos.list accepts at most 50 ids"
            return self._json({"items": [video_item(int(i[1:])) for i in ids if int(i[1:]) not in self.hidden]})
        return self._json({"error": {"message": "unknown endpoint"}}, 404)

    def client(self):
        from app.services.youtube import YouTubeClient

        return YouTubeClient(KEY, http=httpx.Client(transport=httpx.MockTransport(self)))


def body(r: httpx.Response) -> dict:
    return json.loads(r.content)
