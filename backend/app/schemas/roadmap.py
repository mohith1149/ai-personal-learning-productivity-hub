"""Request/response models for the AI Engineering roadmap."""
from datetime import date as DateT, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import Strict
from app.schemas.courses import Notes

TopicStatus = Literal["not_started", "in_progress", "completed"]
Minutes = Annotated[int, Field(ge=1, le=1440)]


class TopicCreate(Strict):
    stage_id: int
    title: str = Field(min_length=1, max_length=200)
    description: Notes | None = None


class TopicUpdate(Strict):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: Notes | None = None
    notes: Notes | None = None


class SetTopicStatus(Strict):
    status: TopicStatus


class StudyCreate(Strict):
    minutes: Minutes
    date: DateT | None = None  # defaults to today in the user's timezone; the future is not allowed
    notes: Notes | None = None


class StudyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    date: DateT
    minutes: int
    notes: str | None
    created_at: datetime


class TopicOut(BaseModel):
    id: int
    stage_id: int
    title: str
    description: str | None
    position: int
    status: str
    notes: str | None
    minutes_spent: int  # sum of the logged study sessions
    study_days: int  # distinct days with a logged session
    last_studied_on: DateT | None
    completed_at: datetime | None


class StageOut(BaseModel):
    id: int
    title: str
    description: str | None
    position: int
    total: int
    completed: int
    in_progress: int
    not_started: int
    percent: int  # floor(completed / total * 100): 100 only when every topic is completed
    minutes_spent: int
    topics: list[TopicOut]


class OverallOut(BaseModel):
    total: int
    completed: int
    in_progress: int
    not_started: int
    percent: int
    minutes_spent: int


class RoadmapOut(BaseModel):
    stages: list[StageOut]
    overall: OverallOut
    next_topic: TopicOut | None  # first topic that is not completed, in roadmap order
