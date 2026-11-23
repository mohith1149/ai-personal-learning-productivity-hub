"""Request/response models for tasks, categories and recurring tasks.

Validation that needs only the request itself lives here; rules that depend on stored data
(e.g. "due date not before the existing scheduled date" on a partial update) live in services/tasks.py.
"""
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.common import Strict as _Strict

HHMM = r"^([01]\d|2[0-3]):[0-5]\d$"
COLOR = r"^#[0-9a-fA-F]{6}$"

Priority = Annotated[int, Field(ge=1, le=4, description="1=urgent, 2=high, 3=normal, 4=low")]
Minutes = Annotated[int, Field(ge=1, le=1440)]
ShortText = Annotated[str, Field(max_length=5000)]


# ---------- categories ----------


class CategoryCreate(_Strict):
    name: str = Field(min_length=1, max_length=80)
    color: str = Field(default="#6366f1", pattern=COLOR)


class CategoryUpdate(_Strict):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    color: str | None = Field(default=None, pattern=COLOR)


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    color: str
    is_system: bool


class CategoryBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    color: str


# ---------- tasks ----------


class TaskCreate(_Strict):
    title: str = Field(min_length=1, max_length=200)
    description: ShortText | None = None
    notes: ShortText | None = None
    category_id: int | None = None
    priority: Priority = 3
    status: Literal["pending", "in_progress"] = "pending"
    scheduled_date: date | None = None
    due_date: date | None = None
    due_time: str | None = Field(default=None, pattern=HHMM)
    estimated_minutes: Minutes | None = None


class TaskUpdate(_Strict):
    """Partial update: only fields present in the request are changed; an explicit null clears optional ones."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: ShortText | None = None
    notes: ShortText | None = None
    category_id: int | None = None
    priority: Priority | None = None
    status: Literal["pending", "in_progress", "completed", "cancelled"] | None = None
    scheduled_date: date | None = None
    due_date: date | None = None
    due_time: str | None = Field(default=None, pattern=HHMM)
    estimated_minutes: Minutes | None = None
    actual_minutes: Minutes | None = None


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    description: str | None
    notes: str | None
    category_id: int | None
    category: CategoryBrief | None
    task_type: str
    priority: int
    status: str
    scheduled_date: date | None
    due_date: date | None
    due_time: str | None
    estimated_minutes: int | None
    actual_minutes: int | None
    completed_at: datetime | None
    recurring_task_id: int | None
    is_overdue: bool = False  # computed per request in the user's timezone, never stored
    created_at: datetime
    updated_at: datetime


class TaskList(BaseModel):
    items: list[TaskOut]
    total: int


class TaskCounts(BaseModel):
    open: int
    overdue: int
    today: int
    upcoming: int
    completed: int
    completed_today: int
    all: int


# ---------- recurring ----------


class RecurringCreate(_Strict):
    title: str = Field(min_length=1, max_length=200)
    description: ShortText | None = None
    category_id: int | None = None
    priority: Priority = 3
    estimated_minutes: Minutes | None = None
    frequency: Literal["daily", "weekdays", "weekly", "monthly"]
    days_of_week: list[Annotated[int, Field(ge=0, le=6)]] | None = Field(
        default=None, description="Weekly only. Monday=0 … Sunday=6"
    )
    day_of_month: int | None = Field(default=None, ge=1, le=31, description="Monthly only")
    start_date: date | None = None  # defaults to today (user's timezone)
    end_date: date | None = None


class RecurringUpdate(_Strict):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: ShortText | None = None
    category_id: int | None = None
    priority: Priority | None = None
    estimated_minutes: Minutes | None = None
    frequency: Literal["daily", "weekdays", "weekly", "monthly"] | None = None
    days_of_week: list[Annotated[int, Field(ge=0, le=6)]] | None = None
    day_of_month: int | None = Field(default=None, ge=1, le=31)
    end_date: date | None = None
    active: bool | None = None


class RecurringOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    description: str | None
    category_id: int | None
    category: CategoryBrief | None
    priority: int
    estimated_minutes: int | None
    frequency: str
    days_of_week: list[int] | None
    day_of_month: int | None
    start_date: date
    end_date: date | None
    active: bool
    last_generated_date: date | None

    @field_validator("days_of_week", mode="before")
    @classmethod
    def _split(cls, v):
        # Stored as "0,2,4"; exposed as [0, 2, 4].
        if isinstance(v, str):
            return [int(p) for p in v.split(",") if p != ""]
        return v
