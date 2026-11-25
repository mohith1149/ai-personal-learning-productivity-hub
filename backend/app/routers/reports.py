"""Weekly and monthly reports. Login required. Read-only."""
from datetime import date
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.core.deps import CurrentUser, DbSession
from app.schemas import reports as s
from app.services import reports as svc

router = APIRouter(prefix="/reports", tags=["reports"])


def _run(fn, *args):
    try:
        return fn(*args)
    except svc.RuleError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from None


@router.get("/weekly", response_model=s.Report)
def weekly(user: CurrentUser, db: DbSession, week_start: Annotated[date | None, Query(description="Any day in the week (Monday to Sunday). Default: this week.")] = None):
    return _run(svc.weekly, db, user, week_start)


@router.get("/monthly", response_model=s.Report)
def monthly(user: CurrentUser, db: DbSession, month: Annotated[str | None, Query(description="YYYY-MM. Default: this month.")] = None):
    return _run(svc.monthly, db, user, month)
