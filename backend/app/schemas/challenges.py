"""Request/response models for the daily AI project challenge."""
import re
from datetime import date as DateT, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.common import Strict
from app.schemas.courses import Notes
from app.schemas.projects import Minutes, normalise_repo_url

Mode = Literal["new_project", "existing_project"]
Status = Literal["planned", "in_progress", "completed", "missed", "excused"]
CalendarStatus = Literal["planned", "in_progress", "completed", "missed", "excused", "rest", "none"]

_SHA = re.compile(r"^[0-9a-f]{7,40}$")


class NewProject(Strict):
    title: str = Field(min_length=1, max_length=200)
    description: Notes | None = None
    repo_url: str | None = Field(default=None, max_length=500)

    @field_validator("repo_url")
    @classmethod
    def _repo(cls, v):
        return normalise_repo_url(v)


class ChallengeCreate(Strict):
    date: DateT | None = None  # defaults to today in your timezone; the past is not allowed
    mode: Mode
    project_id: int | None = None  # existing_project: which project
    new_project: NewProject | None = None  # new_project: the project to start
    planned_task: str = Field(min_length=3, max_length=500)  # what you will build/do today
    estimated_minutes: Minutes | None = None

    @model_validator(mode="after")
    def _mode_matches(self):
        if self.mode == "existing_project" and (self.project_id is None or self.new_project is not None):
            raise ValueError("Pick the existing project you will continue")
        if self.mode == "new_project" and (self.new_project is None or self.project_id is not None):
            raise ValueError("Describe the new project you will start")
        return self


class ChallengeUpdate(Strict):
    planned_task: str | None = Field(default=None, min_length=3, max_length=500)
    estimated_minutes: Minutes | None = None


class CompleteIn(Strict):
    """Evidence for the day. Nothing here is checked against GitHub yet (Phase 4), so the day is stored as 'unverified'."""

    summary: str = Field(min_length=30, max_length=5000)  # what you actually implemented
    repo_url: str = Field(max_length=500)
    commit_sha: str = Field(min_length=7, max_length=40)
    commit_message: str = Field(min_length=3, max_length=500)
    minutes: Minutes
    milestone_id: int | None = None
    evidence_notes: Notes | None = None

    @field_validator("repo_url")
    @classmethod
    def _repo(cls, v):
        return normalise_repo_url(v)

    @field_validator("commit_sha")
    @classmethod
    def _sha(cls, v: str):
        v = v.strip().lower()
        if not _SHA.match(v):
            raise ValueError("A commit hash is 7 to 40 hexadecimal characters (0-9, a-f)")
        return v


class ExcuseIn(Strict):
    date: DateT | None = None  # defaults to today; past days are allowed, future days are not
    reason: str = Field(min_length=5, max_length=1000)


class ProjectRef(BaseModel):
    id: int
    title: str
    repo_url: str | None


class MilestoneRef(BaseModel):
    id: int
    title: str


class ChallengeOut(BaseModel):
    id: int
    date: DateT
    mode: Mode
    status: Status  # 'missed' is worked out from the date: a planned/started day that has passed
    project: ProjectRef | None
    planned_task: str
    estimated_minutes: int | None
    actual_minutes: int | None
    implemented_summary: str | None
    repo_url: str | None
    commit_sha: str | None
    commit_message: str | None
    evidence_notes: str | None
    milestone: MilestoneRef | None
    verification_status: Literal["unverified", "verified"]
    excuse_reason: str | None
    completed_at: datetime | None
    can_complete: bool
    can_edit: bool


class Suggestion(BaseModel):
    source: Literal["project", "roadmap", "course", "previous"]
    mode: Mode
    project_id: int | None
    title: str
    detail: str | None
    planned_task: str


class Stats(BaseModel):
    completed: int
    excused: int
    rest_days: int = 0  # planned rest days up to today; like excused days they neither add to nor break the streak
    missed: int
    completion_rate: int  # completed / (completed + missed), floored
    current_streak: int
    longest_streak: int
    total_minutes: int
    first_day: DateT | None


class Today(BaseModel):
    date: DateT
    rest_day: bool = False  # today is a planned rest day
    challenge: ChallengeOut | None
    stats: Stats
    suggestions: list[Suggestion]


class CalendarDay(BaseModel):
    date: DateT
    status: CalendarStatus
    project_title: str | None
    challenge_id: int | None


class Calendar(BaseModel):
    start: DateT
    end: DateT
    days: list[CalendarDay]
    stats: Stats


class VerifyCheck(BaseModel):
    name: str
    ok: bool
    detail: str


class VerifyOut(BaseModel):
    verified: bool
    checks: list[VerifyCheck]
    challenge: ChallengeOut
