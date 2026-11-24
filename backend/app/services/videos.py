"""Video library business logic.

Rules implemented here:
  * Every query is scoped to the owning user; someone else's id behaves exactly like "not found".
  * LIBRARY: a YouTube video exists once per user (unique user + youtube id). Collections (playlists / channels) only
    reference it through `video_memberships`, so importing it again links it instead of duplicating it.
  * A video is completed ONLY by an explicit call (`complete_video` / `set_status`). Completing twice keeps the first
    completion time.
  * "Remove from library" is a soft delete (`removed_at`): the video disappears from lists, counts and recommendations
    and can be restored. "Delete permanently" erases the row. Neither touches YouTube.
  * RECOMMENDATION RULE: the next video is chosen by SQL
    (`status != 'completed' AND removed_at IS NULL ORDER BY published_at ...`). A completed or removed video can
    therefore never be returned by `next_videos` / `next_video_overall` - the UI does not filter, the query does.
    Default order is oldest-published first; a collection can use newest-first or its manual order instead.
    (Un-completing a video is an explicit user action; only then can it be recommended again.)
  * "Watched today" counts completions inside the user's LOCAL calendar day, not the server's.
  * The application cannot see anyone's YouTube history: progress is only what is recorded here.
"""
import re
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlsplit

from sqlalchemy import case, exists, func, select
from sqlalchemy.orm import Session, selectinload

from app.core.timeutil import local_day_bounds_utc, user_today
from app.models import User, Video, VideoMembership, VideoPlaylist
from app.schemas import videos as s


class NotFound(Exception):
    pass


class RuleError(ValueError):
    """A business-rule violation the client should see as HTTP 422."""


class Conflict(Exception):
    """The request clashes with existing data (HTTP 409)."""


_YT_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_URL_IN_LINE = re.compile(r"https?://\S+")


def youtube_video_id(url: str | None) -> str | None:
    """The 11-character YouTube id of a watch / youtu.be / shorts / embed link, else None."""
    if not url:
        return None
    parts = urlsplit(url)
    host = (parts.hostname or "").lower().removeprefix("www.").removeprefix("m.")
    candidate = None
    if host == "youtu.be":
        candidate = parts.path.strip("/").split("/")[0]
    elif host in ("youtube.com", "music.youtube.com", "youtube-nocookie.com"):
        if parts.path == "/watch":
            candidate = (parse_qs(parts.query).get("v") or [None])[0]
        else:
            segs = [x for x in parts.path.split("/") if x]
            if len(segs) >= 2 and segs[0] in ("shorts", "embed", "live", "v"):
                candidate = segs[1]
    return candidate if candidate and _YT_ID.match(candidate) else None


def parse_line(line: str) -> tuple[str, str] | None:
    """`url`, `title | url` or `title - url` -> (title, url). None when the line has no usable http(s) link."""
    m = _URL_IN_LINE.search(line)
    if not m:
        return None
    url = m.group(0).rstrip(".,;)")
    if len(url) > 500 or urlsplit(url).netloc == "":
        return None
    title = (line[: m.start()] + line[m.end():]).strip(" \t|-:*")
    if not title:
        vid = youtube_video_id(url)
        title = f"YouTube video {vid}" if vid else url[:200]
    return title[:300], url


# ============================== lookups ==============================


def _get_playlist(db: Session, user: User, playlist_id: int) -> VideoPlaylist:
    p = db.scalar(select(VideoPlaylist).where(VideoPlaylist.id == playlist_id, VideoPlaylist.user_id == user.id))
    if p is None:
        raise NotFound("Playlist not found")
    return p


def _get_video(db: Session, user: User, video_id: int, include_removed: bool = False) -> Video:
    q = select(Video).where(Video.id == video_id, Video.user_id == user.id)
    if not include_removed:
        q = q.where(Video.removed_at.is_(None))
    v = db.scalar(q)
    if v is None:
        raise NotFound("Video not found")
    return v


