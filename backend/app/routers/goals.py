"""Goals (courses and projects with a target date) and whether you are on pace. Login required."""
from datetime import date as Day
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.deps import CurrentUser, DbSession
from app.services import goals as svc

router = APIRouter(prefix="/goals", tags=["goals"])


class GoalOut(BaseModel):
    kind: Literal["course", "project"]
    id: int
    title: str
    target_date: Day
    status: Literal["done", "overdue", "behind", "stalled", "not_started", "on_track", "unknown"]
    warning: bool
    message: str
    unit: str
    total: int
    done: int
    remaining: int
    days_left: int
    needed_per_day: float
    recent_per_day: float
    projected_date: Day | None


@router.get("", response_model=list[GoalOut])
def goals(user: CurrentUser, db: DbSession):
    return svc.list_goals(db, user)
