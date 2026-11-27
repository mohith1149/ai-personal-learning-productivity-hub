"""The running stopwatch. Login required."""
from datetime import date as Day
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field

from app.core.deps import CurrentUser, DbSession
from app.schemas.common import Strict
from app.services import courses, projects, roadmap
from app.services import timer as svc

router = APIRouter(prefix="/timer", tags=["timer"])


class TimerOut(BaseModel):
    kind: str
    label: str
    started_at: datetime
    elapsed_seconds: int
    logs_to: str | None
    task_id: int | None
    lesson_id: int | None
    topic_id: int | None
    course_id: int | None
    project_id: int | None


class StartIn(Strict):
    kind: Literal["task", "lesson", "course", "topic", "project"]
    ref_id: int = Field(ge=1)


class StopIn(Strict):
    minutes: int | None = Field(default=None, ge=1, le=1440)
    summary: str | None = Field(default=None, max_length=5000)  # project sessions: what you did


class StopOut(BaseModel):
    minutes: int
    logged_to: str  # project | course | topic | task
    target_id: int | None
    label: str
    date: Day


def _http(e: Exception) -> HTTPException:
    if isinstance(e, (svc.NotFound, projects.NotFound, courses.NotFound, roadmap.NotFound)):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(e))
    if isinstance(e, svc.Conflict):
        return HTTPException(status.HTTP_409_CONFLICT, str(e))
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e))


@router.get("", response_model=TimerOut | None)
def current(user: CurrentUser, db: DbSession):
    return svc.view(db, user)


@router.post("/start", response_model=TimerOut, status_code=status.HTTP_201_CREATED)
def start(body: StartIn, user: CurrentUser, db: DbSession):
    try:
        return svc.start(db, user, body.kind, body.ref_id)
    except (svc.NotFound, svc.Conflict, svc.RuleError) as e:
        raise _http(e) from None


@router.post("/stop", response_model=StopOut)
def stop(body: StopIn, user: CurrentUser, db: DbSession):
    try:
        return svc.stop(db, user, body.minutes, body.summary)
    except (svc.NotFound, svc.Conflict, ValueError, projects.NotFound, courses.NotFound, roadmap.NotFound) as e:
        raise _http(e) from None


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def discard(user: CurrentUser, db: DbSession):
    try:
        svc.discard(db, user)
    except svc.NotFound as e:
        raise _http(e) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