def _order(mode: str, position):
    """ORDER BY for recommendations. Videos without a publish date (added by hand) come after dated ones."""
    if mode == "manual":
        return (position, Video.id)
    published = Video.published_at.asc() if mode == "oldest" else Video.published_at.desc()
    return (Video.published_at.is_(None), published, position, Video.id)


def _open_videos(playlist: VideoPlaylist):
    """THE recommendation query for a collection: not completed, not removed, in the collection's order."""
    return (
        select(Video)
        .join(VideoMembership, VideoMembership.video_id == Video.id)
        .where(VideoMembership.playlist_id == playlist.id, Video.status != "completed", Video.removed_at.is_(None))
        .order_by(*_order(playlist.recommend_order, VideoMembership.position))
        .options(selectinload(Video.memberships))
    )


def next_videos(db: Session, playlist: VideoPlaylist, limit: int) -> list[Video]:
    return list(db.scalars(_open_videos(playlist).limit(limit))) if limit > 0 else []


def next_video_overall(db: Session, user: User, order: str = "oldest") -> Video | None:
    """The next not-completed, not-removed video of the whole library (only ACTIVE collections count)."""
    in_active = exists().where(
        VideoMembership.video_id == Video.id, VideoMembership.playlist_id == VideoPlaylist.id,
        VideoPlaylist.user_id == user.id, VideoPlaylist.active.is_(True))
    return db.scalar(
        select(Video).where(Video.user_id == user.id, Video.status != "completed", Video.removed_at.is_(None), in_active)
        .order_by(*_order(order, Video.id)).limit(1).options(selectinload(Video.memberships)))


# ============================== playlists ==============================


def _watched_today(db: Session, user: User, playlist_ids: list[int], now: datetime | None) -> dict[int, int]:
    if not playlist_ids:
        return {}
    start, end = local_day_bounds_utc(user, user_today(user, now))
    rows = db.execute(
        select(VideoMembership.playlist_id, func.count())
        .join(Video, Video.id == VideoMembership.video_id)
        .where(VideoMembership.playlist_id.in_(playlist_ids), Video.removed_at.is_(None), Video.status == "completed",
               Video.completed_at >= start, Video.completed_at < end)
        .group_by(VideoMembership.playlist_id)
    )
    return {pid: n for pid, n in rows}


def _percent(done: int, total: int) -> int:
    return (100 * done) // total if total else 0  # floor: 100 only when every video is completed


def _summaries(db: Session, user: User, playlists: list[VideoPlaylist], now: datetime | None) -> list[dict]:
    ids = [p.id for p in playlists]
    counts: dict[int, tuple[int, int, int]] = {}
    if ids:
        rows = db.execute(
            select(VideoMembership.playlist_id, func.count(),
                   func.sum(case((Video.status == "completed", 1), else_=0)),
                   func.sum(case((Video.status == "watching", 1), else_=0)))
            .join(Video, Video.id == VideoMembership.video_id)
            .where(VideoMembership.playlist_id.in_(ids), Video.removed_at.is_(None))
            .group_by(VideoMembership.playlist_id)
        )
        counts = {pid: (int(n), int(done or 0), int(prog or 0)) for pid, n, done, prog in rows}
    today = _watched_today(db, user, ids, now)
    out = []
    for p in playlists:
        total, done, prog = counts.get(p.id, (0, 0, 0))
        watched = today.get(p.id, 0)
        nxt = next_videos(db, p, 1)
        out.append({
            "id": p.id, "name": p.name, "kind": p.kind, "source_url": p.source_url,
            "youtube_playlist_id": p.youtube_playlist_id, "youtube_channel_id": p.youtube_channel_id,
            "thumbnail_url": p.thumbnail_url, "description": p.description, "daily_target": p.daily_target,
            "active": p.active, "recommend_order": p.recommend_order, "reported_total": p.reported_total,
            "retrieved_count": p.retrieved_count, "total_videos": total, "completed_videos": done,
            "in_progress_videos": prog, "unwatched_videos": total - done - prog, "percent": _percent(done, total),
            "watched_today": watched, "remaining_today": max(p.daily_target - watched, 0),
            "next_video": nxt[0] if nxt else None, "created_at": p.created_at,
        })
    return out


