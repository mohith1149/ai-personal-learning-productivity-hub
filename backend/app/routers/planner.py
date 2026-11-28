"""HTTP endpoints for the daily planner. Login required."""
from datetime import date

from fastapi import APIRouter, HTTPException, status

from app.core.deps import CurrentUser, DbSession
from app.schemas import planner as s
from app.services import focus
from app.services import planner as svc
from app.services import prefs

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


@router.post("/roll-over", response_model=s.RollOverOut)
def roll_over(body: s.RollOverIn, user: CurrentUser, db: DbSession):
    """Move today's unfinished tasks to tomorrow. `dry_run` previews it and saves nothing."""
    return _run(svc.roll_over, db, user, body)


def _prefs_out(db, user) -> dict:
    return {"weekday_minutes": prefs.weekday_minutes(db, user), "focus_windows": prefs.focus_windows(db, user), "rest_days_per_month": prefs.settings_row(db, user).rest_days_per_month}


@router.get("/preferences", response_model=s.Preferences)
def get_preferences(user: CurrentUser, db: DbSession):
    out = _prefs_out(db, user)
    db.commit()
    return out


@router.patch("/preferences", response_model=s.Preferences)
def update_preferences(body: s.PreferencesIn, user: CurrentUser, db: DbSession):
    row = prefs.settings_row(db, user)
    data = body.model_dump(exclude_unset=True)
    if "weekday_minutes" in data:
        row.weekday_minutes = prefs.encode(data["weekday_minutes"])
    if "focus_windows" in data:
        row.focus_windows = focus.encode(data["focus_windows"])
    if data.get("rest_days_per_month") is not None:
        row.rest_days_per_month = data["rest_days_per_month"]
    db.commit()
    return _prefs_out(db, user)
