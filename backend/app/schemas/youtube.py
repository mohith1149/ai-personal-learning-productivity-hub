"""Request/response models for the YouTube channel / playlist import."""
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field

from app.schemas.common import Strict
from app.schemas.videos import PlaylistSummary

VideoId = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{11}$")]


class PreviewRequest(Strict):
    url: str = Field(min_length=1, max_length=500)
    limit: int | None = Field(default=25, ge=1, le=2000)  # how many videos to retrieve; null = all (capped)


class ImportRequest(Strict):
    url: str = Field(min_length=1, max_length=500)
    video_ids: list[VideoId] = Field(min_length=1, max_length=2000)  # exactly the videos the user ticked
    retrieved: int = Field(default=0, ge=0, le=100000)  # how many the preview fetched (shown beside the reported total)


class StatusOut(BaseModel):
    configured: bool  # whether a key is set. The key itself is never returned.


class SourceOut(BaseModel):
    kind: str  # "channel" | "playlist"
    id: str
    title: str
    url: str
    thumbnail_url: str | None
    total_available: int | None  # what YouTube reports; None = unavailable
    handle: str | None
    channel_title: str | None


class PreviewVideo(BaseModel):
    youtube_video_id: str
    title: str
    url: str
    thumbnail_url: str | None
    duration_seconds: int | None
    published_at: datetime | None
    channel_title: str | None
    in_library: bool  # already imported (and not removed)
    removed: bool  # imported before and removed; importing it again restores it
    status: str | None  # its status if it is in the library


class PreviewOut(BaseModel):
    source: SourceOut
    retrieved: int  # videos actually fetched in this preview
    unavailable: int  # listed by YouTube but private/deleted
    more_available: bool  # YouTube has more than were fetched
    already_in_library: int
    videos: list[PreviewVideo]


class ImportOut(BaseModel):
    collection: PlaylistSummary
    created: int  # new library videos
    linked: int  # already in the library (or restored), now also in this collection
    already_in_collection: int
    unavailable: int  # selected but no longer available on YouTube
