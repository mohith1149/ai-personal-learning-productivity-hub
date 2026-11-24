"""Response model for the dashboard: a read-only summary assembled from the other features. Nothing here is stored."""
from datetime import date

from pydantic import BaseModel

from app.schemas.challenges import ChallengeOut, Stats as ChallengeStats
from app.schemas.planner import DaySummary, PlanItem


class TodayPlan(BaseModel):
    summary: DaySummary
    next_items: list[PlanItem]  # the first open items (overdue first), at most 6
    open_count: int


class VideoToday(BaseModel):
    playlist_id: int
    name: str
    daily_target: int
    watched_today: int
    remaining_today: int
    target_met: bool
    up_next: list[str]  # titles of the videos still to watch today


class ChallengeBlock(BaseModel):
    today: ChallengeOut | None
    stats: ChallengeStats


class HabitsBlock(BaseModel):
    active: int
    due_today: int
    best_streak: int  # the longest CURRENT streak among active habits (days or weeks, see unit)
    best_streak_name: str | None
    best_streak_unit: str | None


class ProjectRow(BaseModel):
    id: int
    title: str
    percent: int
    minutes_spent: int
    last_activity_at: str | None


class CourseRow(BaseModel):
    id: int
    title: str
    percent: int
    next_lesson: str | None


class RoadmapBlock(BaseModel):
    total: int
    completed: int
    in_progress: int
    percent: int
    next_topic: str | None


class TasksBlock(BaseModel):
    overdue: int
    today: int
    completed_today: int


class WeekDay(BaseModel):
    date: date
    study_minutes: int
    dev_minutes: int


class Dashboard(BaseModel):
    date: date
    plan: TodayPlan
    videos: list[VideoToday]
    challenge: ChallengeBlock
    habits: HabitsBlock
    tasks: TasksBlock
    projects: list[ProjectRow]
    courses: list[CourseRow]
    roadmap: RoadmapBlock
    week: list[WeekDay]  # the last 7 days, oldest first
    is_empty: bool  # nothing has been added anywhere yet
