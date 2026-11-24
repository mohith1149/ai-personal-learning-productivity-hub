"""Video playlist business logic.

Rules implemented here:
  * Every query is scoped to the owning user. Ownership of a video is always checked through its playlist, and
    someone else's id behaves exactly like "not found".
  * A video is completed ONLY by an explicit call (`complete_video`). Completing twice keeps the first completion time.
  * RECOMMENDATION RULE: the next video is chosen by SQL (`status != 'completed' ORDER BY position`). A completed video
    can therefore never be returned by `next_videos` / `next_video_overall` - the UI does not filter, the query does.
    (Un-completing a video is an explicit user action; only then can it be recommended again.)
  * "Watched today" counts completions inside the user's LOCAL calendar day, not the server's.
  * The application cannot see anyone's YouTube history: progress is only what is recorded here.
"""
import re
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlsplit

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.timeutil import local_day_bounds_utc, user_today
from app.models import User, Video, VideoPlaylist
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


# ============================== playlists ==============================


def _get_playlist(db: Session, user: User, playlist_id: int) -> VideoPlaylist:
    p = db.scalar(select(VideoPlaylist).where(VideoPlaylist.id == playlist_id, VideoPlaylist.user_id == user.id))
    if p is None:
        raise NotFound("Playlist not found")
    return p


def _get_video(db: Session, user: User, video_id: int) -> Video:
    v = db.scalar(
        select(Video)
        .join(VideoPlaylist, VideoPlaylist.id == Video.playlist_id)
        .where(Video.id == video_id, VideoPlaylist.user_id == user.id)
    )
    if v is None:
        raise NotFound("Video not found")
    return v


def _open_videos(playlist_id: int):
    """THE recommendation query: every video that is not completed, in playlist order."""
    return (
        select(Video)
        .where(Video.playlist_id == playlist_id, Video.status != "completed")
        .order_by(Video.position, Video.id)
    )


def next_videos(db: Session, playlist_id: int, limit: int) -> list[Video]:
    return list(db.scalars(_open_videos(playlist_id).limit(limit))) if limit > 0 else []


def next_video_overall(db: Session, user: User) -> Video | None:
    """First not-completed video across the user's ACTIVE playlists (oldest playlist first)."""
    return db.scalar(
        select(Video)
        .join(VideoPlaylist, VideoPlaylist.id == Video.playlist_id)
        .where(VideoPlaylist.user_id == user.id, VideoPlaylist.active.is_(True), Video.status != "completed")
        .order_by(VideoPlaylist.id, Video.position, Video.id)
    )


def _watched_today(db: Session, user: User, playlist_ids: list[int], now: datetime | None) -> dict[int, int]:
    if not playlist_ids:
        return {}
    start, end = local_day_bounds_utc(user, user_today(user, now))
    rows = db.execute(
        select(Video.playlist_id, func.count())
        .where(Video.playlist_id.in_(playlist_ids), Video.status == "completed",
               Video.completed_at >= start, Video.completed_at < end)
        .group_by(Video.playlist_id)
    )
    return {pid: n for pid, n in rows}


