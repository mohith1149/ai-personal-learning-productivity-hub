"""Request/response models for the daily planner."""
from datetime import date as DateT
from typing import Literal

from pydantic import BaseModel, Field

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


class DayPlan(BaseModel):
    date: DateT
    is_today: bool
    items: list[PlanItem]
    summary: DaySummary
