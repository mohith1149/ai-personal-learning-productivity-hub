"""Request/response models for habits."""
from datetime import date as DateT, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.common import Strict
from app.schemas.courses import Notes

Frequency = Literal["daily", "weekly"]
Value = Annotated[float, Field(ge=0, le=1_000_000)]


class _Target(Strict):
    @model_validator(mode="after")
    def _check(self):
        freq = getattr(self, "frequency", None)
        per = getattr(self, "target_per_period", None)
        if freq == "daily" and per not in (None, 1):
            raise ValueError("A daily habit is done once a day; use a weekly habit for 'N days a week'")
        if per is not None and not 1 <= per <= 7:
            raise ValueError("Days per week must be from 1 to 7")
        return self


class HabitCreate(_Target):
    name: str = Field(min_length=1, max_length=120)
    description: Notes | None = None
    notes: Notes | None = None
    start_date: DateT | None = None  # defaults to today in the user's timezone
    frequency: Frequency = "daily"
    target_per_period: int = 1  # weekly: days per week
    target_value: Annotated[float, Field(gt=0, le=1_000_000)] | None = None  # optional daily amount, e.g. 30
    unit: str | None = Field(default=None, max_length=30)  # e.g. "minutes"
    active: bool = True


class HabitUpdate(_Target):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: Notes | None = None
    notes: Notes | None = None
    start_date: DateT | None = None
    frequency: Frequency | None = None
    target_per_period: int | None = None
    target_value: Annotated[float, Field(gt=0, le=1_000_000)] | None = None
    unit: str | None = Field(default=None, max_length=30)
    active: bool | None = None


class LogIn(Strict):
    completed: bool = True
    value: Value | None = None
    note: Notes | None = None


class LogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    date: DateT
    completed: bool
    value: float | None
    note: str | None


class Streak(BaseModel):
    current: int
    longest: int
    unit: str  # "days" for daily habits, "weeks" (weeks that met the target) for weekly ones


class Window(BaseModel):
    start: DateT
    end: DateT
    completed: int  # days completed in the window
    eligible_days: int  # days in the window that count (on/after the start date, not in the future)
    target: int | None  # weekly habits: the days-per-week goal (this-week window only)
    percent: int | None  # floor(completed / (target or eligible_days) * 100), capped at 100; None when there is nothing to measure


class RecentDay(BaseModel):
    date: DateT
    completed: bool
    logged: bool


class HabitOut(BaseModel):
    id: int
    name: str
    description: str | None
    notes: str | None
    start_date: DateT
    frequency: str
    target_per_period: int
    target_value: float | None
    unit: str | None
    active: bool
    created_at: datetime
    today: LogOut | None  # today's record, if any
    done_today: bool
    streak: Streak
    week: Window
    month: Window
    total_completed: int
    recent: list[RecentDay]  # the last 28 days, oldest first


class HabitList(BaseModel):
    items: list[HabitOut]
    due_today: int  # active habits not yet completed today (daily: always due; weekly: until the week's target is met)
