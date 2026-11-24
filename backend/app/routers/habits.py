"""HTTP endpoints for habits. Login required."""
from datetime import date
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.core.deps import CurrentUser, DbSession
from app.schemas import habits as s
from app.services import habits as svc

router = APIRouter(prefix="/habits", tags=["habits"])

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


@router.get("", response_model=s.HabitList)
def list_habits(user: CurrentUser, db: DbSession):
    return svc.list_habits(db, user)


@router.post("", response_model=s.HabitOut, status_code=status.HTTP_201_CREATED)
def create_habit(body: s.HabitCreate, user: CurrentUser, db: DbSession):
    return _run(svc.create_habit, db, user, body)


@router.get("/{habit_id}", response_model=s.HabitOut)
def get_habit(habit_id: int, user: CurrentUser, db: DbSession):
    return _run(svc.get_habit, db, user, habit_id)


@router.patch("/{habit_id}", response_model=s.HabitOut)
def update_habit(habit_id: int, body: s.HabitUpdate, user: CurrentUser, db: DbSession):
    return _run(svc.update_habit, db, user, habit_id, body)


@router.delete("/{habit_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_habit(habit_id: int, user: CurrentUser, db: DbSession) -> Response:
    _run(svc.delete_habit, db, user, habit_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{habit_id}/logs", response_model=list[s.LogOut])
def history(habit_id: int, user: CurrentUser, db: DbSession, days: Annotated[int, Query(ge=1, le=730)] = 90):
    """Daily records, newest first, for the last `days` days."""
    return _run(svc.history, db, user, habit_id, days)


@router.put("/{habit_id}/logs/{day}", response_model=s.HabitOut)
def set_log(habit_id: int, day: date, body: s.LogIn, user: CurrentUser, db: DbSession):
    """Create or replace the record for one day. Returns the habit with refreshed streak and progress."""
    return _run(svc.set_log, db, user, habit_id, day, body)


@router.delete("/{habit_id}/logs/{day}", response_model=s.HabitOut)
def delete_log(habit_id: int, day: date, user: CurrentUser, db: DbSession):
    return _run(svc.delete_log, db, user, habit_id, day)