def list_playlists(db: Session, user: User, now: datetime | None = None) -> list[dict]:
    playlists = list(db.scalars(
        select(VideoPlaylist).where(VideoPlaylist.user_id == user.id).order_by(VideoPlaylist.id)))
    return _summaries(db, user, playlists, now)


def playlist_summary(db: Session, user: User, playlist_id: int, now: datetime | None = None) -> dict:
    return _summaries(db, user, [_get_playlist(db, user, playlist_id)], now)[0]


def library_stats(db: Session, user: User, order: str = "oldest") -> dict:
    """Overall progress. Counts every non-removed video of the user once, however many collections it is in."""
    total, done, prog = db.execute(
        select(func.count(), func.coalesce(func.sum(case((Video.status == "completed", 1), else_=0)), 0),
               func.coalesce(func.sum(case((Video.status == "watching", 1), else_=0)), 0))
        .where(Video.user_id == user.id, Video.removed_at.is_(None))).one()
    removed = db.scalar(select(func.count()).where(Video.user_id == user.id, Video.removed_at.is_not(None))) or 0
    return {"total": total, "completed": int(done), "in_progress": int(prog), "unwatched": total - int(done) - int(prog),
            "percent": _percent(int(done), total), "removed": removed, "next_video": next_video_overall(db, user, order)}


def _name_taken(db: Session, user: User, name: str, except_id: int | None = None) -> bool:
    q = select(VideoPlaylist.id).where(VideoPlaylist.user_id == user.id, func.lower(VideoPlaylist.name) == name.lower())
    if except_id is not None:
        q = q.where(VideoPlaylist.id != except_id)
    return db.scalar(q) is not None


def create_playlist(db: Session, user: User, data: s.PlaylistCreate) -> VideoPlaylist:
    if _name_taken(db, user, data.name):
        raise Conflict("You already have a playlist with that name")
    p = VideoPlaylist(user_id=user.id, **data.model_dump())
    db.add(p)
    db.commit()
    return p


def update_playlist(db: Session, user: User, playlist_id: int, data: s.PlaylistUpdate) -> VideoPlaylist:
    p = _get_playlist(db, user, playlist_id)
    changes = data.model_dump(exclude_unset=True)
    for required in ("name", "daily_target", "active", "recommend_order"):
        if required in changes and changes[required] is None:
            raise RuleError(f"{required} can't be empty")
    if "name" in changes and _name_taken(db, user, changes["name"], except_id=p.id):
        raise Conflict("You already have a playlist with that name")
    for field, value in changes.items():
        setattr(p, field, value)
    db.commit()
    return p


def delete_playlist(db: Session, user: User, playlist_id: int) -> None:
    """Deletes the collection only. Its videos stay in the library (and in any other collection they belong to)."""
    db.delete(_get_playlist(db, user, playlist_id))
    db.commit()


# ============================== videos ==============================


def _next_position(db: Session, playlist_id: int) -> int:
    top = db.scalar(select(func.max(VideoMembership.position)).where(VideoMembership.playlist_id == playlist_id))
    return (top or 0) + 1


_META = ("thumbnail_url", "duration_seconds", "published_at", "channel_id", "channel_title")


def upsert_video(db: Session, user: User, playlist: VideoPlaylist, fields: dict) -> tuple[str, Video]:
    """Put a video into a collection WITHOUT ever creating a second library row for the same YouTube video.

    Returns (outcome, video) with outcome one of:
      "created"   new library video
      "linked"    already in the library (or restored from removed), now also in this collection
      "duplicate" already in this collection
    Existing videos keep the user's own title / notes / status; only missing YouTube metadata is filled in.
    The caller commits.
    """
    yt = fields.get("youtube_video_id")
    existing = db.scalar(select(Video).where(Video.user_id == user.id, Video.youtube_video_id == yt)) if yt else None
    if existing is None:
        v = Video(user_id=user.id, **fields)
        db.add(v)
        db.flush()
        db.add(VideoMembership(playlist_id=playlist.id, video_id=v.id, position=_next_position(db, playlist.id)))
        db.flush()
        return "created", v
    restored = existing.removed_at is not None
    existing.removed_at = None
    for key in ("description", *_META):
        if getattr(existing, key) is None and fields.get(key) is not None:
            setattr(existing, key, fields[key])
    member = db.scalar(select(VideoMembership.id).where(
        VideoMembership.playlist_id == playlist.id, VideoMembership.video_id == existing.id))
    if member is None:
        db.add(VideoMembership(playlist_id=playlist.id, video_id=existing.id, position=_next_position(db, playlist.id)))
        db.flush()
        return "linked", existing
    return ("linked" if restored else "duplicate"), existing


