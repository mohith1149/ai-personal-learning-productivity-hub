"""Planned rest days. Login required."""
from datetime import date as Day
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.core.deps import CurrentUser, DbSession
from app.core.timeutil import user_today
from app.schemas.common import Strict
from app.services import rest as svc

router = APIRouter(prefix="/rest-days", tags=["rest-days"])


class RestDayOut(BaseModel):
    date: Day
    reason: str | None


class MonthOut(BaseModel):
    month: str  # YYYY-MM
    cap: int  # rest days allowed that month
    used: int
    left: int
    days: list[RestDayOut]


class RestDayIn(Strict):
    date: Day
    reason: str | None = Field(default=None, max_length=200)


def _http(e: Exception) -> HTTPException:
    if isinstance(e, svc.NotFound):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(e))
    if isinstance(e, svc.Conflict):
        return HTTPException(status.HTTP_409_CONFLICT, str(e))
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e))


@router.get("", response_model=MonthOut)
def month(user: CurrentUser, db: DbSession, month: Annotated[str | None, Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$", description="YYYY-MM. Default: this month.")] = None):
    if month is None:
        t = user_today(user)
        year, mon = t.year, t.month
    else:
        year, mon = int(month[:4]), int(month[5:])
    if not 2000 <= year <= 2100:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "That month is out of range")
    return svc.month_view(db, user, year, mon)


@router.post("", response_model=MonthOut, status_code=status.HTTP_201_CREATED)
def add(body: RestDayIn, user: CurrentUser, db: DbSession):
    try:
        return svc.add(db, user, body.date, body.reason)
    except (svc.RuleError, svc.Conflict) as e:
        raise _http(e) from None


@router.delete("/{day}", response_model=MonthOut)
def remove(day: Day, user: CurrentUser, db: DbSession):
    try:
        return svc.remove(db, user, day)
    except svc.NotFound as e:
        raise _http(e) from None
