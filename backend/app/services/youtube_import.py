"""Preview and import videos from a YouTube channel or playlist into the library.

Flow (nothing is saved until the user confirms):
  1. `preview`  - resolve the link, fetch up to `limit` videos, mark which ones the library already has. Read-only.
  2. `import_selected` - the user ticks videos; the server re-reads THOSE videos from YouTube (it never trusts titles,
     dates or counts sent by the browser), then links them into the channel/playlist collection.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User, Video, VideoPlaylist
from app.schemas import youtube as ys
from app.services import videos as lib
from app.services.youtube import Source, SourceInfo, YouTubeClient, YouTubeError, parse_source


def _library_index(db: Session, user: User, ids: list[str]) -> dict[str, Video]:
    if not ids:
        return {}
    rows = db.scalars(select(Video).where(Video.user_id == user.id, Video.youtube_video_id.in_(ids)))
    return {v.youtube_video_id: v for v in rows}


def _source_out(info: SourceInfo) -> dict:
    return {"kind": info.kind, "id": info.id, "title": info.title, "url": info.url, "thumbnail_url": info.thumbnail_url,
            "total_available": info.total_available, "handle": info.handle, "channel_title": info.channel_title}


def preview(db: Session, user: User, client: YouTubeClient, data: ys.PreviewRequest) -> dict:
    info = client.resolve(parse_source(data.url))
    fetched = client.fetch_videos(info, data.limit)
    known = _library_index(db, user, [v.youtube_video_id for v in fetched.videos])
    videos = []
    for v in fetched.videos:
        have = known.get(v.youtube_video_id)
        videos.append({
            "youtube_video_id": v.youtube_video_id, "title": v.title, "url": v.url, "thumbnail_url": v.thumbnail_url,
            "duration_seconds": v.duration_seconds, "published_at": v.published_at, "channel_title": v.channel_title,
            "in_library": have is not None and have.removed_at is None,
            "removed": have is not None and have.removed_at is not None,
            "status": have.status if have is not None and have.removed_at is None else None,
        })
    return {"source": _source_out(info), "retrieved": len(fetched.videos), "unavailable": fetched.unavailable,
            "more_available": fetched.more_available, "already_in_library": sum(v["in_library"] for v in videos),
            "videos": videos}


def _collection_for(db: Session, user: User, info: SourceInfo) -> VideoPlaylist:
    """The user's collection for this channel/playlist: reused if it exists, created otherwise."""
    if info.kind == "channel":
        match = (VideoPlaylist.kind == "channel", VideoPlaylist.youtube_channel_id == info.id)
    else:
        match = (VideoPlaylist.kind == "playlist", VideoPlaylist.youtube_playlist_id == info.id)
    p = db.scalar(select(VideoPlaylist).where(VideoPlaylist.user_id == user.id, *match))
    if p is None:
        name, n = info.title[:120], 1
        while lib._name_taken(db, user, name):  # a hand-made collection may already use the title
            n += 1
            suffix = f" (YouTube)" if n == 2 else f" (YouTube {n - 1})"
            name = info.title[: 120 - len(suffix)] + suffix
        p = VideoPlaylist(user_id=user.id, name=name, kind=info.kind, recommend_order="oldest", daily_target=1)
        db.add(p)
    p.source_url = info.url
    p.thumbnail_url = info.thumbnail_url or p.thumbnail_url
    p.reported_total = info.total_available  # None stays None: unknown is not turned into a number
    if info.kind == "channel":
        p.youtube_channel_id = info.id
    else:
        p.youtube_playlist_id = info.id
        p.youtube_channel_id = p.youtube_channel_id or info.channel_id
    db.flush()
    return p


def import_selected(db: Session, user: User, client: YouTubeClient, data: ys.ImportRequest) -> dict:
    source: Source = parse_source(data.url)
    info = client.resolve(source)
    wanted = list(dict.fromkeys(data.video_ids))  # drop repeats, keep the user's order
    details = client.video_details(wanted)
    if not details:
        raise YouTubeError("not_found", "None of the selected videos are available on YouTube any more.")
    collection = _collection_for(db, user, info)
    collection.retrieved_count = max(data.retrieved, len(details))
    result = {"created": 0, "linked": 0, "already_in_collection": 0}
    # Oldest first, so the collection's manual order matches publish order too.
    for v in sorted(details, key=lambda m: (m.published_at is None, m.published_at)):
        outcome, _ = lib.upsert_video(db, user, collection, {
            "title": v.title, "url": v.url, "youtube_video_id": v.youtube_video_id, "description": v.description,
            "thumbnail_url": v.thumbnail_url, "duration_seconds": v.duration_seconds, "published_at": v.published_at,
            "channel_id": v.channel_id, "channel_title": v.channel_title})
        result[{"created": "created", "linked": "linked", "duplicate": "already_in_collection"}[outcome]] += 1
    db.commit()
    return {"collection": lib.playlist_summary(db, user, collection.id), "unavailable": len(wanted) - len(details), **result}