def add_video(db: Session, user: User, playlist_id: int, data: s.VideoCreate) -> Video:
    p = _get_playlist(db, user, playlist_id)
    outcome, v = upsert_video(db, user, p, {**data.model_dump(), "youtube_video_id": youtube_video_id(data.url)})
    if outcome == "duplicate":
        db.rollback()
        raise Conflict("That video is already in this playlist")
    db.commit()
    return v


def bulk_add_videos(db: Session, user: User, playlist_id: int, data: s.BulkVideos) -> dict:
    p = _get_playlist(db, user, playlist_id)
    seen: set[str] = set()
    result = {"added": 0, "linked": 0, "duplicates": 0, "invalid": []}
    for raw in data.lines:
        parsed = parse_line(raw)
        if parsed is None:
            result["invalid"].append(raw[:120])
            continue
        title, url = parsed
        yt = youtube_video_id(url)
        if (yt or url) in seen:
            result["duplicates"] += 1
            continue
        seen.add(yt or url)
        if yt is None and db.scalar(
                select(Video.id).join(VideoMembership, VideoMembership.video_id == Video.id)
                .where(VideoMembership.playlist_id == p.id, Video.url == url, Video.removed_at.is_(None))):
            result["duplicates"] += 1  # no YouTube id, so it can only be de-duplicated within this collection
            continue
        outcome, _ = upsert_video(db, user, p, {"title": title, "url": url, "youtube_video_id": yt,
                                                "category": data.category})
        result[{"created": "added", "linked": "linked", "duplicate": "duplicates"}[outcome]] += 1
    db.commit()
    return result


def list_videos(db: Session, user: User, playlist_id: int | None = None, view: str = "all", q: str | None = None,
                status: str | None = None, sort: str = "recommended", limit: int = 100, offset: int = 0) -> dict:
    """The whole library (playlist_id=None) or one collection.

    view: all / open / completed / removed (removed videos appear ONLY in the "removed" view).
    status: narrow to one status. sort: recommended / newest / oldest / completed / added.
    """
    where = [Video.user_id == user.id]
    playlist = _get_playlist(db, user, playlist_id) if playlist_id is not None else None
    where.append(Video.removed_at.is_not(None) if view == "removed" else Video.removed_at.is_(None))
    if view == "open":
        where.append(Video.status != "completed")
    elif view == "completed":
        where.append(Video.status == "completed")
    if status:
        where.append(Video.status == status)
    if q:
        like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        where.append(Video.title.ilike(like, escape="\\"))
    base = select(Video).where(*where)
    if playlist is not None:
        base = base.join(VideoMembership, VideoMembership.video_id == Video.id).where(
            VideoMembership.playlist_id == playlist.id)
    position = VideoMembership.position if playlist is not None else Video.id
    mode = playlist.recommend_order if playlist is not None else "oldest"
    if view == "completed" and sort == "recommended":
        sort = "completed"
    orders = {
        "recommended": _order(mode, position),
        "newest": (Video.published_at.is_(None), Video.published_at.desc(), Video.id.desc()),
        "oldest": (Video.published_at.is_(None), Video.published_at.asc(), Video.id),
        "completed": (Video.completed_at.is_(None), Video.completed_at.desc(), Video.id),
        "added": (Video.created_at.desc(), Video.id.desc()),
    }
    total = db.scalar(select(func.count()).select_from(base.order_by(None).subquery())) or 0
    items = list(db.scalars(
        base.order_by(*orders[sort]).limit(limit).offset(offset).options(selectinload(Video.memberships))))
    return {"items": items, "total": total}


