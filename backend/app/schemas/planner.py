"""Request/response models for the daily planner."""
from datetime import date as DateT
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import Strict

Kind = Literal["task", "lesson", "video", "topic", "habit", "project"]
ItemStatus = Literal["pending", "overdue", "completed", "excused"]


class ItemRef(Strict):
    kind: Kind
    ref_id: int
    date: DateT  # the day of the plan the item was acted on from


class ExcuseIn(ItemRef):
    reason: str = Field(min_length=3, max_length=1000)


class RescheduleIn(Strict):
    date: DateT  # the new day for the task
    from_date: DateT  # the plan day being viewed (the reply is that day's refreshed plan)
    move_due_date: bool = False  # also move the task's deadline (otherwise only the day you plan to do it moves)


class PlanItem(BaseModel):
    key: str  # "task:12" - unique within a day
    kind: Kind
    ref_id: int
    title: str
    subtitle: str | None
    status: ItemStatus
    due_date: DateT | None
    minutes: int | None  # estimated / lesson length / video length, when known
    excuse_reason: str | None
    can_complete: bool  # can be completed straight from the planner
    can_reschedule: bool  # tasks only
    can_excuse: bool
    link: str  # page inside the app where the activity lives
    url: str | None  # external link (lesson / video), if any
    carry_count: int = 0  # how many times this task was moved to another day
    slipping: bool = False  # moved 3 or more times and still open


class KindCount(BaseModel):
    kind: Kind
    total: int  # excused items are not counted
    completed: int


class DaySummary(BaseModel):
    total: int  # activities that count (excused ones are left out)
    completed: int
    pending: int
    overdue: int
    excused: int
    percent: int  # floor(completed / total), 0 when there is nothing to do
    study_minutes: int  # logged study sessions (courses + roadmap topics) on this day
    dev_minutes: int  # logged project development sessions on this day
    by_kind: list[KindCount]
    rest_day: bool = False  # a planned rest day: open items are left out of the percentage
    planned_minutes: int = 0  # time of the items that count (estimates, lesson/video lengths, minutes already logged)
    available_minutes: int | None = None  # the hours you set for this weekday; None = not set
    unestimated: int = 0  # open items with no time, so they are not in planned_minutes
    overloaded: bool = False  # planned_minutes is more than available_minutes


class DayPlan(BaseModel):
    date: DateT
    is_today: bool
    items: list[PlanItem]
    summary: DaySummary


class RollOverIn(Strict):
    task_ids: list[int] | None = Field(default=None, max_length=200)  # None = every unfinished task
    dry_run: bool = False  # preview: change nothing


class MovedTask(BaseModel):
    task_id: int
    title: str
    carry_count: int
    minutes: int | None
    slipping: bool


class TomorrowLoad(BaseModel):
    date: DateT
    total: int
    planned_minutes: int
    available_minutes: int | None
    overloaded: bool
    unestimated: int
    rest_day: bool


class RollOverOut(BaseModel):
    dry_run: bool
    moved: list[MovedTask]
    tomorrow: TomorrowLoad


class Preferences(BaseModel):
    weekday_minutes: list[int] | None  # Monday..Sunday; None = not set
    rest_days_per_month: int


class PreferencesIn(Strict):
    weekday_minutes: list[int] | None = None
    rest_days_per_month: int | None = Field(default=None, ge=0, le=31)

    @field_validator("weekday_minutes")
    @classmethod
    def _week(cls, v):
        if v is not None and (len(v) != 7 or any(not 0 <= m <= 1440 for m in v)):
            raise ValueError("Give 7 values (Monday to Sunday), each between 0 and 1440 minutes")
        return v
