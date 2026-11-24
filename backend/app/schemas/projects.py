"""Request/response models for projects, their milestones, tasks and development sessions."""
import re
from datetime import date as DateT, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.common import Strict
from app.schemas.courses import Notes

Status = Literal["active", "paused", "completed", "archived"]
Origin = Literal["new", "existing"]
Priority = Annotated[int, Field(ge=1, le=4)]  # 1 = urgent ... 4 = low
Minutes = Annotated[int, Field(ge=1, le=1440)]
TechItem = Annotated[str, Field(max_length=40)]  # blanks and repeats are dropped by the validator

_GITHUB = re.compile(r"^https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?$")


def normalise_repo_url(v: str | None) -> str | None:
    """Only real GitHub repository links (https://github.com/owner/name) are accepted; they are stored in that exact form."""
    if v is None:
        return None
    m = _GITHUB.match(v.strip())
    if not m:
        raise ValueError("Enter a GitHub repository link like https://github.com/owner/repository")
    return f"https://github.com/{m.group(1)}/{m.group(2)}"


class _ProjectFields(Strict):
    @field_validator("repo_url", check_fields=False)
    @classmethod
    def _repo(cls, v):
        return normalise_repo_url(v)

    @field_validator("tech_stack", check_fields=False)
    @classmethod
    def _stack(cls, v):
        if v is None:
            return v
        seen, out = set(), []
        for item in v:  # drop blanks/duplicates, keep order
            item = item.strip()
            if item and item.lower() not in seen:
                seen.add(item.lower())
                out.append(item)
        return out

    @model_validator(mode="after")
    def _dates(self):
        start, target = getattr(self, "start_date", None), getattr(self, "target_date", None)
        if start and target and target < start:
            raise ValueError("The target date can't be before the start date")
        return self


class ProjectCreate(_ProjectFields):
    title: str = Field(min_length=1, max_length=200)
    origin: Origin = "new"  # started here, or an existing project you're bringing in
    description: Notes | None = None
    objective: Notes | None = None
    tech_stack: list[TechItem] = Field(default_factory=list, max_length=20)
    repo_url: str | None = Field(default=None, max_length=500)
    status: Status = "active"
    priority: Priority = 2
    start_date: DateT | None = None  # defaults to today for a new project
    target_date: DateT | None = None
    notes: Notes | None = None


class ProjectUpdate(_ProjectFields):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    origin: Origin | None = None
    description: Notes | None = None
    objective: Notes | None = None
    tech_stack: list[TechItem] | None = Field(default=None, max_length=20)
    repo_url: str | None = Field(default=None, max_length=500)
    status: Status | None = None
    priority: Priority | None = None
    start_date: DateT | None = None
    target_date: DateT | None = None
    notes: Notes | None = None


class MilestoneCreate(Strict):
    title: str = Field(min_length=1, max_length=200)
    description: Notes | None = None
    due_date: DateT | None = None


class MilestoneUpdate(Strict):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: Notes | None = None
    due_date: DateT | None = None


class MilestoneStatus(Strict):
    status: Literal["pending", "done"]
    evidence: Notes | None = None  # what shows it's really done (a commit, a link, a note)


class TaskCreate(Strict):
    title: str = Field(min_length=1, max_length=200)
    description: Notes | None = None
    priority: Priority = 2
    due_date: DateT | None = None
    estimated_minutes: Annotated[int, Field(ge=1, le=100000)] | None = None


class SessionCreate(Strict):
    minutes: Minutes
    summary: str = Field(min_length=3, max_length=5000)  # what was actually done
    date: DateT | None = None  # defaults to today in the user's timezone; the future is not allowed
    milestone_id: int | None = None
    task_id: int | None = None
    notes: Notes | None = None


class MilestoneOut(BaseModel):
    id: int
    title: str
    description: str | None
    status: str
    position: int
    due_date: DateT | None
    completed_at: datetime | None
    evidence: str | None
    overdue: bool  # still pending and past its due date


class TaskOut(BaseModel):
    id: int
    title: str
    status: str
    priority: int
    due_date: DateT | None
    estimated_minutes: int | None
    completed_at: datetime | None


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    date: DateT
    minutes: int
    summary: str
    milestone_id: int | None
    task_id: int | None
    notes: str | None
    created_at: datetime


class Progress(BaseModel):
    milestones_done: int
    milestones_total: int
    tasks_done: int  # completed tasks
    tasks_total: int  # tasks that aren't cancelled
    percent: int  # floor(done / total) over milestones + tasks together; 0 when there is nothing yet


class ProjectSummary(BaseModel):
    id: int
    title: str
    origin: str
    status: str
    priority: int
    description: str | None
    objective: str | None
    tech_stack: list[str]
    repo_url: str | None
    start_date: DateT | None
    target_date: DateT | None
    completed_at: datetime | None
    last_activity_at: datetime | None
    created_at: datetime
    progress: Progress
    minutes_spent: int  # sum of development sessions
    session_count: int
    days_active: int  # distinct days with a session
    overdue: bool  # active, has a target date in the past


class ProjectDetail(ProjectSummary):
    notes: str | None
    milestones: list[MilestoneOut]
    tasks: list[TaskOut]
    sessions: list[SessionOut]  # newest first