def today(db: Session, user: User, playlist_id: int, now: datetime | None = None) -> dict:
    summary = playlist_summary(db, user, playlist_id, now)
    remaining = summary["remaining_today"]
    return {
        "daily_target": summary["daily_target"], "watched_today": summary["watched_today"],
        "remaining_today": remaining, "target_met": remaining == 0,
        "up_next": next_videos(db, _get_playlist(db, user, playlist_id), remaining),
    }


def update_video(db: Session, user: User, video_id: int, data: s.VideoUpdate) -> Video:
    v = _get_video(db, user, video_id)
    changes = data.model_dump(exclude_unset=True)
    if changes.get("title", "x") is None:
        raise RuleError("title can't be empty")
    if "url" in changes:
        yt = youtube_video_id(changes["url"])
        taken = yt is not None and yt != v.youtube_video_id and db.scalar(
            select(Video.id).where(Video.user_id == user.id, Video.youtube_video_id == yt))
        if taken:
            raise Conflict("That video is already in your library")
        v.youtube_video_id = yt
    for field, value in changes.items():
        setattr(v, field, value)
    db.commit()
    return v


def remove_video(db: Session, user: User, video_id: int, now: datetime | None = None) -> Video:
    """Hide the video from the library, counts and recommendations. Reversible; nothing happens on YouTube."""
    v = _get_video(db, user, video_id)
    v.removed_at = now or datetime.now(timezone.utc)
    db.commit()
    return v


def restore_video(db: Session, user: User, video_id: int) -> Video:
    v = _get_video(db, user, video_id, include_removed=True)
    v.removed_at = None
    db.commit()
    return v


def delete_video(db: Session, user: User, video_id: int) -> None:
    """Permanently erase the video (removed or not). It can be imported again later as a brand-new video."""
    db.delete(_get_video(db, user, video_id, include_removed=True))
    db.commit()


def start_video(db: Session, user: User, video_id: int) -> Video:
    v = _get_video(db, user, video_id)
    if v.status == "completed":
        raise RuleError("This video is already completed; reopen it first")
    v.status = "watching"
    db.commit()
    return v


def complete_video(db: Session, user: User, video_id: int, now: datetime | None = None) -> Video:
    v = _get_video(db, user, video_id)
    if v.status != "completed":  # idempotent: the first completion time is kept
        v.status = "completed"
        v.completed_at = now or datetime.now(timezone.utc)
    db.commit()
    return v


def uncomplete_video(db: Session, user: User, video_id: int) -> Video:
    v = _get_video(db, user, video_id)
    v.status = "unwatched"
    v.completed_at = None
    db.commit()
    return v


def set_status(db: Session, user: User, video_id: int, status: str, now: datetime | None = None) -> Video:
    """Explicit status change (the UI's status menu). Moving away from completed clears the completion time."""
    if status == "completed":
        return complete_video(db, user, video_id, now)
    v = _get_video(db, user, video_id)
    v.status = status
    v.completed_at = None
    db.commit()
    return v


def move_video(db: Session, user: User, video_id: int, direction: str, playlist_id: int) -> Video:
    """Swap a video with its neighbour in a collection's manual order (matters when recommend_order is 'manual')."""
    v = _get_video(db, user, video_id)
    p = _get_playlist(db, user, playlist_id)
    rows = list(db.scalars(select(VideoMembership).where(VideoMembership.playlist_id == p.id)
                           .order_by(VideoMembership.position, VideoMembership.id)))
    mine = next((m for m in rows if m.video_id == v.id), None)
    if mine is None:
        raise NotFound("Video not found")
    i = rows.index(mine)
    j = i - 1 if direction == "up" else i + 1
    if 0 <= j < len(rows):
        # Renumber the whole list 1..n so equal/gappy positions can never make a swap a no-op.
        rows[i], rows[j] = rows[j], rows[i]
        for n, m in enumerate(rows, start=1):
            m.position = n
    db.commit()
    return v
