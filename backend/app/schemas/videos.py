"""Request/response models for video playlists and videos."""
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.common import Strict
from app.schemas.courses import Notes, Url, _HasUrl, _check_url

DailyTarget = Annotated[int, Field(ge=1, le=50)]
Line = Annotated[str, Field(min_length=1, max_length=600)]


class _HasSourceUrl(Strict):
    @field_validator("source_url", check_fields=False)
    @classmethod
    def _source_ok(cls, v):
        return _check_url(v)  # only http(s): the link is rendered as a clickable anchor


RecommendOrder = Literal["oldest", "newest", "manual"]
VideoStatus = Literal["unwatched", "watching", "completed"]


class PlaylistCreate(_HasSourceUrl):
    name: str = Field(min_length=1, max_length=120)
    source_url: Url | None = None
    description: Notes | None = None
    daily_target: DailyTarget = 1
    active: bool = True
    recommend_order: RecommendOrder = "oldest"


class PlaylistUpdate(_HasSourceUrl):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    source_url: Url | None = None
    description: Notes | None = None
    daily_target: DailyTarget | None = None
    active: bool | None = None
    recommend_order: RecommendOrder | None = None


class VideoCreate(_HasUrl):
    title: str = Field(min_length=1, max_length=300)
    url: Url | None = None
    description: Notes | None = None
    category: str | None = Field(default=None, max_length=80)
    notes: Notes | None = None


class VideoUpdate(_HasUrl):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    url: Url | None = None
    description: Notes | None = None
    category: str | None = Field(default=None, max_length=80)
    notes: Notes | None = None


class BulkVideos(Strict):
    """Pasted lines: `https://...`, `Title | https://...` or `Title - https://...`, one video per line."""

    lines: list[Line] = Field(min_length=1, max_length=200)
    category: str | None = Field(default=None, max_length=80)


class Move(Strict):
    direction: Literal["up", "down"]
    playlist_id: int  # the order is per collection


class SetStatus(Strict):
    status: VideoStatus


class VideoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    url: str | None
    youtube_video_id: str | None
    description: str | None
    category: str | None
    status: str
    completed_at: datetime | None
    notes: str | None
    thumbnail_url: str | None
    duration_seconds: int | None
    published_at: datetime | None
    channel_id: str | None
    channel_title: str | None
    removed_at: datetime | None
    created_at: datetime  # "date added"
    playlist_ids: list[int]


class VideoList(BaseModel):
    items: list[VideoOut]
    total: int


class PlaylistSummary(BaseModel):
    id: int
    name: str
    kind: str
    source_url: str | None
    youtube_playlist_id: str | None
    youtube_channel_id: str | None
    thumbnail_url: str | None
    description: str | None
    daily_target: int
    active: bool
    recommend_order: str
    reported_total: int | None  # what YouTube said exists; None = unavailable (never estimated)
    retrieved_count: int  # how many the last fetch actually retrieved
    total_videos: int  # in the library (removed ones excluded)
    completed_videos: int
    in_progress_videos: int
    unwatched_videos: int
    percent: int  # completed / total in library, floored, so 100 only when every video is watched
    watched_today: int  # videos completed during the user's local day
    remaining_today: int  # max(daily_target - watched_today, 0)
    next_video: VideoOut | None
    created_at: datetime


class LibraryStats(BaseModel):
    """Overall progress across the whole library (removed videos are not counted)."""

    total: int
    completed: int
    in_progress: int
    unwatched: int
    percent: int
    removed: int
    next_video: VideoOut | None


class TodayOut(BaseModel):
    daily_target: int
    watched_today: int
    remaining_today: int
    target_met: bool
    up_next: list[VideoOut]  # the next `remaining_today` unwatched videos, in order


class BulkResult(BaseModel):
    added: int  # new library videos
    linked: int  # already in the library, now also in this playlist
    duplicates: int  # already in this playlist
    invalid: list[str]
