"""Response models for the weekly and monthly reports. Read-only: every figure is computed from your records on each request."""
from datetime import date
from typing import Literal

from pydantic import BaseModel


class Period(BaseModel):
    kind: Literal["week", "month"]
    start: date
    end: date
    label: str
    days: int
    is_current: bool  # the period contains today
    through: date  # the last day that counts (today for the current period, else end); later days are future and show no activity


class ReportDay(BaseModel):
    date: date
    tasks_done: int
    lessons_done: int
    videos_done: int
    topics_done: int
    items_done: int  # the four above together
    study_minutes: int
    project_minutes: int
    habits_done: int
    challenge: Literal["completed", "excused", "missed", "planned", "in_progress", "none"]
    plan_total: int | None  # None for days that have not happened yet
    plan_completed: int | None


class Totals(BaseModel):
    tasks_done: int
    lessons_done: int
    videos_done: int
    topics_done: int
    items_done: int
    study_minutes: int
    project_minutes: int
    habits_done: int
    challenge_days: int  # days with a completed challenge


class PlanTotals(BaseModel):
    total: int
    completed: int
    percent: int  # floored; 0 when nothing was planned


class ChallengeTotals(BaseModel):
    completed: int
    verified: int  # completed AND checked against GitHub
    missed: int
    excused: int
    current_streak: int


class ProjectTime(BaseModel):
    project_id: int
    title: str
    minutes: int


class HabitDone(BaseModel):
    habit_id: int
    name: str
    done_days: int


class Report(BaseModel):
    period: Period
    days: list[ReportDay]
    totals: Totals
    previous: Totals  # the same figures for the period just before this one (same length)
    plan: PlanTotals
    challenge: ChallengeTotals
    projects: list[ProjectTime]
    habits: list[HabitDone]
