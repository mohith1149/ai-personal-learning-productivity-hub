"""HTTP endpoints for the daily AI project challenge. Login required."""
from datetime import date, timedelta
from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.config import get_settings
from app.core.deps import CurrentUser, DbSession
from app.core.timeutil import user_today
from app.schemas import challenges as s
from app.services import challenges as svc
from app.services import github as gh

router = APIRouter(prefix="/challenges", tags=["challenges"])

ERRORS = (svc.NotFound, svc.RuleError, svc.Conflict)


def _http(exc: Exception) -> HTTPException:
    if isinstance(exc, svc.NotFound):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    if isinstance(exc, svc.Conflict):
        return HTTPException(status.HTTP_409_CONFLICT, str(exc))
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc))


_GH_STATUS = {"bad_repo": 422, "bad_sha": 422, "not_found": 404, "rate_limited": 429, "bad_token": 503, "network": 502, "api_error": 502}


def get_github(user: CurrentUser) -> Iterator[gh.GitHubClient]:
    """One client per request (tests replace this dependency with a fake-transport client)."""
    client = gh.GitHubClient(get_settings().github_token)
    try:
        yield client
    finally:
        client.close()


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


@router.post("/{challenge_id}/verify", response_model=s.VerifyOut)
def verify(challenge_id: int, user: CurrentUser, db: DbSession, client: Annotated[gh.GitHubClient, Depends(get_github)]):
    """Check the completed day's commit against GitHub. Only a pass marks it verified."""
    try:
        return _run(svc.verify_challenge, db, user, challenge_id, client)
    except gh.GitHubError as e:
        raise HTTPException(_GH_STATUS.get(e.code, 502), e.message) from None


@router.delete("/{challenge_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(challenge_id: int, user: CurrentUser, db: DbSession) -> Response:
    _run(svc.delete_challenge, db, user, challenge_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
