"""Request/response models for courses, modules, lessons, study sessions and course templates."""
from datetime import date as DateT, datetime
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.common import Strict

Priority = Annotated[int, Field(ge=1, le=4, description="1=urgent, 2=high, 3=normal, 4=low")]
Minutes = Annotated[int, Field(ge=1, le=1440)]
Notes = Annotated[str, Field(max_length=10000)]
Url = Annotated[str, Field(max_length=500)]


def _check_url(v: str | None) -> str | None:
    """Links are rendered as clickable <a href>, so only http(s) is allowed (blocks javascript:/data: links)."""
    if v is None:
        return v
    parts = urlsplit(v)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise ValueError("Enter a full web address starting with http:// or https://")
    return v


class _HasUrl(Strict):
    @field_validator("url", check_fields=False)
    @classmethod
    def _url_ok(cls, v):
        return _check_url(v)


# ---------- courses ----------


class CourseCreate(_HasUrl):
    title: str = Field(min_length=1, max_length=200)
    provider: str | None = Field(default=None, max_length=100)
    url: Url | None = None
    description: Notes | None = None
    notes: Notes | None = None
    kind: Literal["course", "video_series"] = "course"
    priority: Priority = 2
    target_date: DateT | None = None


class CourseUpdate(_HasUrl):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    provider: str | None = Field(default=None, max_length=100)
    url: Url | None = None
    description: Notes | None = None
    notes: Notes | None = None
    kind: Literal["course", "video_series"] | None = None
    priority: Priority | None = None
    target_date: DateT | None = None
    status: Literal["active", "paused", "archived", "completed"] | None = None


# ---------- modules / lessons ----------


class ModuleCreate(Strict):
    title: str = Field(min_length=1, max_length=200)


class ModuleUpdate(Strict):
    title: str = Field(min_length=1, max_length=200)


class LessonCreate(_HasUrl):
    title: str = Field(min_length=1, max_length=300)
    url: Url | None = None
    lesson_type: Literal["lesson", "video"] = "lesson"
    duration_minutes: Minutes | None = None
    notes: Notes | None = None


class LessonUpdate(_HasUrl):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    url: Url | None = None
    lesson_type: Literal["lesson", "video"] | None = None
    duration_minutes: Minutes | None = None
    notes: Notes | None = None
    module_id: int | None = Field(default=None, description="Move the lesson to another module of the same course")


class BulkLessons(Strict):
    module_id: int
    titles: list[Annotated[str, Field(min_length=1, max_length=300)]] = Field(min_length=1, max_length=200)


class Move(Strict):
    direction: Literal["up", "down"]


class LessonOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    module_id: int
    course_id: int
    title: str
    url: str | None
    lesson_type: str
    duration_minutes: int | None
    position: int
    status: str
    completed_at: datetime | None
    notes: str | None


class ModuleOut(BaseModel):
    id: int
    title: str
    position: int
    total_lessons: int
    completed_lessons: int
    lessons: list[LessonOut]


class Progress(BaseModel):
    total_lessons: int
    completed_lessons: int
    percent: int  # floor, so it only reads 100 when EVERY lesson is done
    empty_modules: int  # modules with no lessons yet; while any exist the course cannot be completed
    total_minutes: int  # sum of known lesson durations
    remaining_minutes: int  # known durations of lessons not yet completed


class NextLesson(BaseModel):
    id: int
    title: str
    module_id: int
    module_title: str
    status: str
    url: str | None


class CourseSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    provider: str | None
    url: str | None
    description: str | None
    kind: str
    status: str
    priority: int
    target_date: DateT | None
    started_at: datetime | None
    completed_at: datetime | None
    last_studied_at: datetime | None
    progress: Progress
    next_lesson: NextLesson | None
    minutes_studied: int


class CourseDetail(CourseSummary):
    notes: str | None
    modules: list[ModuleOut]


# ---------- study sessions ----------


class SessionCreate(Strict):
    course_id: int
    lesson_id: int | None = None
    minutes: Minutes
    date: DateT | None = None  # defaults to today in the user's timezone; the future is not allowed
    notes: Notes | None = None


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    date: DateT
    minutes: int
    course_id: int | None
    lesson_id: int | None
    notes: str | None
    created_at: datetime


# ---------- templates ----------


class TemplateOut(BaseModel):
    key: str
    title: str
    provider: str
    url: str
    description: str
    modules: list[str]
    already_added: bool
