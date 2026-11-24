"""HTTP endpoints for the daily planner. Login required."""
from datetime import date

from fastapi import APIRouter, HTTPException, status

from app.core.deps import CurrentUser, DbSession
from app.schemas import planner as s
from app.services import planner as svc

router = APIRouter(prefix="/planner", tags=["planner"])

ERRORS = (svc.NotFound, svc.RuleError, svc.Conflict)


def _http(exc: Exception) -> HTTPException:
    if isinstance(exc, svc.NotFound):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    if isinstance(exc, svc.Conflict):
        return HTTPException(status.HTTP_409_CONFLICT, str(exc))
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc))


def _run(fn, *args):
    try:
        return fn(*args)
    except ERRORS as e:
        raise _http(e) from None


@router.get("", response_model=s.DayPlan)
def get_day(user: CurrentUser, db: DbSession, day: date | None = None):
    """The plan for one day (default: today in your timezone), assembled from your tasks, courses, videos, roadmap, habits and projects."""
    from app.core.timeutil import user_today

    return svc.build_day(db, user, day or user_today(user))


@router.post("/complete", response_model=s.DayPlan)
def complete(body: s.ItemRef, user: CurrentUser, db: DbSession):
    return _run(svc.complete_item, db, user, body)


@router.post("/reopen", response_model=s.DayPlan)
def reopen(body: s.ItemRef, user: CurrentUser, db: DbSession):
    return _run(svc.reopen_item, db, user, body)


@router.post("/tasks/{task_id}/reschedule", response_model=s.DayPlan)
def reschedule(task_id: int, body: s.RescheduleIn, user: CurrentUser, db: DbSession):
    return _run(svc.reschedule_task, db, user, task_id, body)


@router.post("/excuse", response_model=s.DayPlan)
def excuse(body: s.ExcuseIn, user: CurrentUser, db: DbSession):
    return _run(svc.excuse_item, db, user, body)


@router.post("/unexcuse", response_model=s.DayPlan)
def unexcuse(body: s.ItemRef, user: CurrentUser, db: DbSession):
    return _run(svc.remove_excuse, db, user, body)
