"""HTTP endpoints for the daily AI project challenge. Login required."""
from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.core.deps import CurrentUser, DbSession
from app.core.timeutil import user_today
from app.schemas import challenges as s
from app.services import challenges as svc

router = APIRouter(prefix="/challenges", tags=["challenges"])

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


@router.get("/today", response_model=s.Today)
def today(user: CurrentUser, db: DbSession):
    """Today's challenge (if planned), your streak and totals, and ideas for what to build today."""
    return svc.today_view(db, user)


@router.get("/calendar", response_model=s.Calendar)
def calendar(user: CurrentUser, db: DbSession, start: date | None = None, end: date | None = None):
    """Day-by-day status. Defaults to the last 30 days."""
    end = end or user_today(user)
    return _run(svc.calendar, db, user, start or end - timedelta(days=29), end)


@router.get("/history", response_model=list[s.ChallengeOut])
def history(user: CurrentUser, db: DbSession, limit: Annotated[int, Query(ge=1, le=200)] = 60):
    return svc.history(db, user, limit)


@router.post("", response_model=s.ChallengeOut, status_code=status.HTTP_201_CREATED)
def create(body: s.ChallengeCreate, user: CurrentUser, db: DbSession):
    return _run(svc.create_challenge, db, user, body)


@router.post("/excuse", response_model=s.ChallengeOut)
def excuse(body: s.ExcuseIn, user: CurrentUser, db: DbSession):
    """Excuse today or a past day (a reason is required)."""
    return _run(svc.excuse_day, db, user, body)


@router.get("/{challenge_id}", response_model=s.ChallengeOut)
def get_one(challenge_id: int, user: CurrentUser, db: DbSession):
    return _run(svc.get_challenge, db, user, challenge_id)


@router.patch("/{challenge_id}", response_model=s.ChallengeOut)
def update(challenge_id: int, body: s.ChallengeUpdate, user: CurrentUser, db: DbSession):
    return _run(svc.update_challenge, db, user, challenge_id, body)


@router.post("/{challenge_id}/start", response_model=s.ChallengeOut)
def start(challenge_id: int, user: CurrentUser, db: DbSession):
    return _run(svc.start_challenge, db, user, challenge_id)


@router.post("/{challenge_id}/complete", response_model=s.ChallengeOut)
def complete(challenge_id: int, body: s.CompleteIn, user: CurrentUser, db: DbSession):
    return _run(svc.complete_challenge, db, user, challenge_id, body)


@router.delete("/{challenge_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(challenge_id: int, user: CurrentUser, db: DbSession) -> Response:
    _run(svc.delete_challenge, db, user, challenge_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
