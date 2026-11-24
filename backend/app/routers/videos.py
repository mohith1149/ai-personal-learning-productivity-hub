"""HTTP endpoints for video playlists and videos. Thin: validate -> call service -> serialise. Login required."""
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.core.deps import CurrentUser, DbSession
from app.schemas import videos as s
from app.services import videos as svc

playlists_router = APIRouter(prefix="/video-playlists", tags=["videos"])
videos_router = APIRouter(prefix="/videos", tags=["videos"])

ERRORS = (svc.NotFound, svc.RuleError, svc.Conflict)


def _http(exc: Exception) -> HTTPException:
    if isinstance(exc, svc.NotFound):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    if isinstance(exc, svc.Conflict):
        return HTTPException(status.HTTP_409_CONFLICT, str(exc))
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc))


def _run(fn, *args):
    try:
        return fn(*args)
    except ERRORS as e:
        raise _http(e) from None


# ---------------- playlists ----------------


@playlists_router.get("", response_model=list[s.PlaylistSummary])
def list_playlists(user: CurrentUser, db: DbSession):
    return svc.list_playlists(db, user)


@playlists_router.post("", response_model=s.PlaylistSummary, status_code=status.HTTP_201_CREATED)
def create_playlist(body: s.PlaylistCreate, user: CurrentUser, db: DbSession):
    p = _run(svc.create_playlist, db, user, body)
    return svc.playlist_summary(db, user, p.id)


@playlists_router.get("/{playlist_id}", response_model=s.PlaylistSummary)
def get_playlist(playlist_id: int, user: CurrentUser, db: DbSession):
    return _run(svc.playlist_summary, db, user, playlist_id)


@playlists_router.patch("/{playlist_id}", response_model=s.PlaylistSummary)
def update_playlist(playlist_id: int, body: s.PlaylistUpdate, user: CurrentUser, db: DbSession):
    _run(svc.update_playlist, db, user, playlist_id, body)
    return svc.playlist_summary(db, user, playlist_id)


@playlists_router.delete("/{playlist_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_playlist(playlist_id: int, user: CurrentUser, db: DbSession) -> Response:
    _run(svc.delete_playlist, db, user, playlist_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@playlists_router.get("/{playlist_id}/today", response_model=s.TodayOut)
def playlist_today(playlist_id: int, user: CurrentUser, db: DbSession):
    return _run(svc.today, db, user, playlist_id)


@playlists_router.get("/{playlist_id}/videos", response_model=s.VideoList)
def list_videos(
    playlist_id: int, user: CurrentUser, db: DbSession,
    view: Literal["all", "open", "completed"] = "all",
    q: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return _run(svc.list_videos, db, user, playlist_id, view, q, limit, offset)


@playlists_router.post("/{playlist_id}/videos", response_model=s.VideoOut, status_code=status.HTTP_201_CREATED)
def add_video(playlist_id: int, body: s.VideoCreate, user: CurrentUser, db: DbSession):
    return _run(svc.add_video, db, user, playlist_id, body)


@playlists_router.post("/{playlist_id}/bulk-videos", response_model=s.BulkResult, status_code=status.HTTP_201_CREATED)
def bulk_add_videos(playlist_id: int, body: s.BulkVideos, user: CurrentUser, db: DbSession):
    return _run(svc.bulk_add_videos, db, user, playlist_id, body)


# ---------------- videos ----------------


@videos_router.get("/next", response_model=s.VideoOut | None)
def next_video(user: CurrentUser, db: DbSession):
    return svc.next_video_overall(db, user)


@videos_router.patch("/{video_id}", response_model=s.VideoOut)
def update_video(video_id: int, body: s.VideoUpdate, user: CurrentUser, db: DbSession):
    return _run(svc.update_video, db, user, video_id, body)


@videos_router.delete("/{video_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_video(video_id: int, user: CurrentUser, db: DbSession) -> Response:
    _run(svc.delete_video, db, user, video_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@videos_router.post("/{video_id}/start", response_model=s.VideoOut)
def start_video(video_id: int, user: CurrentUser, db: DbSession):
    return _run(svc.start_video, db, user, video_id)


@videos_router.post("/{video_id}/complete", response_model=s.VideoOut)
def complete_video(video_id: int, user: CurrentUser, db: DbSession):
    return _run(svc.complete_video, db, user, video_id)


@videos_router.post("/{video_id}/uncomplete", response_model=s.VideoOut)
def uncomplete_video(video_id: int, user: CurrentUser, db: DbSession):
    return _run(svc.uncomplete_video, db, user, video_id)


@videos_router.post("/{video_id}/move", response_model=s.VideoOut)
def move_video(video_id: int, body: s.Move, user: CurrentUser, db: DbSession):
    return _run(svc.move_video, db, user, video_id, body.direction)
