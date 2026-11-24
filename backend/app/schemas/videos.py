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


class PlaylistCreate(_HasSourceUrl):
    name: str = Field(min_length=1, max_length=120)
    source_url: Url | None = None
    description: Notes | None = None
    daily_target: DailyTarget = 1
    active: bool = True


class PlaylistUpdate(_HasSourceUrl):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    source_url: Url | None = None
    description: Notes | None = None
    daily_target: DailyTarget | None = None
    active: bool | None = None


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


class VideoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    playlist_id: int
    title: str
    url: str | None
    youtube_video_id: str | None
    description: str | None
    category: str | None
    status: str
    position: int
    completed_at: datetime | None
    notes: str | None
    created_at: datetime


class VideoList(BaseModel):
    items: list[VideoOut]
    total: int


class PlaylistSummary(BaseModel):
    id: int
    name: str
    source_url: str | None
    youtube_playlist_id: str | None
    description: str | None
    daily_target: int
    active: bool
    total_videos: int
    completed_videos: int
    percent: int  # floor, so 100 only when every video is watched
    watched_today: int  # videos completed during the user's local day
    remaining_today: int  # max(daily_target - watched_today, 0)
    next_video: VideoOut | None
    created_at: datetime


class TodayOut(BaseModel):
    daily_target: int
    watched_today: int
    remaining_today: int
    target_met: bool
    up_next: list[VideoOut]  # the next `remaining_today` unwatched videos, in order


class BulkResult(BaseModel):
    added: int
    duplicates: int
    invalid: list[str]