def _summaries(db: Session, user: User, playlists: list[VideoPlaylist], now: datetime | None) -> list[dict]:
    ids = [p.id for p in playlists]
    counts: dict[int, tuple[int, int]] = {}
    if ids:
        rows = db.execute(
            select(Video.playlist_id, func.count(), func.sum(case((Video.status == "completed", 1), else_=0)))
            .where(Video.playlist_id.in_(ids)).group_by(Video.playlist_id)
        )
        counts = {pid: (int(total), int(done or 0)) for pid, total, done in rows}
    today = _watched_today(db, user, ids, now)
    out = []
    for p in playlists:
        total, done = counts.get(p.id, (0, 0))
        watched = today.get(p.id, 0)
        nxt = next_videos(db, p.id, 1)
        out.append({
            "id": p.id, "name": p.name, "source_url": p.source_url, "youtube_playlist_id": p.youtube_playlist_id,
            "description": p.description, "daily_target": p.daily_target, "active": p.active,
            "total_videos": total, "completed_videos": done, "percent": (100 * done) // total if total else 0,
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
    for required in ("name", "daily_target", "active"):
        if required in changes and changes[required] is None:
            raise RuleError(f"{required} can't be empty")
    if "name" in changes and _name_taken(db, user, changes["name"], except_id=p.id):
        raise Conflict("You already have a playlist with that name")
    for field, value in changes.items():
        setattr(p, field, value)
    db.commit()
    return p


def delete_playlist(db: Session, user: User, playlist_id: int) -> None:
    db.delete(_get_playlist(db, user, playlist_id))  # its videos go with it (cascade)
    db.commit()


# ============================== videos ==============================


def _next_position(db: Session, playlist_id: int) -> int:
    return (db.scalar(select(func.max(Video.position)).where(Video.playlist_id == playlist_id)) or 0) + 1


def _exists(db: Session, playlist_id: int, yt_id: str | None) -> bool:
    return yt_id is not None and db.scalar(
        select(Video.id).where(Video.playlist_id == playlist_id, Video.youtube_video_id == yt_id)) is not None


def add_video(db: Session, user: User, playlist_id: int, data: s.VideoCreate) -> Video:
    p = _get_playlist(db, user, playlist_id)
    yt = youtube_video_id(data.url)
    if _exists(db, p.id, yt):
        raise Conflict("That video is already in this playlist")
    v = Video(user_id=user.id, playlist_id=p.id, youtube_video_id=yt, position=_next_position(db, p.id),
              **data.model_dump())
    db.add(v)
    db.commit()
    return v


def bulk_add_videos(db: Session, user: User, playlist_id: int, data: s.BulkVideos) -> dict:
    p = _get_playlist(db, user, playlist_id)
    pos = _next_position(db, p.id)
    seen: set[str] = set()
    added = duplicates = 0
    invalid: list[str] = []
    for raw in data.lines:
        parsed = parse_line(raw)
        if parsed is None:
            invalid.append(raw[:120])
            continue
        title, url = parsed
        yt = youtube_video_id(url)
        if (yt and (yt in seen or _exists(db, p.id, yt))) or (not yt and url in seen):
            duplicates += 1
            continue
        seen.add(yt or url)
        db.add(Video(user_id=user.id, playlist_id=p.id, title=title, url=url, youtube_video_id=yt,
                     category=data.category, position=pos))
        pos += 1
        added += 1
    db.commit()
    return {"added": added, "duplicates": duplicates, "invalid": invalid}


def list_videos(db: Session, user: User, playlist_id: int, view: str = "all", q: str | None = None,
                limit: int = 100, offset: int = 0) -> dict:
    p = _get_playlist(db, user, playlist_id)
    where = [Video.playlist_id == p.id]
    if view == "open":
        where.append(Video.status != "completed")
    elif view == "completed":
        where.append(Video.status == "completed")
    if q:
        like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        where.append(Video.title.ilike(like, escape="\\"))
    total = db.scalar(select(func.count()).select_from(Video).where(*where)) or 0
    order = (Video.completed_at.desc(), Video.id) if view == "completed" else (Video.position, Video.id)
    items = list(db.scalars(select(Video).where(*where).order_by(*order).limit(limit).offset(offset)))
    return {"items": items, "total": total}


def today(db: Session, user: User, playlist_id: int, now: datetime | None = None) -> dict:
    summary = playlist_summary(db, user, playlist_id, now)
    remaining = summary["remaining_today"]
    return {
        "daily_target": summary["daily_target"], "watched_today": summary["watched_today"],
        "remaining_today": remaining, "target_met": remaining == 0,
        "up_next": next_videos(db, playlist_id, remaining),
    }


def update_video(db: Session, user: User, video_id: int, data: s.VideoUpdate) -> Video:
    v = _get_video(db, user, video_id)
    changes = data.model_dump(exclude_unset=True)
    if changes.get("title", "x") is None:
        raise RuleError("title can't be empty")
    if "url" in changes:
        yt = youtube_video_id(changes["url"])
        if yt != v.youtube_video_id and _exists(db, v.playlist_id, yt):
            raise Conflict("That video is already in this playlist")
        v.youtube_video_id = yt
    for field, value in changes.items():
        setattr(v, field, value)
    db.commit()
    return v


def delete_video(db: Session, user: User, video_id: int) -> None:
    db.delete(_get_video(db, user, video_id))
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


def move_video(db: Session, user: User, video_id: int, direction: str) -> Video:
    v = _get_video(db, user, video_id)
    siblings = list(db.scalars(select(Video).where(Video.playlist_id == v.playlist_id)
                               .order_by(Video.position, Video.id)))
    i = siblings.index(v)
    j = i - 1 if direction == "up" else i + 1
    if 0 <= j < len(siblings):
        # Renumber the whole list 1..n so equal/gappy positions can never make a swap a no-op.
        siblings[i], siblings[j] = siblings[j], siblings[i]
        for n, item in enumerate(siblings, start=1):
            item.position = n
    db.commit()
    return v
